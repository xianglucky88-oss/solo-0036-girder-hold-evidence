from .exact import encode, median
from .windows import PHASES


def summarize_window(pairs, gaps, kind, owner, point, label, minimum):
    """Return evidence for one window and the exact median, or None when coverage is short."""
    key = (kind, owner, point, label)
    members = pairs.get(key, ())
    value = median(pair.adjusted for pair in members) if len(members) >= minimum else None
    summary = dict(median_um=encode(value), pair_count=len(members),
                   pairs=[dict(tick=pair.tick, point_row=pair.point_row, reference_row=pair.reference_row,
                               adjusted_um=pair.adjusted) for pair in members],
                   gaps=gaps.get(key, []))
    return summary, value


def summarize_phases(pairs, gaps, kind, hold, point, minimum):
    summaries, values = {}, {}
    for phase in PHASES:
        summaries[phase], values[phase] = summarize_window(pairs, gaps, kind, hold, point, phase, minimum)
    return summaries, values
