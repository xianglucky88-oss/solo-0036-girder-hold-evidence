from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from .errors import Rejected
from .validation import key, number, records, text


@dataclass(frozen=True)
class Axle:
    id: str
    target_mm: int
    tolerance_mm: int
    vehicle: Optional[str] = None
    lane: Optional[str] = None


@dataclass(frozen=True)
class Vehicle:
    id: str
    lane: str
    axles: tuple[Axle, ...]
    min_kg: int = 0
    max_kg: int = 10**8
    target_kg: Optional[int] = None
    tolerance_kg: Optional[int] = None
    label: str = ""


@dataclass(frozen=True)
class LoadCase:
    id: str
    label: str
    lane: str
    target_kg: int
    tolerance_kg: int
    axles: tuple[Axle, ...]
    vehicles: tuple[Vehicle, ...] = field(default_factory=tuple)
    total_min_kg: int = 0
    total_max_kg: int = 10**8
    multi_vehicle: bool = False


def pick(item: Mapping[str, Any], *names: str) -> tuple[Any, Optional[str]]:
    for name in names:
        if name in item and item[name] is not None:
            return item[name], name
    return None, None


def parse_range(item: Mapping[str, Any], label: str, *, required: bool = True,
                low: int = 0) -> tuple[int, int, Optional[int], Optional[int]]:
    """Read either [min, max], explicit bounds, or target +/- tolerance."""
    value, range_name = pick(item, "mass_range_kg", "mass_range", "range_kg", "range",
                              "mass_interval_kg", "mass_interval", "interval",
                              "mass_bounds_kg", "bounds_kg", "mass_bounds", "bounds",
                              "mass_requirement", "mass_requirements", "requirement",
                              "total_mass_range_kg", "whole_mass_range_kg",
                              "wheel_mass_range_kg")
    if value is None:
        mass_value = item.get("mass_kg", item.get("mass", item.get("total_mass_kg")))
        if isinstance(mass_value, (list, tuple, Mapping)):
            value = mass_value
    if value is not None:
        if isinstance(value, Mapping):
            return parse_range(value, label, required=required, low=low)
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise Rejected(f"{label}须为 [下限, 上限] 质量范围")
        lower = number(value[0], f"{label}下限", low)
        upper = number(value[1], f"{label}上限", low)
        if lower > upper:
            raise Rejected(f"{label}下限不得大于上限")
        return lower, upper, None, None

    mass = item.get("mass")
    if isinstance(mass, Mapping):
        return parse_range(mass, f"{label}质量", required=required, low=low)

    lower_value, _ = pick(item, "min_kg", "minimum_kg", "lower_kg", "from_kg",
                         "min_mass_kg", "minimum_mass_kg", "mass_min_kg", "mass_minimum_kg",
                         "lower_mass_kg", "mass_lower_kg", "minimum_total_mass_kg",
                         "total_min_kg", "min_total_kg", "total_minimum_kg",
                         "minimum_total_kg", "whole_min_kg", "wheel_min_kg",
                         "min", "minimum", "lower", "mass_min", "lower_mass")
    upper_value, _ = pick(item, "max_kg", "maximum_kg", "upper_kg", "to_kg",
                         "max_mass_kg", "maximum_mass_kg", "mass_max_kg", "mass_maximum_kg",
                         "upper_mass_kg", "mass_upper_kg", "maximum_total_mass_kg",
                         "total_max_kg", "max_total_kg", "total_maximum_kg",
                         "maximum_total_kg", "whole_max_kg", "wheel_max_kg",
                         "max", "maximum", "upper", "mass_max", "upper_mass")
    if lower_value is not None or upper_value is not None:
        if lower_value is None or upper_value is None:
            raise Rejected(f"{label}须同时给出质量下限和上限")
        lower = number(lower_value, f"{label}质量下限", low)
        upper = number(upper_value, f"{label}质量上限", low)
        if lower > upper:
            raise Rejected(f"{label}质量下限不得大于上限")
        target_value, _ = pick(item, "target_kg", "target_mass_kg", "mass_target_kg")
        tolerance_value, _ = pick(item, "tolerance_kg", "mass_tolerance_kg", "tolerance_mass_kg")
        target = number(target_value, f"{label}目标质量", low) if target_value is not None else None
        tolerance = number(tolerance_value, f"{label}质量容差", 0) if tolerance_value is not None else None
        return lower, upper, target, tolerance

    target_value, _ = pick(item, "target_kg", "target_mass_kg", "mass_target_kg",
                           "total_target_kg", "total_mass_kg", "wheel_mass_kg",
                           "whole_mass_kg", "expected_mass_kg",
                           "target_mass", "required_kg", "required_mass_kg",
                           "mass_requirement_kg", "required_total_kg")
    if target_value is None:
        if required:
            raise Rejected(f"{label}须给出目标质量与容差，或质量上下限")
        return 0, 10**8, None, None
    target = number(target_value, f"{label}目标总质量", 1)
    tolerance_value, _ = pick(item, "tolerance_kg", "mass_tolerance_kg", "tolerance_mass_kg",
                              "total_tolerance_kg", "tolerance", "mass_tolerance", "tol_kg")
    tolerance = number(tolerance_value, f"{label}总质量容差", 0) if tolerance_value is not None else 0
    return target - tolerance, target + tolerance, target, tolerance


def parse_axle(item: Mapping[str, Any]) -> Axle:
    if not isinstance(item, Mapping):
        raise Rejected("轴位要求须为对象")
    axle_id, _ = pick(item, "id", "axle", "axle_id")
    if axle_id is None:
        raise Rejected("轴位要求应包含 id")
    target_value, _ = pick(item, "target_mm", "station_mm", "position_mm", "target", "target_station_mm")
    tolerance_value, _ = pick(item, "tolerance_mm", "tolerance", "tol_mm", "position_tolerance_mm")
    if target_value is None or tolerance_value is None:
        raise Rejected("轴位要求应包含 target_mm 和 tolerance_mm")
    vehicle_value, _ = pick(item, "vehicle", "vehicle_id", "vehicle_no", "vehicle_number",
                             "truck", "truck_id", "truck_no", "car", "car_id", "car_no")
    lane_value, _ = pick(item, "lane", "lane_id")
    return Axle(
        key(axle_id, "车轴号"),
        number(target_value, "目标轴距"),
        number(tolerance_value, "轴距容差"),
        key(vehicle_value, "车号") if vehicle_value not in (None, "") else None,
        key(lane_value, "车道") if lane_value not in (None, "") else None,
    )


def parse_vehicle(item: Mapping[str, Any], fallback_lane: str = "") -> Vehicle:
    if not isinstance(item, Mapping):
        raise Rejected("车辆计划须为对象")
    vehicle_id, _ = pick(item, "id", "vehicle", "vehicle_id", "vehicle_no",
                          "vehicle_number", "truck", "truck_id", "car", "car_id")
    if vehicle_id is None:
        raise Rejected("车辆计划应包含 id")
    vehicle_id = key(vehicle_id, "车号")
    lane_value, _ = pick(item, "lane", "lane_id", "applicable_lane")
    lane = key(lane_value, "车道") if lane_value not in (None, "") else fallback_lane
    if not lane:
        raise Rejected(f"车辆 {vehicle_id} 须给出车道")
    label_value, _ = pick(item, "label", "name")
    label = text(label_value, "车辆名称", 80) if label_value not in (None, "") else ""
    axle_value, _ = pick(item, "axles", "axle_plan", "axle_positions", "positions")
    axles = tuple(records(axle_value, parse_axle, "车辆计划车轴", 16))
    # Axle ids may repeat between vehicles; uniqueness inside one vehicle remains required.
    if len({axle.id for axle in axles}) != len(axles):
        raise Rejected(f"车辆 {vehicle_id} 的车轴编号重复")
    axles = tuple(Axle(axle.id, axle.target_mm, axle.tolerance_mm, vehicle_id,
                       axle.lane or lane) for axle in axles)
    lower, upper, target, tolerance = parse_range(item, f"车辆 {vehicle_id} 分车总质量", required=False, low=1)
    return Vehicle(vehicle_id, lane, axles, lower, upper, target, tolerance, label)


def _range_map(case_data: Mapping[str, Any], vehicles: list[Vehicle]) -> dict[str, tuple[int, int]]:
    """Support mass ranges supplied as id-keyed maps or record lists."""
    result = {vehicle.id: (vehicle.min_kg, vehicle.max_kg) for vehicle in vehicles}
    map_value, _ = pick(case_data, "vehicle_mass_ranges_kg", "vehicle_mass_ranges",
                        "vehicle_mass_range_kg", "vehicle_mass_range",
                        "vehicle_ranges_kg", "vehicle_ranges",
                        "mass_range_by_vehicle_kg", "mass_range_by_vehicle",
                        "per_vehicle_mass_range_kg", "per_vehicle_mass",
                        "vehicle_mass_limits_kg", "vehicle_mass_limits", "mass_limits",
                        "vehicle_limits", "mass_by_vehicle_kg", "mass_by_vehicle",
                        "vehicle_mass_kg", "vehicle_mass", "vehicle_weights_kg",
                        "weight_by_vehicle_kg", "vehicle_masses_kg", "vehicle_masses",
                        "vehicle_limits_kg", "vehicle_mass_requirements")
    if isinstance(map_value, Mapping):
        for vehicle in vehicles:
            if vehicle.id not in map_value:
                continue
            value = map_value[vehicle.id]
            if isinstance(value, (list, tuple)) and len(value) == 2:
                result[vehicle.id] = (number(value[0], f"{vehicle.id} 质量下限", 1),
                                      number(value[1], f"{vehicle.id} 质量上限", 1))
            elif isinstance(value, Mapping):
                lo, hi, _, _ = parse_range(value, f"车辆 {vehicle.id} 分车质量", required=False, low=1)
                if (lo, hi) != (0, 10**8):
                    result[vehicle.id] = (lo, hi)
            elif isinstance(value, int):
                result[vehicle.id] = (value, value)
    if isinstance(map_value, list):
        for entry in map_value:
            if not isinstance(entry, Mapping):
                continue
            vid, _ = pick(entry, "vehicle", "vehicle_id", "truck", "car", "id")
            if vid in result:
                lo, hi, _, _ = parse_range(entry, f"车辆 {vid} 分车质量", required=False, low=1)
                if (lo, hi) != (0, 10**8):
                    result[vid] = (lo, hi)
    targets, _ = pick(case_data, "vehicle_targets_kg", "vehicle_target_mass_kg")
    tolerances, _ = pick(case_data, "vehicle_tolerances_kg", "vehicle_tolerance_kg")
    if isinstance(targets, Mapping):
        for vehicle in vehicles:
            if vehicle.id in targets:
                target = number(targets[vehicle.id], f"{vehicle.id} 目标质量", 1)
                tol = number(tolerances.get(vehicle.id, 0) if isinstance(tolerances, Mapping) else 0,
                             f"{vehicle.id} 质量容差", 0)
                result[vehicle.id] = (target - tol, target + tol)
    records_value, _ = pick(case_data, "vehicle_requirements", "vehicle_mass_requirements",
                            "mass_requirements", "mass_ranges", "weights", "vehicle_weights")
    if isinstance(records_value, list):
        for entry in records_value:
            if not isinstance(entry, Mapping):
                continue
            vid, _ = pick(entry, "vehicle", "vehicle_id", "vehicle_no", "truck", "car", "id")
            if vid in result:
                lo, hi, _, _ = parse_range(entry, f"车辆 {vid} 分车质量", required=False, low=1)
                if "min_kg" in entry or "lower_kg" in entry or "target_kg" in entry or "mass_range_kg" in entry:
                    result[vid] = (lo, hi)
    for lo, hi in result.values():
        if lo > hi:
            raise Rejected("分车质量下限不得大于上限")
    return result


def parse_case(item: Mapping[str, Any]) -> LoadCase:
    if not isinstance(item, Mapping):
        raise Rejected("工况须为对象")
    case_id = key(item.get("id"), "工况号")
    label = text(item.get("label"), "工况名")

    lane_value = item.get("lane")
    case_lane = key(lane_value, "车道") if lane_value not in (None, "") else ""

    vehicle_data, vehicle_key_name = pick(item, "vehicles", "vehicle", "trucks", "truck",
                                          "cars", "car", "vehicle_plan",
                                          "truck_plan", "vehicle_plans", "truck_plans",
                                          "vehicle_specs", "vehicle_configs", "axle_groups")
    if vehicle_data is None:
        axle_map = item.get("vehicle_axles", item.get("axles_by_vehicle"))
        axle_sets = item.get("axle_sets")
        if isinstance(axle_map, Mapping):
            lanes = item.get("vehicle_lanes", item.get("lanes_by_vehicle", {}))
            vehicle_data = []
            for vehicle_id, axle_plan in axle_map.items():
                lane = lanes.get(vehicle_id, case_lane) if isinstance(lanes, Mapping) else case_lane
                vehicle_data.append({"id": vehicle_id, "lane": lane, "axles": axle_plan})
        elif isinstance(axle_sets, list):
            vehicle_data = axle_sets
    vehicles: list[Vehicle] = []
    if vehicle_data is not None:
        if isinstance(vehicle_data, Mapping):
            if "axles" in vehicle_data or "axle_plan" in vehicle_data or "id" in vehicle_data:
                vehicle_data = [vehicle_data]
            else:
                normalized_vehicles = []
                for vehicle_id, spec in vehicle_data.items():
                    if isinstance(spec, Mapping):
                        normalized_vehicles.append({**spec, "id": spec.get("id", vehicle_id)})
                    else:
                        normalized_vehicles.append({"id": vehicle_id, "axles": spec})
                vehicle_data = normalized_vehicles
        if not isinstance(vehicle_data, list) or not 1 <= len(vehicle_data) <= 16:
            raise Rejected("车辆计划须包含 1 至 16 条记录")
        raw_axle_data = item.get("axles")
        for vehicle_item in vehicle_data:
            if not isinstance(vehicle_item, Mapping):
                continue
            has_axle_plan = any(name in vehicle_item for name in ("axles", "axle_plan", "axle_positions", "positions"))
            if has_axle_plan or not isinstance(raw_axle_data, list):
                continue
            vehicle_id, _ = pick(vehicle_item, "id", "vehicle", "vehicle_id", "truck", "car")
            inherited_axles = []
            for axle_item in raw_axle_data:
                if not isinstance(axle_item, Mapping):
                    continue
                axle_vehicle, _ = pick(axle_item, "vehicle", "vehicle_id", "vehicle_no",
                                      "truck", "truck_id", "car", "car_id")
                if axle_vehicle == vehicle_id:
                    inherited_axles.append(axle_item)
            if inherited_axles:
                vehicle_item["axles"] = inherited_axles
        seen = set()
        for vehicle_item in vehicle_data:
            vehicle = parse_vehicle(vehicle_item, case_lane)
            if vehicle.id in seen:
                raise Rejected("车辆计划中的车号重复")
            seen.add(vehicle.id)
            vehicles.append(vehicle)
        ranges = _range_map(item, vehicles)
        vehicles = [Vehicle(v.id, v.lane, v.axles, *ranges[v.id], v.target_kg, v.tolerance_kg, v.label)
                    for v in vehicles]
    else:
        axle_data = item.get("axles")
        if not isinstance(axle_data, list) or not 1 <= len(axle_data) <= 16:
            raise Rejected("目标车轴须包含 1 至 16 条记录")
        axles = [parse_axle(entry) for entry in axle_data]
        if len({(axle.vehicle, axle.id) for axle in axles}) != len(axles):
            raise Rejected("同一车辆的车轴编号重复")
        grouped: dict[str, list[Axle]] = {}
        flat_vehicle = any(axle.vehicle for axle in axles)
        if flat_vehicle:
            for axle in axles:
                vid = axle.vehicle or ""
                if not vid:
                    raise Rejected("平面车轴计划中的车号须填写完整")
                lane = axle.lane or case_lane
                if not lane:
                    raise Rejected("多车工况须给出车道")
                grouped.setdefault(vid, []).append(Axle(axle.id, axle.target_mm, axle.tolerance_mm, vid, lane))
            for vid, group in grouped.items():
                vehicles.append(Vehicle(vid, group[0].lane or case_lane, tuple(group)))
            ranges = _range_map(item, vehicles)
            vehicles = [Vehicle(v.id, v.lane, v.axles, *ranges[v.id], None, None, v.label) for v in vehicles]
        else:
            if not case_lane:
                raise Rejected("工况应包含 lane，或在车辆计划中给出车道")
            if len({axle.id for axle in axles}) != len(axles):
                raise Rejected("目标车轴编号重复；多车同号轴须提供车号或 vehicles 计划")
            lower, upper, target, tolerance = parse_range(item, "工况总质量", required=True, low=1)
            target_kg = target if target is not None else lower
            tolerance_kg = tolerance if tolerance is not None else upper - lower
            vehicle = Vehicle(case_id, case_lane, tuple(
                Axle(a.id, a.target_mm, a.tolerance_mm, case_id, case_lane) for a in axles),
                lower, upper, target_kg, tolerance_kg)
            total_lower, total_upper = lower, upper
            flat = tuple(vehicle.axles)
            return LoadCase(case_id, label, case_lane, target_kg, tolerance_kg, flat,
                            (vehicle,), total_lower, total_upper, False)

    multi = len(vehicles) > 1
    flat = tuple(axle for vehicle in vehicles for axle in vehicle.axles)
    if len(flat) > 16:
        raise Rejected("一个工况的计划车轴总数不得超过 16 条")
    if case_lane == "":
        case_lane = vehicles[0].lane

    lower, upper, target, tolerance = parse_range(item, "整轮总质量", required=False, low=1)
    if (lower, upper) == (0, 10**8) and target is None:
        # No explicit whole-wheel range: the sum of vehicle ranges is the broad envelope.
        lower = sum(v.min_kg for v in vehicles)
        upper = sum(v.max_kg for v in vehicles)
    target_kg = target if target is not None else lower
    tolerance_kg = tolerance if tolerance is not None else max(0, upper - target_kg)
    return LoadCase(case_id, label, case_lane, target_kg, tolerance_kg, flat,
                    tuple(vehicles), lower, upper, multi)


def parse_load_case(item):  # backwards-compatible public alias
    return parse_case(item)
