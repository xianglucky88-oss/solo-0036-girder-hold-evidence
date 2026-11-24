from dataclasses import asdict

from .errors import Rejected


def evidence(survey, placement, match):
    reading_ids = set()
    for phase in match["phases"].values():
        for pair in phase["pairs"]:
            reading_ids.update((pair["point_row"], pair["reference_row"]))
        for gap in phase["gaps"]:
            reading_ids.update(gap["point_rows"] + gap["reference_rows"])
    positions = [asdict(survey.positions[row_id]) for axle in placement["axles"] for row_id in axle["evidence"]]
    readings = [asdict(survey.readings[row_id]) for row_id in sorted(reading_ids)]
    return dict(response=match, placement=placement, positions=positions, readings=readings)


def explain(survey, report, hold, point):
    match = next((row for row in report["responses"] if row["hold"] == hold and row["point"] == point), None)
    if match is None:
        raise Rejected("找不到该轮次和测点组合", 404)
    return evidence(survey, report["placement"][hold], match)
