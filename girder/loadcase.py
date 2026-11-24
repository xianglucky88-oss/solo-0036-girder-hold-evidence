from dataclasses import dataclass

from .validation import fields, key, number, records, text


@dataclass(frozen=True)
class Axle:
    id: str
    target_mm: int
    tolerance_mm: int


@dataclass(frozen=True)
class LoadCase:
    id: str
    label: str
    lane: str
    target_kg: int
    tolerance_kg: int
    axles: tuple[Axle, ...]


def parse_axle(item):
    fields(item, "id target_mm tolerance_mm", "轴位要求")
    return Axle(key(item["id"], "车轴号"), number(item["target_mm"], "目标轴距"),
                number(item["tolerance_mm"], "轴距容差"))


def parse_case(item):
    fields(item, "id label lane target_kg tolerance_kg axles", "工况")
    return LoadCase(key(item["id"], "工况号"), text(item["label"], "工况名"), key(item["lane"], "车道"),
                    number(item["target_kg"], "目标总质量", 1), number(item["tolerance_kg"], "总质量容差"),
                    tuple(records(item["axles"], parse_axle, "目标车轴", 16)))
