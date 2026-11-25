from dataclasses import asdict

from .errors import Rejected
from .retest_survey import build_extended_survey
from .retests import load_retests, retest_exclusions, retest_votes


def evidence(survey, placement, match, positions=None, readings=None, scope="base", retest_id=None):
    reading_ids = set()
    for phase in match["phases"].values():
        for pair in phase["pairs"]:
            reading_ids.update((pair["point_row"], pair["reference_row"]))
        for gap in phase["gaps"]:
            reading_ids.update(gap["point_rows"] + gap["reference_rows"])
    positions = survey.positions if positions is None else positions
    readings = survey.readings if readings is None else readings
    place_rows = [asdict(row) | {"scope": scope, "retest_id": retest_id}
                  for axle in placement["axles"] for row_id in axle["evidence"]
                  for row in [positions.get(row_id)] if row is not None]
    reading_rows = [asdict(readings[row_id]) | {"scope": scope, "retest_id": retest_id}
                    for row_id in sorted(reading_ids) if row_id in readings]
    return dict(response=match, placement=placement, positions=place_rows, readings=reading_rows)


def explain(survey, report, hold, point):
    match = next((row for row in report["responses"] if row["hold"] == hold and row["point"] == point), None)
    if match is None:
        raise Rejected("找不到该轮次和测点组合", 404)
    return evidence(survey, report["placement"][hold], match)


def explain_extended(store, run, survey, report, hold, point):
    """原计划轮或补测轮的证据追溯，使用包含补测行的扩展调查。"""
    with store.transaction() as db:
        records = load_retests(db, run)
        events = retest_votes(db, run)
    extended = build_extended_survey(survey.plan, survey.positions, survey.readings,
                                     records, retest_exclusions(events))
    pool = report["responses"] + report.get("retest_responses", [])
    match = next((row for row in pool if row["hold"] == hold and row["point"] == point), None)
    if match is None:
        raise Rejected("找不到该轮次和测点组合", 404)
    is_retest = hold in report.get("retest_placement", {})
    placement = report["placement"].get(hold) or report["retest_placement"][hold]
    return evidence(extended, placement, match,
                    scope="retest" if is_retest else "base",
                    retest_id=hold if is_retest else None)
