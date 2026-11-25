from collections import defaultdict
from dataclasses import dataclass

from .windows import WindowIndex


@dataclass(frozen=True)
class Pair:
    tick: int
    point_row: str
    reference_row: str
    adjusted: int


def align(plan, readings, excluded):
    windows = WindowIndex.for_plan(plan)
    channels = defaultdict(lambda: defaultdict(list))
    unassigned = []
    for row in readings.values():
        if row.id in excluded:
            continue
        window = windows.find(row.tick)
        if window is None:
            unassigned.append(row.id)
        else:
            channels[row.channel][row.tick].append(row)
    pairs, gaps = defaultdict(list), defaultdict(list)
    for point in plan.points:
        for tick, samples in sorted(channels[point.id].items()):
            kind, owner, label = windows.find(tick)
            group = (kind, owner, point.id, label)
            refs = channels[point.reference].get(tick, [])
            if len(samples) == len(refs) == 1:
                sample, ref = samples[0], refs[0]
                pairs[group].append(Pair(tick, sample.id, ref.id, point.sign * (sample.value_um - ref.value_um)))
            else:
                reason = "point_ambiguous" if len(samples) > 1 else "reference_ambiguous" if refs else "reference_missing"
                gaps[group].append(dict(tick=tick, reason=reason, point_rows=sorted(row.id for row in samples),
                                        reference_rows=sorted(row.id for row in refs)))
    return pairs, gaps, sorted(unassigned)
