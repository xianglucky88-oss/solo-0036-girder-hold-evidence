from dataclasses import dataclass

from .errors import Rejected
from .validation import fields, key, number, text


@dataclass(frozen=True)
class Point:
    id: str
    label: str
    station_mm: int
    reference: str
    sign: int


def parse_point(item):
    fields(item, "id label station_mm reference sign", "测点")
    sign = item["sign"]
    if type(sign) is not int or sign not in (-1, 1):
        raise Rejected("测点方向须为 1 或 -1")
    return Point(key(item["id"], "测点号"), text(item["label"], "测点名"),
                 number(item["station_mm"], "断面桩距"), key(item["reference"], "参考点号"), sign)
