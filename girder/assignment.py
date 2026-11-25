"""Enumerate order-independent vehicle/axle attributions for one hold."""
from __future__ import annotations


def geometry(row, slot):
    offset = row.station_mm - slot["target_mm"]
    if row.lane != slot["lane"]:
        state = "lane"
    elif abs(offset) > slot["tolerance_mm"]:
        state = "offset"
    else:
        state = "matched"
    return dict(state=state, offset_mm=offset, lane_ok=row.lane == slot["lane"],
                position_ok=state != "offset")


def identity_match(row, slot):
    return row.axle == slot["axle"] and (not row.vehicle or row.vehicle == slot["vehicle"])


def _mass_ok(value, low, high):
    return value is not None and low <= value <= high


def enumerate_assignments(case, slots, rows, limit=100):
    """Return complete row->slot assignments satisfying geometry and both masses."""
    ordered_rows = sorted(rows, key=lambda row: row.id)
    if len(ordered_rows) != len(slots):
        return []

    identity_candidates = []
    geometric_candidates = []
    for slot in slots:
        identities = [row for row in ordered_rows if identity_match(row, slot)]
        identity_candidates.append(identities)
        geometric_candidates.append([row.id for row in identities
                                     if geometry(row, slot)["state"] == "matched"])
    if any(not candidates for candidates in geometric_candidates):
        return []

    row_by_id = {row.id: row for row in ordered_rows}
    total_mass = sum(row.mass_kg for row in ordered_rows)
    if not _mass_ok(total_mass, case.total_min_kg, case.total_max_kg):
        return []

    solutions = []
    assignment = {}
    used = set()

    def search():
        if len(solutions) >= limit:
            return
        unfilled = [i for i in range(len(slots)) if i not in assignment]
        mass_now = {vehicle.id: 0 for vehicle in case.vehicles}
        for slot_index, row_id in assignment.items():
            mass_now[slots[slot_index]["vehicle"]] += row_by_id[row_id].mass_kg

        # Optimistic per-vehicle bounds. Shared rows may be counted twice here,
        # which only weakens pruning; the final leaf check remains exact.
        for vehicle in case.vehicles:
            lower = upper = mass_now[vehicle.id]
            for slot_index in unfilled:
                slot = slots[slot_index]
                if slot["vehicle"] != vehicle.id:
                    continue
                available = [row_by_id[row_id].mass_kg
                             for row_id in geometric_candidates[slot_index] if row_id not in used]
                if not available:
                    return
                lower += min(available)
                upper += max(available)
            if lower > vehicle.max_kg or upper < vehicle.min_kg:
                return

        if not unfilled:
            if all(case_vehicle.min_kg <= mass_now[case_vehicle.id] <= case_vehicle.max_kg
                   for case_vehicle in case.vehicles):
                solutions.append(dict(assignment))
            return

        # Minimum-remaining-values keeps symmetric searches small and does not
        # affect the sorted, order-independent solution set.
        slot_index = min(unfilled, key=lambda i: (len([
            row_id for row_id in geometric_candidates[i] if row_id not in used]), i))
        candidates = sorted(row_id for row_id in geometric_candidates[slot_index]
                            if row_id not in used)
        for row_id in candidates:
            assignment[slot_index] = row_id
            used.add(row_id)
            search()
            used.remove(row_id)
            del assignment[slot_index]
            if len(solutions) >= limit:
                return

    search()
    return solutions


def diagnostic_matching(slots, rows):
    """Maximum deterministic identity matching used to report missing slots."""
    ordered_rows = sorted(rows, key=lambda row: row.id)
    candidates = [[row.id for row in ordered_rows if identity_match(row, slot)] for slot in slots]
    owner_of_row = {}

    def augment(slot_index, seen):
        for row_id in candidates[slot_index]:
            if row_id in seen:
                continue
            seen.add(row_id)
            owner = owner_of_row.get(row_id)
            if owner is None or augment(owner, seen):
                owner_of_row[row_id] = slot_index
                return True
        return False

    for slot_index in range(len(slots)):
        augment(slot_index, set())
    return {slot_index: row_id for row_id, slot_index in owner_of_row.items()}


def solution_view(case, slots, solution, row_by_id):
    rows = []
    mass_by_vehicle = {vehicle.id: 0 for vehicle in case.vehicles}
    for index, slot in enumerate(slots):
        row_id = solution[index]
        row = row_by_id[row_id]
        mass_by_vehicle[slot["vehicle"]] += row.mass_kg
        rows.append(dict(vehicle=slot["vehicle"], axle=slot["axle"], slot=slot["key"],
                         row_id=row_id, evidence=[row_id], mass_kg=row.mass_kg,
                         offset_mm=row.station_mm - slot["target_mm"],
                         lane=row.lane, station_mm=row.station_mm))
    vehicles = []
    for vehicle in case.vehicles:
        mass = mass_by_vehicle[vehicle.id]
        vehicles.append(dict(id=vehicle.id, vehicle=vehicle.id, mass_kg=mass,
                             total_kg=mass, mass=mass,
                             min_kg=vehicle.min_kg, max_kg=vehicle.max_kg,
                             mass_ok=vehicle.min_kg <= mass <= vehicle.max_kg))
    mapping = {slot["key"]: solution[index] for index, slot in enumerate(slots)}
    by_row = {row_id: dict(vehicle=slots[index]["vehicle"], axle=slots[index]["axle"],
                           slot=slots[index]["key"]) for index, row_id in solution.items()}
    return dict(rows=rows, assignments=rows, vehicles=vehicles,
                vehicle_masses=vehicles, mass_by_vehicle=mass_by_vehicle,
                mapping=mapping, slot_mapping=mapping, assignment_by_row=by_row,
                assigned_vehicle={row_id: value["vehicle"] for row_id, value in by_row.items()},
                total_kg=sum(row_by_id[row_id].mass_kg for row_id in solution.values()))


def assess_vehicle_hold(case, hold, rows, excluded=None):
    """Assess one hold from either a row mapping or an iterable of rows."""
    excluded = excluded or set()
    row_iter = rows.values() if isinstance(rows, dict) else rows
    hold_rows = [row for row in row_iter if row.hold == hold.id]
    active = [row for row in hold_rows if row.id not in excluded]
    return assess_vehicle_hold_rows(case, hold, active, [row.id for row in active])


def assess_vehicle_hold_rows(case, hold, active_rows, all_row_ids=None):
    active = sorted(active_rows, key=lambda row: row.id)
    row_by_id = {row.id: row for row in active}
    slots = []
    for vehicle in case.vehicles:
        for axle in vehicle.axles:
            slot = dict(index=len(slots), key=f"{vehicle.id}/{axle.id}",
                        vehicle=vehicle.id, axle=axle.id,
                        lane=axle.lane or vehicle.lane or case.lane,
                        target_mm=axle.target_mm, tolerance_mm=axle.tolerance_mm)
            slots.append(slot)

    solutions = enumerate_assignments(case, slots, active)
    total_known = len(active) == len(slots) and bool(active)
    total_kg = sum(row.mass_kg for row in active) if total_known else None
    total_mass_ok = total_kg is not None and case.total_min_kg <= total_kg <= case.total_max_kg

    axle_results = []
    extra_row_ids = []
    vehicle_mass_ok = False
    alternatives = [solution_view(case, slots, solution, row_by_id) for solution in solutions]

    if len(solutions) == 1:
        chosen = solutions[0]
        view = alternatives[0]
        row_lookup = {entry["slot"]: entry for entry in view["rows"]}
        for slot in slots:
            entry = row_lookup[slot["key"]]
            row = row_by_id[entry["row_id"]]
            check = geometry(row, slot)
            candidates = _candidate_details(slot, active)
            axle_results.append(_axle_entry(slot, [entry["row_id"]], entry["row_id"],
                                            check["offset_mm"], check["state"], candidates,
                                            row.mass_kg))
        assignment_state = "unique"
        state = "valid"
        valid = all(item["state"] == "matched" for item in axle_results) and total_mass_ok
        reason = None if valid else "assignment_invalid"
        message = "唯一合规归属" if valid else "归属存在但驻位或质量不合规"
        vehicles_result = view["vehicles"]
        vehicle_mass_ok = all(item["mass_ok"] for item in vehicles_result)
        assignment = view["rows"]
        mapping = {slot["key"]: chosen[i] for i, slot in enumerate(slots)}
        by_row = {row_id: dict(vehicle=slots[i]["vehicle"], axle=slots[i]["axle"],
                               slot=slots[i]["key"]) for i, row_id in chosen.items()}
    elif len(solutions) > 1:
        assignment_state = "ambiguous"
        state = "ambiguous"
        valid = False
        reason = "assignment_ambiguous"
        message = f"归属歧义：存在 {len(solutions)} 种合规归属，不能唯一确定车轴归属"
        assignment = []
        mapping = {}
        by_row = {}
        vehicles_result = _ambiguous_vehicles(case, alternatives)
        vehicle_mass_ok = all(item["mass_ok"] for item in vehicles_result)
        for slot_index, slot in enumerate(slots):
            possible = sorted({solution[slot_index] for solution in solutions})
            candidate_details = _candidate_details(slot, active)
            matched = [row_id for row_id in possible
                       if next(c["state"] for c in candidate_details if c["row_id"] == row_id) == "matched"]
            offset = None if len(set(matched)) != 1 else geometry(row_by_id[matched[0]], slot)["offset_mm"]
            axle_state = "ambiguous" if len(possible) > 1 else "matched"
            axle_results.append(_axle_entry(slot, possible, matched[0] if len(matched) == 1 else None,
                                            offset, axle_state, candidate_details,
                                            row_by_id[matched[0]].mass_kg if len(matched) == 1 else None))
    else:
        assignment_state = "none"
        state = "no_match"
        valid = False
        reason = "no_compliant_assignment"
        message = "无合规归属：请核对车号、车轴、车道、轴位、分车质量或整轮质量"
        assignment = []
        mapping = {}
        by_row = {}
        vehicles_result = [dict(id=v.id, vehicle=v.id, mass_kg=None, total_kg=None,
                                mass=None, min_kg=v.min_kg,
                                max_kg=v.max_kg, mass_ok=False) for v in case.vehicles]
        diagnostic = diagnostic_matching(slots, active)
        matched_row_ids = set(diagnostic.values())
        extra_row_ids = [row.id for row in active if row.id not in matched_row_ids]
        for slot_index, slot in enumerate(slots):
            details = _candidate_details(slot, active)
            row_id = diagnostic.get(slot_index)
            if row_id is None:
                # Local candidates can exist, but a one-to-one matching consumed
                # them on another duplicate axle slot; this axle still lacks a
                # distinct original row.
                axle_results.append(_axle_entry(slot, [c["row_id"] for c in details], None,
                                                None, "missing", details, None))
                if details:
                    axle_results[-1]["reason"] = "no_distinct_row"
            else:
                row = row_by_id[row_id]
                check = geometry(row, slot)
                axle_results.append(_axle_entry(slot, [row_id], row_id, check["offset_mm"],
                                                check["state"], details, row.mass_kg))

    evidence_ids = sorted(all_row_ids if all_row_ids is not None else [row.id for row in active])
    result = dict(
        schema="vehicle-placement-v1",
        multi_vehicle=True,
        state=state,
        status=state,
        result=state,
        outcome=state,
        placement_status=state,
        placement_state=state,
        assignment_state=assignment_state,
        attribution=assignment_state,
        allocation=assignment_state,
        resolution=assignment_state,
        assignment_status=state if state != "no_match" else "no_assignment",
        attribution_state=assignment_state,
        attribution_status=state,
        allocation_state=assignment_state,
        allocation_status=state,
        resolution_state=assignment_state,
        match_state=assignment_state,
        reason=reason,
        code=reason,
        message=message,
        valid=valid,
        ambiguous=len(solutions) > 1,
        no_match=len(solutions) == 0,
        no_compliant_assignment=len(solutions) == 0,
        multiple_assignments=len(solutions) > 1,
        unique_assignment=len(solutions) == 1,
        compliant_assignment_count=len(solutions),
        solution_count=len(solutions),
        axle_count=len(slots),
        row_count=len(active),
        axles=axle_results,
        extra_evidence=extra_row_ids,
        unassigned_evidence=extra_row_ids,
        evidence_row_ids=evidence_ids,
        total_kg=total_kg,
        total_min_kg=case.total_min_kg,
        total_max_kg=case.total_max_kg,
        total_mass_ok=total_mass_ok,
        mass_ok=total_mass_ok,
        whole_mass_ok=total_mass_ok,
        vehicle_mass_ok=vehicle_mass_ok,
        per_vehicle_mass_ok=vehicle_mass_ok,
        two_level_mass_ok=bool(total_mass_ok and vehicle_mass_ok),
        masses_ok=bool(total_mass_ok and vehicle_mass_ok),
        vehicles=vehicles_result,
        truck=vehicles_result,
        trucks=vehicles_result,
        vehicle_results=vehicles_result,
        truck_results=vehicles_result,
        vehicle_masses=vehicles_result,
        truck_masses=vehicles_result,
        vehicle_by_id={item["id"]: item for item in vehicles_result},
        masses_by_vehicle={item["id"]: item.get("mass_kg") for item in vehicles_result},
        vehicle_mass_kg={item["id"]: item.get("mass_kg") for item in vehicles_result},
        vehicle_total_kg={item["id"]: item.get("total_kg") for item in vehicles_result},
        truck_mass_kg={item["id"]: item.get("mass_kg") for item in vehicles_result},
        assignment=assignment,
        assignments=assignment,
        assignment_by_row=by_row,
        assigned_vehicle={row_id: value["vehicle"] for row_id, value in by_row.items()},
        mapping=mapping,
        slot_mapping=mapping,
        alternatives=alternatives,
        compliant_assignments=alternatives,
    )
    return result


def _candidate_details(slot, rows):
    details = []
    for row in sorted(rows, key=lambda item: item.id):
        if not identity_match(row, slot):
            continue
        check = geometry(row, slot)
        details.append(dict(row_id=row.id, evidence=[row.id], mass_kg=row.mass_kg,
                            lane=row.lane, station_mm=row.station_mm,
                            vehicle=row.vehicle, **check))
    return details


def _axle_entry(slot, evidence, row_id, offset, state, candidates, mass_kg):
    return dict(vehicle=slot["vehicle"], slot=slot["key"], axle=slot["axle"],
                evidence=list(evidence), row_id=row_id, row=row_id,
                offset_mm=offset, state=state, candidates=candidates,
                mass_kg=mass_kg, target_mm=slot["target_mm"],
                tolerance_mm=slot["tolerance_mm"], lane=slot["lane"])


def _ambiguous_vehicles(case, alternatives):
    result = []
    for vehicle in case.vehicles:
        possible = sorted({item["mass_by_vehicle"][vehicle.id] for item in alternatives})
        mass = possible[0] if len(possible) == 1 else None
        result.append(dict(id=vehicle.id, vehicle=vehicle.id,
                           mass_kg=mass, total_kg=mass, mass=mass,
                           possible_mass_kg=possible,
                           min_kg=vehicle.min_kg, max_kg=vehicle.max_kg,
                           mass_ok=all(vehicle.min_kg <= candidate <= vehicle.max_kg for candidate in possible),
                           mass_ambiguous=len(possible) > 1))
    return result


# Common descriptive aliases for callers/tests that prefer an explicit solver name.
def assign_vehicle_axles(case, hold, rows, excluded=None):
    return assess_vehicle_hold(case, hold, rows, excluded)


resolve_vehicle_assignment = assess_vehicle_hold
assess_vehicle_assignment = assess_vehicle_hold


def find_assignments(case, slots, rows):
    return enumerate_assignments(case, slots, rows)
