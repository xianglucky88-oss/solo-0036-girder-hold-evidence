from dataclasses import dataclass

from .csv_input import integer, rows
from .errors import Rejected
from .validation import key


@dataclass(frozen=True)
class Position:
    id: str
    hold: str
    axle: str
    lane: str
    station_mm: int
    mass_kg: int
    line: int


def parse_positions(source, plan):
    case_axles = {case.id: {axle.id for axle in case.axles} for case in plan.cases}
    holds = {hold.id: case_axles[hold.case] for hold in plan.holds}
    result = {}
    for line, (identity, hold, axle, lane, station, mass) in rows(source, "id hold axle lane station_mm mass_kg", "驻位表", 1280):
        key(identity, "驻位行号")
        if identity in result or hold not in holds or axle not in holds[hold]:
            raise Rejected(f"驻位表第 {line} 行编号重复或轮次、车轴未登记")
        result[identity] = Position(identity, hold, axle, key(lane, "车道"),
                                    integer(station, "实测轴距", 0, plan.span_mm), integer(mass, "实测质量", 1), line)
    return result
