from collections import defaultdict


def _assess_group(owner, lane, target_kg, tolerance_kg, axles, by_axle):
    assessed, mass, complete = [], 0, True
    for axle in axles:
        candidates = sorted(by_axle[owner, axle.id], key=lambda row: row.id)
        evidence = [row.id for row in candidates]
        if len(candidates) != 1:
            complete = False
            assessed.append(dict(axle=axle.id, evidence=evidence, offset_mm=None,
                                 state="ambiguous" if candidates else "missing"))
            continue
        row = candidates[0]
        offset = row.station_mm - axle.target_mm
        state = "lane" if row.lane != lane else "offset" if abs(offset) > axle.tolerance_mm else "matched"
        assessed.append(dict(axle=axle.id, evidence=evidence, offset_mm=offset, state=state))
        mass += row.mass_kg
    total = mass if complete else None
    mass_ok = complete and abs(mass - target_kg) <= tolerance_kg
    return dict(axles=assessed, total_kg=total, mass_ok=mass_ok,
                valid=mass_ok and all(axle["state"] == "matched" for axle in assessed))


def index_positions(rows, excluded):
    by_axle = defaultdict(list)
    for row in rows.values():
        if row.id not in excluded:
            by_axle[row.hold, row.axle].append(row)
    return by_axle


def assess_placement(plan, rows, excluded):
    by_axle = index_positions(rows, excluded)
    cases = {case.id: case for case in plan.cases}
    result = {}
    for hold in plan.holds:
        case = cases[hold.case]
        result[hold.id] = _assess_group(hold.id, case.lane, case.target_kg, case.tolerance_kg, case.axles, by_axle)
    return result


def assess_steps(plan, rows, excluded):
    if plan.graded is None:
        return {}
    by_axle = index_positions(rows, excluded)
    levels = {level.id: level for level in plan.graded.levels}
    result = {}
    for step in plan.graded.steps:
        level = levels[step.level]
        result[step.id] = _assess_group(step.id, level.lane, level.target_kg, level.tolerance_kg, level.axles, by_axle)
    return result
