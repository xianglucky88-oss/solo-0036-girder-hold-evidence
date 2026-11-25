from dataclasses import dataclass
from typing import Optional

from .csv_input import integer, mapped_rows, rows
from .errors import Rejected
from .validation import key
POSITION_ALIASES = {
    "id": ("id", "row_id"),
    "hold": ("hold", "hold_id", "round_id"),
    "vehicle": ("vehicle", "vehicle_id", "vehicle_no", "vehicle_number",
                "truck", "truck_id", "truck_no", "car", "car_id", "car_no",
                "车号", "车辆"),
    "axle": ("axle", "axle_id"),
    "lane": ("lane", "lane_id"),
    "station_mm": ("station_mm", "position_mm", "station", "target_mm"),
    "mass_kg": ("mass_kg", "mass", "weight_kg"),
}
OLD_HEADER = "id hold axle lane station_mm mass_kg"


@dataclass(frozen=True, init=False)
class Position:
    id: str
    hold: str
    axle: str
    lane: str
    station_mm: int
    mass_kg: int
    line: int
    vehicle: Optional[str]

    def __init__(self, id, hold, axle=None, lane=None, station_mm=None,
                 mass_kg=None, line=None, vehicle=None):
        # Compatibility with the vehicle-first positional shape used by the
        # multi-vehicle contract: id, hold, vehicle, axle, lane, station, mass, line.
        if station_mm is not None and not isinstance(station_mm, int):
            csv_line = vehicle
            vehicle = axle
            axle = lane
            lane = station_mm
            station_mm = mass_kg
            mass_kg = line
            line = csv_line
        elif not isinstance(line, int) and isinstance(vehicle, int):
            # Alternate positional order: ..., mass_kg, vehicle, line.
            vehicle, line = line, vehicle
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "hold", hold)
        object.__setattr__(self, "axle", axle)
        object.__setattr__(self, "lane", lane)
        object.__setattr__(self, "station_mm", station_mm)
        object.__setattr__(self, "mass_kg", mass_kg)
        object.__setattr__(self, "line", line)
        object.__setattr__(self, "vehicle", vehicle or None)


def parse_positions(source, plan):
    cases = {case.id: case for case in plan.cases}
    holds = {hold.id: hold.case for hold in plan.holds}
    result = {}

    # Keep the original exact six-column contract on its established path.
    first_line = source.splitlines()[0].strip() if isinstance(source, str) and source.splitlines() else ""
    if first_line == OLD_HEADER.replace(" ", ","):
        case_axles = {case.id: {axle.id for axle in case.axles} for case in plan.cases}
        for line, (identity, hold, axle, lane, station, mass) in rows(source, OLD_HEADER, "驻位表", 1280):
            key(identity, "驻位行号")
            if identity in result or hold not in holds or axle not in case_axles[holds.get(hold, "")]:
                raise Rejected(f"驻位表第 {line} 行编号重复或轮次、车轴未登记")
            result[identity] = Position(identity, hold, axle, key(lane, "车道"),
                                       integer(station, "实测轴距", 0, plan.span_mm),
                                       integer(mass, "实测质量", 1), line)
        return result

    records = mapped_rows(source, "驻位表", 1280, POSITION_ALIASES,
                          ("id", "hold", "axle", "lane", "station_mm", "mass_kg"))
    header_fields = [part.strip().removeprefix("﻿") for part in first_line.split(",")]
    has_vehicle_column = any(name in POSITION_ALIASES["vehicle"] for name in header_fields)

    for line, item in records:
        identity = item["id"]
        hold_id = item["hold"]
        axle_id = item["axle"]
        raw_vehicle = item.get("vehicle", "") if has_vehicle_column else ""
        vehicle_id = raw_vehicle.strip() if isinstance(raw_vehicle, str) else ""
        key(identity, "驻位行号")
        if identity in result or hold_id not in holds:
            raise Rejected(f"驻位表第 {line} 行编号重复或轮次未登记")
        case = cases[holds[hold_id]]

        if vehicle_id:
            vehicle_id = key(vehicle_id, "车号")
            plan_vehicle = next((v for v in case.vehicles if v.id == vehicle_id), None)
            if plan_vehicle is None or axle_id not in {axle.id for axle in plan_vehicle.axles}:
                raise Rejected(f"驻位表第 {line} 行所填车号或车轴未登记，整份退件",
                               code="unregistered_vehicle_axle",
                               details={"line": line, "row_id": identity,
                                        "vehicle": vehicle_id, "axle": axle_id})
        elif axle_id not in {axle.id for axle in case.axles}:
            # A blank vehicle is inferable; an unregistered axle is still a
            # foreign-key error and cannot become an inference candidate.
            raise Rejected(f"驻位表第 {line} 行轮次、车轴未登记")

        result[identity] = Position(
            identity, hold_id, axle_id, key(item["lane"], "车道"),
            integer(item["station_mm"], "实测轴距", 0, plan.span_mm),
            integer(item["mass_kg"], "实测质量", 1), line, vehicle_id or None)
    return result
