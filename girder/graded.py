"""Continuous graded static loading: shared zero point, ordered steps and paired return check."""

from dataclasses import asdict, dataclass

from .errors import Rejected
from .exact import encode
from .loadcase import Axle, parse_axle
from .phase_samples import summarize_window
from .validation import fields, key, number, records, text
from .windows import FINAL_EMPTY, FIRST_EMPTY

DIRECTIONS = ("up", "peak", "back")
DIRECTION_NAMES = {"up": "去程", "peak": "峰值", "back": "回程"}
DIRECTION_ALIASES = {
    "up": "up", "forward": "up", "outbound": "up", "去程": "up",
    "peak": "peak", "峰值": "peak",
    "back": "back", "return": "back", "down": "back", "inbound": "back", "回程": "back",
}


@dataclass(frozen=True)
class Level:
    id: str
    label: str
    lane: str
    target_kg: int
    tolerance_kg: int
    contrast_tolerance_kg: int
    axles: tuple[Axle, ...]


@dataclass(frozen=True)
class GradedStep:
    id: str
    level: str
    direction: str
    window: tuple[int, int]


@dataclass(frozen=True)
class Contrast:
    level: str
    forward: str
    back: str

    @property
    def id(self):
        return self.level


@dataclass(frozen=True)
class Graded:
    id: str
    label: str
    first_empty: tuple[int, int]
    final_empty: tuple[int, int]
    levels: tuple[Level, ...]
    steps: tuple[GradedStep, ...]
    contrasts: tuple[Contrast, ...]


def _window(value, label):
    if not isinstance(value, list) or len(value) != 2:
        raise Rejected(f"{label}须给出两个整秒端点")
    start, end = [number(t, "时间窗端点") for t in value]
    if start >= end:
        raise Rejected(f"{label}的起点须小于终点")
    return start, end


def _pick(item, *names):
    for name in names:
        if name in item:
            return item[name]
    raise Rejected(f"缺少字段：{names[0]}")


def parse_level(item):
    fields(item, "id label lane target_kg tolerance_kg axles", "分级级别",
           optional="contrast_tolerance_kg contrast_kg paired_tolerance_kg")
    contrast = _pick(item, "contrast_tolerance_kg", "contrast_kg", "paired_tolerance_kg")
    return Level(key(item["id"], "级别号"), text(item["label"], "级别名"), key(item["lane"], "车道"),
                 number(item["target_kg"], "目标总质量", 1), number(item["tolerance_kg"], "单台阶容差"),
                 number(contrast, "对照容差"),
                 tuple(records(item["axles"], parse_axle, "级别目标车轴", 16)))


def parse_step(item):
    fields(item, "id level window", "分级台阶", optional="direction kind")
    direction = _pick(item, "direction", "kind")
    if direction not in DIRECTION_ALIASES:
        raise Rejected("台阶方向须为去程、峰值或回程")
    return GradedStep(key(item["id"], "台阶号"), key(item["level"], "级别号"), DIRECTION_ALIASES[direction],
                      _window(item["window"], "台阶时间窗"))


def parse_contrast(item):
    fields(item, "level", "去回对照", optional="forward up outbound back down return")
    forward = _pick(item, "forward", "up", "outbound")
    back = _pick(item, "back", "down", "return")
    return Contrast(key(item["level"], "级别号"), key(forward, "去程台阶号"), key(back, "回程台阶号"))


def _optional_records(value, parser, label, maximum):
    if not isinstance(value, list) or len(value) > maximum:
        raise Rejected(f"{label}须为不超过 {maximum} 条的记录列表")
    result = [parser(item) for item in value]
    if len({item.id for item in result}) != len(result):
        raise Rejected(f"{label}中的编号重复")
    return result


def parse_graded(item):
    fields(item, "id label first_empty final_empty levels steps", "分级试验", optional="contrasts")
    identity = key(item["id"], "分级试验号")
    label = text(item["label"], "分级试验名")
    first_empty = _window(item["first_empty"], "首空载时间窗")
    final_empty = _window(item["final_empty"], "末段撤净时间窗")
    levels = records(item["levels"], parse_level, "分级级别", 8)
    steps = records(item["steps"], parse_step, "分级台阶", 12)
    contrasts = _optional_records(item.get("contrasts", []), parse_contrast, "去回对照", 8)
    level_ids = {level.id for level in levels}
    by_step = {step.id: step for step in steps}
    if any(step.level not in level_ids for step in steps):
        raise Rejected("分级台阶须引用已登记级别")
    ordered = [first_empty, *(step.window for step in steps), final_empty]
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise Rejected("首空载、各台阶和末段撤净窗口须按顺序且互不重叠")
    seen = set()
    for contrast in contrasts:
        if contrast.level not in level_ids or contrast.level in seen:
            raise Rejected("去回对照须引用唯一且已登记的级别")
        seen.add(contrast.level)
        if contrast.forward not in by_step or contrast.back not in by_step:
            raise Rejected("去回对照须引用已登记台阶")
        forward, back = by_step[contrast.forward], by_step[contrast.back]
        if forward.level != contrast.level or back.level != contrast.level or contrast.forward == contrast.back:
            raise Rejected("去回对照须使用同级指定台阶，不得以邻级或峰值顶替")
        if forward.direction != "up" or back.direction != "back":
            raise Rejected("去回对照须使用去程和回程台阶，峰值不得顶替")
    return Graded(identity, label, first_empty, final_empty, tuple(levels), tuple(steps), tuple(contrasts))


def step_axes(graded):
    """Map each step id to the axle identifiers registered for its level."""
    levels = {level.id: level for level in graded.levels}
    return {step.id: {axle.id for axle in levels[step.level].axles} for step in graded.steps}


def _window_values(plan, pairs, gaps, label):
    summaries, values = {}, {}
    for point in plan.points:
        summaries[point.id], values[point.id] = summarize_window(
            pairs, gaps, "graded", plan.graded.id, point.id, label, plan.minimum_pairs)
    return summaries, values


def _point_view(summary, point_id):
    return dict(point=point_id, median_um=summary["median_um"], pair_count=summary["pair_count"],
                pairs=summary["pairs"], gaps=summary["gaps"])


def evaluate_graded(plan, step_placement, pairs, gaps):
    """Reduce the registered continuous process; return (graded report, ready)."""
    graded = plan.graded
    if graded is None:
        return None, True
    levels = {level.id: level for level in graded.levels}

    empty = {}
    for label in (FIRST_EMPTY, FINAL_EMPTY):
        summaries, values = _window_values(plan, pairs, gaps, label)
        empty[label] = dict(values=values,
                            points=[_point_view(summaries[point.id], point.id) for point in plan.points])

    steps, step_values = [], {}
    for step in graded.steps:
        summaries, values = _window_values(plan, pairs, gaps, step.id)
        step_values[step.id] = values
        steps.append(dict(id=step.id, level=step.level, direction=step.direction,
                          direction_name=DIRECTION_NAMES[step.direction], window=list(step.window),
                          placement=step_placement[step.id],
                          points=[_point_view(summaries[point.id], point.id) for point in plan.points]))

    first, final = empty[FIRST_EMPTY]["values"], empty[FINAL_EMPTY]["values"]
    points = []
    for point in plan.points:
        leading, trailing = first[point.id], final[point.id]
        complete = leading is not None and trailing is not None
        points.append(dict(point=point.id, first_empty_um=encode(leading), final_empty_um=encode(trailing),
                           residual_um=encode(trailing - leading if complete else None),
                           state="valid" if complete else "coverage"))

    contrasts, workorder = [], []
    for contrast in graded.contrasts:
        level = levels[contrast.level]
        forward_placement = step_placement[contrast.forward]
        back_placement = step_placement[contrast.back]
        structural = forward_placement["valid"] and back_placement["valid"]
        forward_total, back_total = forward_placement["total_kg"], back_placement["total_kg"]
        mass_delta = None if forward_total is None or back_total is None else abs(back_total - forward_total)
        mass_ok = mass_delta is not None and mass_delta <= level.contrast_tolerance_kg
        rows = []
        for point in plan.points:
            zero, finish = first[point.id], final[point.id]
            forward, back = step_values[contrast.forward][point.id], step_values[contrast.back][point.id]
            complete = zero is not None and finish is not None
            forward_displacement = forward - zero if complete and forward is not None else None
            back_displacement = back - zero if complete and back is not None else None
            difference = None
            if not structural:
                state = "placement"
            elif not complete or forward is None or back is None:
                state = "coverage"
            elif not mass_ok:
                state = "mass"
            else:
                difference = back_displacement - forward_displacement
                state = "valid"
            residual = next(item["residual_um"] for item in points if item["point"] == point.id)
            row = dict(point=point.id, first_empty_um=encode(zero), final_empty_um=encode(finish),
                       forward_um=encode(forward), back_um=encode(back),
                       forward_displacement_um=encode(forward_displacement),
                       back_displacement_um=encode(back_displacement), difference_um=encode(difference),
                       residual_um=residual, state=state)
            rows.append(row)
            workorder.append(dict(level=level.id, level_label=level.label, forward=contrast.forward,
                                  back=contrast.back, **row))
        if not structural:
            state = "placement"
        elif any(row["state"] == "coverage" for row in rows):
            state = "coverage"
        elif not mass_ok:
            state = "mass"
        else:
            state = "valid"
        contrasts.append(dict(level=level.id, level_label=level.label, forward=contrast.forward, back=contrast.back,
                              contrast_tolerance_kg=level.contrast_tolerance_kg, mass_delta_kg=mass_delta,
                              state=state, points=rows))

    missing = []
    for step in graded.steps:
        if not step_placement[step.id]["valid"]:
            missing.append(dict(kind="step_placement", step=step.id, level=step.level))
    for item in points:
        if item["state"] != "valid":
            missing.append(dict(kind="empty_coverage", point=item["point"]))
    for item, contrast in zip(contrasts, graded.contrasts):
        if item["state"] != "valid":
            missing.append(dict(kind="contrast", level=contrast.level, state=item["state"]))

    report = dict(id=graded.id, label=graded.label,
                  first_empty_window=list(graded.first_empty), final_empty_window=list(graded.final_empty),
                  first_empty=dict(window=list(graded.first_empty), points=empty[FIRST_EMPTY]["points"]),
                  final_empty=dict(window=list(graded.final_empty), points=empty[FINAL_EMPTY]["points"]),
                  points=points, steps=steps, contrasts=contrasts, workorder=workorder, missing=missing,
                  ready=not missing)
    return report, report["ready"]


def graded_evidence(survey, report, graded_id, point):
    """Gather trace evidence for one point: axle placement, shared empties and adopted/missing contrasts."""
    graded = report.get("graded")
    if graded is None or graded["id"] != graded_id:
        raise Rejected("找不到该分级试验", 404)
    if point not in {row["point"] for row in graded["points"]}:
        raise Rejected("找不到该测点", 404)

    reading_ids = set()

    def collect(phases):
        for pair in phases["pairs"]:
            reading_ids.update((pair["point_row"], pair["reference_row"]))
        for gap in phases["gaps"]:
            reading_ids.update(gap["point_rows"] + gap["reference_rows"])

    steps = []
    for step in graded["steps"]:
        found = next(row for row in step["points"] if row["point"] == point)
        collect(found)
        steps.append(dict(id=step["id"], level=step["level"], direction=step["direction"],
                          direction_name=step["direction_name"], window=step["window"],
                          placement=step["placement"], phases=found))
    empties = {}
    for label, window in ((FIRST_EMPTY, graded["first_empty_window"]), (FINAL_EMPTY, graded["final_empty_window"])):
        found = next(row for row in graded[label]["points"] if row["point"] == point)
        collect(found)
        empties[label] = dict(window=window, phases=found)

    contrasts = []
    for contrast in graded["contrasts"]:
        found = next(row for row in contrast["points"] if row["point"] == point)
        contrasts.append(dict(level=contrast["level"], level_label=contrast["level_label"],
                              forward=contrast["forward"], back=contrast["back"], state=found["state"],
                              mass_delta_kg=contrast["mass_delta_kg"],
                              contrast_tolerance_kg=contrast["contrast_tolerance_kg"],
                              adopted=found["state"] == "valid", difference_um=found["difference_um"],
                              forward_displacement_um=found["forward_displacement_um"],
                              back_displacement_um=found["back_displacement_um"], evidence=found))
    response = next(row for row in graded["points"] if row["point"] == point)
    positions = [asdict(survey.positions[row_id]) for step in graded["steps"]
                 for axle in step["placement"]["axles"] for row_id in axle["evidence"]]
    readings = [asdict(survey.readings[row_id]) for row_id in sorted(reading_ids)]
    return dict(graded=graded_id, point=point, response=response,
                workorder=[row for row in graded.get("workorder", []) if row["point"] == point],
                first_empty=empties[FIRST_EMPTY], final_empty=empties[FINAL_EMPTY],
                steps=steps, contrasts=contrasts, positions=positions, readings=readings)
