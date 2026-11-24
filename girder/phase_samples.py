from .exact import encode, median
from .windows import PHASES


def summarize_phases(pairs, gaps, hold, point, minimum):
    summaries, values = {}, {}
    for phase in PHASES:
        key = (hold, point, phase)
        members = pairs.get(key, ())
        value = median(pair.adjusted for pair in members) if len(members) >= minimum else None
        values[phase] = value
        summaries[phase] = dict(median_um=encode(value), pair_count=len(members),
                                pairs=[dict(tick=pair.tick, point_row=pair.point_row, reference_row=pair.reference_row,
                                            adjusted_um=pair.adjusted) for pair in members], gaps=gaps.get(key, []))
    return summaries, values
