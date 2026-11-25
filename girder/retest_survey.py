from dataclasses import replace

from .intake import Survey
from .position_input import Position
from .reading_input import Reading
from .windows import Hold


def build_retest_holds(plan, records):
    """把已登记补测记录重建成 Hold 对象。窗口全局互斥由调用方校验。"""
    holds = []
    for item in records:
        payload = item["hold"]
        windows = tuple(tuple(pair) for pair in (payload["before"], payload["loaded"], payload["after"]))
        holds.append(Hold(payload["id"], payload["case"], windows))
    return holds


def build_extended_survey(plan, base_positions, base_readings, records, exclusions):
    """合并原计划轮与补测轮，形成可统一归约的 Survey；补测行可被单独排除。"""
    positions = dict(base_positions)
    readings = dict(base_readings)
    holds = list(plan.holds)
    excluded_positions = set(exclusions.get("retest_position", ()))
    excluded_readings = set(exclusions.get("retest_reading", ()))
    for item in records:
        hold = build_retest_holds(plan, [item])[0]
        holds.append(hold)
        for row_id, row in item["positions"].items():
            if row_id not in excluded_positions:
                positions[row_id] = Position(**row)
        for row_id, row in item["readings"].items():
            if row_id not in excluded_readings:
                readings[row_id] = Reading(**row)
    extended_plan = replace(plan, holds=tuple(holds))
    return Survey(extended_plan, positions, readings)
