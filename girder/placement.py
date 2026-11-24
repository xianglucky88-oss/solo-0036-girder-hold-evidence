from collections import defaultdict


def assess_placement(plan, rows, excluded):
    by_axle = defaultdict(list)
    for row in rows.values():
        if row.id not in excluded:
            by_axle[row.hold, row.axle].append(row)
    cases = {case.id: case for case in plan.cases}
    result = {}
    for hold in plan.holds:
        case = cases[hold.case]
        axles = []
        mass = 0
        complete = True
        for axle in case.axles:
            candidates = sorted(by_axle[hold.id, axle.id], key=lambda row: row.id)
            evidence = [row.id for row in candidates]
            if len(candidates) != 1:
                complete = False
                axles.append(dict(axle=axle.id, evidence=evidence, offset_mm=None,
                                  state="ambiguous" if candidates else "missing"))
                continue
            row = candidates[0]
            offset = row.station_mm - axle.target_mm
            state = "lane" if row.lane != case.lane else "offset" if abs(offset) > axle.tolerance_mm else "matched"
            axles.append(dict(axle=axle.id, evidence=evidence, offset_mm=offset, state=state))
            mass += row.mass_kg
        total = mass if complete else None
        mass_ok = complete and abs(mass - case.target_kg) <= case.tolerance_kg
        result[hold.id] = dict(axles=axles, total_kg=total, mass_ok=mass_ok,
                               valid=mass_ok and all(axle["state"] == "matched" for axle in axles))
    return result
