from dataclasses import dataclass

from .csv_input import integer, rows
from .errors import Rejected
from .validation import key


@dataclass(frozen=True)
class Reading:
    id: str
    channel: str
    tick: int
    value_um: int
    line: int


def parse_readings(source, plan):
    channels = set(plan.references) | {point.id for point in plan.points}
    result = {}
    for line, (identity, channel, tick, value) in rows(source, "id channel tick value_um", "采样表", 16000):
        key(identity, "采样行号")
        if identity in result or channel not in channels:
            raise Rejected(f"采样表第 {line} 行编号重复或通道未登记")
        result[identity] = Reading(identity, channel, integer(tick, "采样时刻"),
                                   integer(value, "位移", -10**8), line)
    return result
