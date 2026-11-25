from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction

from .clockmap import format_clock
from .windows import WindowIndex


@dataclass(frozen=True)
class Pair:
    tick: Fraction
    point_row: str
    reference_row: str
    adjusted: int


def align(plan, readings, excluded):
    windows = WindowIndex(plan.holds)
    tolerance = plan.pair_tolerance_s
    channels = defaultdict(list)
    unassigned = []
    outside_reasons = {}
    for row in readings.values():
        if row.id in excluded:
            continue
        if row.sync_state == "no_sync_evidence":
            unassigned.append(row.id)
            outside_reasons[row.id] = "no_sync_evidence"
            continue
        window = windows.find(row.tick)
        if window is None:
            unassigned.append(row.id)
            outside_reasons[row.id] = "outside_window"
        else:
            hold, phase = window
            channels[hold, phase, row.channel].append(row)

    pairs, gaps = defaultdict(list), defaultdict(list)
    for point in plan.points:
        for hold in plan.holds:
            for phase in ("before", "loaded", "after"):
                group = (hold.id, point.id, phase)
                samples = sorted(channels.get((hold.id, phase, point.id), ()), key=lambda row: row.id)
                references = sorted(channels.get((hold.id, phase, point.reference), ()), key=lambda row: row.id)
                candidate_refs = {sample.id: [ref for ref in references
                                              if abs(sample.tick - ref.tick) <= tolerance] for sample in samples}
                candidate_points = {ref.id: [sample for sample in samples
                                             if abs(sample.tick - ref.tick) <= tolerance] for ref in references}
                for sample in samples:
                    refs = candidate_refs[sample.id]
                    if not refs:
                        reason = "reference_missing"
                    elif len(refs) > 1:
                        reason = "reference_ambiguous"
                    elif len(candidate_points[refs[0].id]) != 1:
                        reason = "point_ambiguous"
                    else:
                        ref = refs[0]
                        pairs[group].append(Pair(sample.tick, sample.id, ref.id,
                                                 point.sign * (sample.value_um - ref.value_um)))
                        continue
                    gaps[group].append(dict(tick=format_clock(sample.tick), reason=reason,
                                            point_rows=[sample.id],
                                            reference_rows=sorted(ref.id for ref in refs)))
    for group in pairs.values():
        group.sort(key=lambda pair: (pair.tick, pair.point_row))
    return pairs, gaps, sorted(unassigned), outside_reasons
