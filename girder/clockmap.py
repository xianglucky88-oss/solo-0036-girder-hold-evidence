"""采集机本机时刻与试验时刻的同步观测和匀速钟差换算。"""

import re
from bisect import bisect_left
from dataclasses import dataclass
from fractions import Fraction

from .errors import Rejected
from .validation import key

CLOCK = re.compile(r"-?(?:[0-9]+(?:\.[0-9]{1,6})?|\.[0-9]{1,6})\Z")
CLOCK_LIMIT = 10**6


def parse_clock(value, label, low=-CLOCK_LIMIT, high=CLOCK_LIMIT):
    if not isinstance(value, str) or not CLOCK.fullmatch(value):
        raise Rejected(f"{label}须为不超过 6 位小数的秒数")
    clock = Fraction(value)
    if not low <= clock <= high:
        raise Rejected(f"{label}超出允许范围")
    return clock


def format_clock(value):
    """把精确时刻格式化为至多 6 位小数的字符串，第 7 位小数按远离零方向进位。"""
    if value is None:
        return None
    if value.denominator == 1:
        return str(value.numerator)
    sign = "-" if value < 0 else ""
    scaled = abs(value) * 1_000_000
    units, remainder = divmod(scaled.numerator, scaled.denominator)
    if remainder * 2 >= scaled.denominator:
        units += 1
    text = str(units).zfill(7)
    whole, fraction = text[:-6], text[-6:].rstrip("0")
    return f"{sign}{whole}" if not fraction else f"{sign}{whole}.{fraction}"


@dataclass(frozen=True)
class Observation:
    id: str
    device: str
    local_tick: Fraction
    test_tick: Fraction
    line: int


def parse_sync(source):
    from .csv_input import rows

    result = {}
    identities = set()
    for line, (identity, device, local, test) in rows(
            source, "id device local_tick test_tick", "同步观测表", 4000):
        key(identity, "同步观测行号")
        if identity in identities:
            raise Rejected(f"同步观测表第 {line} 行编号重复")
        identities.add(identity)
        observation = Observation(identity, key(device, "采集机号"),
                                  parse_clock(local, "本机时刻"), parse_clock(test, "试验时刻"), line)
        result.setdefault(observation.device, []).append(observation)
    for device, observations in result.items():
        if len(observations) < 2:
            raise Rejected(f"采集机 {device} 至少需要两条同步观测")
        for previous, current in zip(observations, observations[1:]):
            if current.local_tick <= previous.local_tick or current.test_tick <= previous.test_tick:
                raise Rejected(f"采集机 {device} 的同步观测存在矛盾或倒退，整包退件")
    return result


class ClockMap:
    """相邻同步观测之间按匀速钟差换算，观测端点有效，覆盖范围外返回 None。"""

    def __init__(self, observations):
        self.observations = sorted(observations, key=lambda item: item.local_tick)
        self.local_ticks = [item.local_tick for item in self.observations]

    def to_test(self, local_tick):
        index = bisect_left(self.local_ticks, local_tick)
        if index < len(self.observations) and self.observations[index].local_tick == local_tick:
            return self.observations[index].test_tick
        if index == 0 or index == len(self.observations):
            return None
        left, right = self.observations[index - 1], self.observations[index]
        span = right.local_tick - left.local_tick
        return left.test_tick + (local_tick - left.local_tick) * (right.test_tick - left.test_tick) / span


def build_maps(observations):
    return {device: ClockMap(entries) for device, entries in observations.items()}
