from dataclasses import dataclass

from .csv_input import integer, rows
from .errors import Rejected
from .position_input import Position
from .reading_input import Reading
from .validation import fields, key, number, text
from .windows import PHASES, Hold


@dataclass(frozen=True)
class Retest:
    id: str
    label: str
    case: str
    hold: Hold
    positions: dict
    readings: dict


def parse_retest_hold(data, case_ids, known_ids):
    fields(data, "id case before loaded after", "补测轮次")
    hold_id = key(data["id"], "补测轮次号")
    case_id = key(data["case"], "工况号")
    if case_id not in case_ids or hold_id in known_ids:
        raise Rejected("补测轮次须引用已登记工况且轮次号不得与既有轮次重复")
    windows = []
    for phase in PHASES:
        pair = data[phase]
        if not isinstance(pair, list) or len(pair) != 2:
            raise Rejected("时间窗须给出两个整秒端点")
        start, end = [number(t, "时间窗端点") for t in pair]
        if start >= end or windows and windows[-1][1] > start:
            raise Rejected("空载、驻载、撤载窗口必须按顺序且互不重叠")
        windows.append((start, end))
    return Hold(hold_id, case_id, tuple(windows))


def parse_retest_positions(source, hold, case, span):
    result = {}
    axles = {axle.id for axle in case.axles}
    for line, (identity, wheel, axle, lane, station, mass) in rows(
            source, "id hold axle lane station_mm mass_kg", "补测驻位表", 1280):
        key(identity, "补测驻位行号")
        if identity in result or wheel != hold.id or axle not in axles:
            raise Rejected(f"补测驻位表第 {line} 行编号重复、轮次不符或车轴未登记")
        result[identity] = Position(identity, hold.id, axle, key(lane, "车道"),
                                    integer(station, "实测轴距", 0, span), integer(mass, "实测质量", 1), line)
    return result


def parse_retest_readings(source, plan):
    result = {}
    channels = set(plan.references) | {point.id for point in plan.points}
    for line, (identity, channel, tick, value) in rows(
            source, "id channel tick value_um", "补测采样表", 16000):
        key(identity, "补测采样行号")
        if identity in result or channel not in channels:
            raise Rejected(f"补测采样表第 {line} 行编号重复或通道未登记")
        result[identity] = Reading(identity, channel, integer(tick, "采样时刻"),
                                   integer(value, "位移", -10**8), line)
    return result


def parse_retest(plan, data, existing):
    """解析一次补测登记（不含外层 revision 字段）；existing 是已占用的轮次号集合。"""
    fields(data, "id label case before loaded after positions readings", "补测登记")
    retest_id = key(data["id"], "补测编号")
    label = text(data["label"], "补测名称")
    known = {hold.id for hold in plan.holds} | existing
    if retest_id in known:
        raise Rejected("补测编号与既有轮次重复")
    hold = parse_retest_hold({k: data[k] for k in ("id", "case", "before", "loaded", "after")},
                             {case.id for case in plan.cases}, known)
    case = next(item for item in plan.cases if item.id == hold.case)
    positions = parse_retest_positions(data["positions"], hold, case, plan.span_mm)
    readings = parse_retest_readings(data["readings"], plan)
    return Retest(retest_id, label, hold.case, hold, positions, readings)
