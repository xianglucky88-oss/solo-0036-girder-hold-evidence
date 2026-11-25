from dataclasses import dataclass
from fractions import Fraction

from .clockmap import parse_clock
from .errors import Rejected
from .layout import Point, parse_point
from .loadcase import LoadCase, parse_case
from .validation import fields, key, number, optional_fields, records, text
from .windows import Hold, WindowIndex, parse_hold


@dataclass(frozen=True)
class Plan:
    id: str
    label: str
    span_mm: int
    references: tuple[str, ...]
    points: tuple[Point, ...]
    cases: tuple[LoadCase, ...]
    holds: tuple[Hold, ...]
    minimum_pairs: int
    residual_limit_um: int
    repeat_limit_um: int
    pair_tolerance_s: Fraction


def parse_plan(data):
    optional_fields(data, "id label span_mm references points cases holds minimum_pairs residual_limit_um "
                          "repeat_limit_um pair_tolerance_s", "试验计划")
    fields(data, "id label span_mm references points cases holds minimum_pairs residual_limit_um repeat_limit_um", "试验计划")
    span = number(data["span_mm"], "跨长", 1)
    refs = data["references"]
    if not isinstance(refs, list) or not 1 <= len(refs) <= 12:
        raise Rejected("参考点须有 1 至 12 个编号")
    refs = [key(ref, "参考点号") for ref in refs]
    points = records(data["points"], parse_point, "测点", 24)
    cases = records(data["cases"], parse_case, "工况", 16)
    holds = records(data["holds"], parse_hold, "轮次", 40)
    if len(set(refs)) != len(refs) or set(refs) & {point.id for point in points}:
        raise Rejected("参考点与测点编号必须全局唯一")
    if any(point.reference not in refs or point.station_mm > span for point in points):
        raise Rejected("测点须在跨内且引用已登记参考点")
    if any(axle.target_mm > span for case in cases for axle in case.axles):
        raise Rejected("计划轴位须在跨内")
    if {hold.case for hold in holds} != {case.id for case in cases}:
        raise Rejected("每个工况至少需要一轮，且轮次必须引用已登记工况")
    WindowIndex(holds)
    tolerance = parse_clock(data["pair_tolerance_s"], "配对允许时差", 0, 100) if "pair_tolerance_s" in data else Fraction(0)
    return Plan(key(data["id"], "计划号"), text(data["label"], "计划名"), span, tuple(refs), tuple(points),
                tuple(cases), tuple(holds), number(data["minimum_pairs"], "最低配对数", 1, 100),
                number(data["residual_limit_um"], "残余位移复核线"), number(data["repeat_limit_um"], "重复差复核线"),
                tolerance)
