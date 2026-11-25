from bisect import bisect_right
from dataclasses import dataclass

from .errors import Rejected
from .validation import fields, key, number

PHASES = ("before", "loaded", "after")
FIRST_EMPTY = "first_empty"
FINAL_EMPTY = "final_empty"


@dataclass(frozen=True)
class Hold:
    id: str
    case: str
    windows: tuple[tuple[int, int], ...]


def parse_hold(item):
    fields(item, "id case before loaded after", "轮次")
    windows = []
    for phase in PHASES:
        pair = item[phase]
        if not isinstance(pair, list) or len(pair) != 2:
            raise Rejected("时间窗须给出两个整秒端点")
        start, end = [number(t, "时间窗端点") for t in pair]
        if start >= end or windows and windows[-1][1] > start:
            raise Rejected("空载、驻载、撤载窗口必须按顺序且互不重叠")
        windows.append((start, end))
    return Hold(key(item["id"], "轮次号"), key(item["case"], "工况号"), tuple(windows))


class WindowIndex:
    """Half-open window index shared by regular holds and the graded process."""

    def __init__(self, entries):
        self.entries = sorted(entries)
        if any(left[1] > right[0] for left, right in zip(self.entries, self.entries[1:])):
            raise Rejected("各轮次的采样窗口不得重叠")
        self.starts = [entry[0] for entry in self.entries]

    @staticmethod
    def entries_for(holds, graded=None):
        entries = []
        for hold in holds:
            for phase, (start, end) in zip(PHASES, hold.windows):
                entries.append((start, end, "hold", hold.id, phase))
        if graded is not None:
            start, end = graded.first_empty
            entries.append((start, end, "graded", graded.id, FIRST_EMPTY))
            for step in graded.steps:
                start, end = step.window
                entries.append((start, end, "graded", graded.id, step.id))
            start, end = graded.final_empty
            entries.append((start, end, "graded", graded.id, FINAL_EMPTY))
        return entries

    @classmethod
    def for_plan(cls, plan):
        return cls(cls.entries_for(plan.holds, plan.graded))

    def find(self, tick):
        """Return (kind, owner, phase) for a tick inside a registered window."""
        index = bisect_right(self.starts, tick) - 1
        if index >= 0:
            _, end, kind, owner, label = self.entries[index]
            if tick < end:
                return kind, owner, label
        return None
