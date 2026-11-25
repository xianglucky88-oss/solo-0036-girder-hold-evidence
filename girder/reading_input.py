from dataclasses import dataclass
from fractions import Fraction

from .clockmap import build_maps, parse_clock
from .csv_input import header_of, integer, rows
from .errors import Rejected
from .validation import key

LEGACY_HEADER = "id channel tick value_um"
DEVICE_HEADER = "id channel device local_tick value_um"


@dataclass(frozen=True)
class Reading:
    id: str
    channel: str
    tick: Fraction
    value_um: int
    line: int
    device: str | None = None
    local_tick: Fraction | None = None
    sync_state: str = "shared_clock"


def parse_readings(source, plan, observations=None):
    channels = set(plan.references) | {point.id for point in plan.points}
    header, _, _ = header_of(source, "采样表")
    if header == LEGACY_HEADER.split():
        return _parse_legacy(source, channels), "shared_clock"
    if header == DEVICE_HEADER.split():
        return _parse_devices(source, channels, build_maps(observations or {})), "device_clock"
    raise Rejected(f"采样表表头应为 {LEGACY_HEADER.replace(' ', ',')} 或 {DEVICE_HEADER.replace(' ', ',')}")


def _parse_legacy(source, channels):
    result = {}
    for line, (identity, channel, tick, value) in rows(source, LEGACY_HEADER, "采样表", 16000):
        key(identity, "采样行号")
        if identity in result or channel not in channels:
            raise Rejected(f"采样表第 {line} 行编号重复或通道未登记")
        result[identity] = Reading(identity, channel, Fraction(integer(tick, "采样时刻")),
                                   integer(value, "位移", -10**8), line)
    return result


def _parse_devices(source, channels, clocks):
    result = {}
    for line, (identity, channel, device, local, value) in rows(source, DEVICE_HEADER, "采样表", 16000):
        key(identity, "采样行号")
        device = key(device, "采集机号")
        if identity in result or channel not in channels:
            raise Rejected(f"采样表第 {line} 行编号重复或通道未登记")
        local_tick = parse_clock(local, "本机时刻")
        clock = clocks.get(device)
        test_tick = clock.to_test(local_tick) if clock is not None else None
        if test_tick is None:
            state = "no_sync_evidence"
            test_tick = local_tick
        else:
            state = "synced"
        result[identity] = Reading(identity, channel, test_tick, integer(value, "位移", -10**8), line,
                                   device, local_tick, state)
    return result
