from dataclasses import asdict

from .errors import Rejected


def evidence(survey, placement, match, reasons=None):
    reading_ids = set()
    for phase in match["phases"].values():
        for pair in phase["pairs"]:
            reading_ids.update((pair["point_row"], pair["reference_row"]))
        for gap in phase["gaps"]:
            reading_ids.update(gap["point_rows"] + gap["reference_rows"])
    positions = [asdict(survey.positions[row_id]) for axle in placement["axles"] for row_id in axle["evidence"]]
    readings = [asdict(survey.readings[row_id]) for row_id in sorted(reading_ids)]
    result = dict(response=match, placement=placement, positions=positions, readings=readings)
    if reasons is not None:
        position_ids = {row["id"] for row in positions}
        result["exclusion_reasons"] = {
            "position": {row_id: reasons["position"][row_id] for row_id in reasons["position"]
                         if row_id in position_ids},
            "reading": {row_id: reasons["reading"][row_id] for row_id in reasons["reading"]
                        if row_id in reading_ids},
        }
    return result


def explain(survey, report, hold, point, reasons=None):
    match = next((row for row in report["responses"] if row["hold"] == hold and row["point"] == point), None)
    if match is None:
        raise Rejected("找不到该轮次和测点组合", 404)
    return evidence(survey, report["placement"][hold], match, reasons)
