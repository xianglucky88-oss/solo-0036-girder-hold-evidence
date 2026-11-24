from bisect import bisect_right
from dataclasses import dataclass

from .errors import Rejected
from .validation import fields, key, number

PHASES = ("before", "loaded", "after")


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
    def __init__(self, holds):
        self.entries = sorted((start, end, hold.id, phase) for hold in holds
                              for phase, (start, end) in zip(PHASES, hold.windows))
        if any(left[1] > right[0] for left, right in zip(self.entries, self.entries[1:])):
            raise Rejected("各轮次的采样窗口不得重叠")
        self.starts = [entry[0] for entry in self.entries]

    def find(self, tick):
        index = bisect_right(self.starts, tick) - 1
        if index >= 0:
            _, end, hold, phase = self.entries[index]
            if tick < end:
                return hold, phase
        return None
