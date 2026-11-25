from fractions import Fraction

from .alignment import align
from .deflection import make_responses
from .exact import encode
from .placement import assess_placement
from .repeats import summarize_repeats
from .retest_survey import build_extended_survey
from .substitution import analyze

CONTRACT = "hold-reduction-v2"


def _index(rows, hold):
    return {row["point"]: row for row in rows if row["hold"] == hold}


def reduce_with_retests(survey, plan, records, base_exclusions, retest_exclusions, confirmed):
    """在原计划归约之上加入补测登记与替补履约。

    1. 原计划轮照常归约，缺证原轮构成待履行义务；
    2. 补测轮单独归约，整轮驻位有效且所有测点三相合格才具备资格；
    3. 同工况构造资格图，求最大匹配及强制归属，已确认归属先固定；
    4. 有效响应按已落实义务归约，未采用补测不进入重复差与包络。
    """
    base_placement = assess_placement(plan, survey.positions, base_exclusions.get("position", set()))
    base_pairs, base_gaps, unassigned = align(plan, survey.readings, base_exclusions.get("reading", set()))
    base_responses = make_responses(plan, base_placement, base_pairs, base_gaps)

    extended = build_extended_survey(plan, survey.positions, survey.readings, records, retest_exclusions)
    ext_placement = assess_placement(extended.plan, extended.positions, base_exclusions.get("position", set()))
    ext_pairs, ext_gaps, _ = align(extended.plan, extended.readings, base_exclusions.get("reading", set()))
    ext_responses = make_responses(extended.plan, ext_placement, ext_pairs, ext_gaps)

    original_ids = [hold.id for hold in plan.holds]
    original_set = set(original_ids)
    retest_ids = [hold.id for hold in extended.plan.holds if hold.id not in original_set]
    case_of = {hold.id: hold.case for hold in plan.holds}
    case_of_extended = {hold.id: hold.case for hold in extended.plan.holds}

    def hold_valid(hold_id):
        return ext_placement[hold_id]["valid"] and all(
            row["state"] == "valid" for row in ext_responses if row["hold"] == hold_id)

    obligation_ids = [hold_id for hold_id in original_ids if not hold_valid(hold_id)]
    obligations = [(hold_id, case_of[hold_id]) for hold_id in obligation_ids]
    qualified_cases = {}
    for hold_id in retest_ids:
        if hold_valid(hold_id):
            qualified_cases.setdefault(case_of_extended[hold_id], []).append(hold_id)
    edges = {hold_id: sorted(qualified_cases.get(case, [])) for hold_id, case in obligations}

    confirmed_map = {item["hold"]: item["retest_id"] for item in confirmed}
    solution = analyze(edges, confirmed_map)

    # 已落实义务：合格原轮自行履约，缺证原轮由已确认且仍合格的补测轮替补。
    qualified_retests = {hold_id for hold_id in retest_ids if hold_valid(hold_id)}
    fulfilled = {}
    broken_confirmations = []
    for hold_id in original_ids:
        if hold_id not in obligation_ids:
            fulfilled[hold_id] = dict(origin=hold_id, kind="self")
        elif hold_id in confirmed_map:
            origin = confirmed_map[hold_id]
            if origin in qualified_retests:
                fulfilled[hold_id] = dict(origin=origin, kind="retest")
            else:
                broken_confirmations.append(hold_id)

    effective = []
    for hold_id in original_ids:
        status = fulfilled.get(hold_id)
        if status is None:
            continue
        for row in _index(ext_responses, status["origin"]).values():
            effective.append(dict(row, hold=hold_id, origin=status["origin"],
                                  fulfillment=status["kind"]))

    repeats = summarize_repeats(plan, effective)
    envelopes = _envelopes_with_origin(plan, effective)
    # 仍缺义务：当前匹配未覆盖的义务，加上确认后补测又失效的义务。
    outstanding = sorted(set(solution["missing"]) | set(broken_confirmations))
    ready = not outstanding and all(hold_id in fulfilled for hold_id in original_ids)

    retest_summary = [dict(retest_id=hold_id, case=case_of_extended[hold_id],
                           qualified=hold_valid(hold_id),
                           adopted=hold_id in confirmed_map.values())
                      for hold_id in retest_ids]
    return dict(
        contract=CONTRACT,
        ready=ready,
        placement=base_placement,
        retest_placement={hold_id: ext_placement[hold_id] for hold_id in retest_ids},
        responses=base_responses,
        retest_responses=[row for row in ext_responses if row["hold"] in set(retest_ids)],
        effective_responses=effective,
        repeats=repeats,
        envelopes=envelopes,
        unassigned_readings=unassigned,
        obligations=dict(
            missing=[dict(hold=hold_id, case=case_of[hold_id]) for hold_id in obligation_ids],
            eligible_edges=edges,
            max_fill=solution["max_fill"],
            forced=solution["forced"],
            confirmed=[dict(hold=item["hold"], retest_id=item["retest_id"], reason=item["reason"],
                            revision=item["revision"],
                            active=item["retest_id"] in qualified_retests) for item in confirmed],
            outstanding=outstanding,
            broken_confirmations=broken_confirmations,
        ),
        retests=retest_summary,
    )


def _envelopes_with_origin(plan, responses):
    stations = {point.id: point.station_mm for point in plan.points}
    sections = {}
    for row in responses:
        sections.setdefault(stations[row["point"]], []).append(row)
    result = []
    for station in sorted(sections):
        rows = sections[station]
        valid = [row for row in rows if row["state"] == "valid"]
        result.append(dict(
            station_mm=station,
            complete=len(valid) == len(plan.holds),
            missing=[dict(hold=row["hold"], point=row["point"]) for row in rows if row["state"] != "valid"],
            low=_extreme(valid, min),
            high=_extreme(valid, max),
        ))
    return result


def _extreme(valid, selector):
    if not valid:
        return None
    values = [(Fraction(row["loaded_um"]), row) for row in valid]
    edge = selector(value for value, _ in values)
    return dict(value_um=encode(edge),
                evidence=[dict(hold=row["hold"], point=row["point"], origin=row.get("origin", row["hold"]),
                               fulfillment=row.get("fulfillment", "self"))
                          for value, row in values if value == edge])
