from dataclasses import dataclass

from .clockmap import parse_sync
from .errors import Rejected
from .plan import Plan, parse_plan
from .position_input import Position, parse_positions
from .reading_input import Reading, parse_readings
from .validation import optional_fields


@dataclass(frozen=True)
class Survey:
    plan: Plan
    positions: dict[str, Position]
    readings: dict[str, Reading]
    observations: dict[str, tuple]


def parse_survey(data):
    optional_fields(data, "plan positions readings sync", "导入包")
    plan = parse_plan(data["plan"])
    observations = parse_sync(data["sync"]) if data.get("sync") else {}
    readings, clock_kind = parse_readings(data["readings"], plan, observations)
    if clock_kind == "device_clock" and not observations:
        raise Rejected("跨采集机采样表须随件提交同步观测")
    if clock_kind == "shared_clock" and observations:
        raise Rejected("共用时钟采样表不接收同步观测，请改用跨采集机采样表头")
    return Survey(plan, parse_positions(data["positions"], plan), readings, observations)
