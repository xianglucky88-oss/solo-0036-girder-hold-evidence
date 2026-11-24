from dataclasses import dataclass

from .plan import Plan, parse_plan
from .position_input import Position, parse_positions
from .reading_input import Reading, parse_readings
from .validation import fields


@dataclass(frozen=True)
class Survey:
    plan: Plan
    positions: dict[str, Position]
    readings: dict[str, Reading]


def parse_survey(data):
    fields(data, "plan positions readings", "导入包")
    plan = parse_plan(data["plan"])
    return Survey(plan, parse_positions(data["positions"], plan), parse_readings(data["readings"], plan))
