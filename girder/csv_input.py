import csv
import io
import re

from .errors import Rejected
from .validation import number

INTEGER = re.compile(r"-?[0-9]{1,10}\Z")


def rows(source, header, label, maximum):
    if not isinstance(source, str) or len(source.encode("utf-8")) > 450_000:
        raise Rejected(f"{label}须为不超过 450 KB 的 CSV 文本")
    reader = csv.reader(io.StringIO(source.removeprefix('\ufeff'), newline=""), strict=True)
    try:
        if next(reader, None) != header.split():
            raise Rejected(f"{label}表头应为 {header.replace(' ', ',')}")
        count = 0
        for values in reader:
            if not values:
                continue
            count += 1
            if len(values) != len(header.split()) or count > maximum:
                raise Rejected(f"{label}第 {reader.line_num} 行列数不符或行数超限")
            yield reader.line_num, values
        if not count:
            raise Rejected(f"{label}没有数据行")
    except csv.Error as exc:
        raise Rejected(f"{label}第 {reader.line_num} 行 CSV 格式错误") from exc


def integer(value, name, low=0, high=10**8):
    if not INTEGER.fullmatch(value):
        raise Rejected(f"{name}须为整数")
    return number(int(value), name, low, high)
