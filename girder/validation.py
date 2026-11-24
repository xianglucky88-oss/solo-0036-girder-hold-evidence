import re

from .errors import Rejected

KEY = re.compile(r"[A-Za-z0-9_-]{1,40}\Z")


def fields(value, names, label):
    if not isinstance(value, dict) or value.keys() != set(names.split()):
        raise Rejected(f"{label}应包含以下字段：{names}")
    return value


def key(value, label):
    if not isinstance(value, str) or not KEY.fullmatch(value):
        raise Rejected(f"{label}须为 1 至 40 位英数、下划线或连字符")
    return value


def text(value, label, maximum=100):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or not value.isprintable():
        raise Rejected(f"{label}须为 1 至 {maximum} 个可打印字符")
    return value.strip()


def number(value, label, low=0, high=10**8):
    if type(value) is not int or not low <= value <= high:
        raise Rejected(f"{label}须为 {low} 至 {high} 的整数")
    return value


def records(value, parser, label, maximum):
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise Rejected(f"{label}须包含 1 至 {maximum} 条记录")
    result = [parser(item) for item in value]
    if len({item.id for item in result}) != len(result):
        raise Rejected(f"{label}中的编号重复")
    return result
