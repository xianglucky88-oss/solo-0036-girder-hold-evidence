from dataclasses import asdict

from .clockmap import format_clock
from .errors import Rejected


def reading_row(row):
    return dict(id=row.id, channel=row.channel, tick=format_clock(row.tick), value_um=row.value_um, line=row.line,
                device=row.device, local_tick=format_clock(row.local_tick), sync_state=row.sync_state)


def evidence(survey, placement, match):
    reading_ids = set()
    for phase in match["phases"].values():
        for pair in phase["pairs"]:
            reading_ids.update((pair["point_row"], pair["reference_row"]))
        for gap in phase["gaps"]:
            reading_ids.update(gap["point_rows"] + gap["reference_rows"])
    positions = [asdict(survey.positions[row_id]) for axle in placement["axles"] for row_id in axle["evidence"]]
    readings = [reading_row(survey.readings[row_id]) for row_id in sorted(reading_ids)]
    devices = sorted({survey.readings[row_id].device for row_id in reading_ids
                      if survey.readings[row_id].device is not None})
    observations = [asdict(entry) | dict(local_tick=format_clock(entry.local_tick),
                                         test_tick=format_clock(entry.test_tick))
                    for device in devices for entry in survey.observations.get(device, ())]
    return dict(response=match, placement=placement, positions=positions, readings=readings,
                sync_observations=observations)


def explain(survey, report, hold, point):
    match = next((row for row in report["responses"] if row["hold"] == hold and row["point"] == point), None)
    if match is None:
        raise Rejected("找不到该轮次和测点组合", 404)
    return evidence(survey, report["placement"][hold], match)
