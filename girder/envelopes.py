from collections import defaultdict
from fractions import Fraction

from .exact import encode


def extremes(valid, selector):
    if not valid:
        return None
    values = [(Fraction(row["loaded_um"]), row) for row in valid]
    edge = selector(value for value, _ in values)
    return dict(value_um=encode(edge), evidence=[dict(hold=row["hold"], point=row["point"], case=row["case"])
                                                 for value, row in values if value == edge])


def make_envelopes(plan, responses):
    stations = {point.id: point.station_mm for point in plan.points}
    sections = defaultdict(list)
    for row in responses:
        sections[stations[row["point"]]].append(row)
    result = []
    for station, rows in sorted(sections.items()):
        valid = [row for row in rows if row["state"] == "valid"]
        result.append(dict(station_mm=station, complete=len(valid) == len(rows),
                           missing=[dict(hold=row["hold"], point=row["point"]) for row in rows if row["state"] != "valid"],
                           low=extremes(valid, min), high=extremes(valid, max)))
    return result
