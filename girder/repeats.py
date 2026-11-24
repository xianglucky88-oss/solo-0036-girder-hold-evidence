from collections import defaultdict
from fractions import Fraction

from .exact import encode


def summarize_repeats(plan, responses):
    groups = defaultdict(list)
    for row in responses:
        groups[row["case"], row["point"]].append(row)
    result = []
    for (case, point), rows in groups.items():
        usable = [Fraction(row["loaded_um"]) for row in rows if row["state"] == "valid"]
        state = "incomplete" if len(usable) < len(rows) else "single" if len(usable) == 1 else "comparable"
        spread = max(usable) - min(usable) if state == "comparable" else None
        result.append(dict(case=case, point=point, holds=[row["hold"] for row in rows],
                           missing=[row["hold"] for row in rows if row["state"] != "valid"], state=state,
                           spread_um=encode(spread), review=None if spread is None else spread > plan.repeat_limit_um))
    return result
