import csv
import io
import re

from .errors import Rejected
from .validation import number

INTEGER = re.compile(r"-?[0-9]{1,10}\Z")
BOM = "﻿"


def rows(source, header, label, maximum):
    if not isinstance(source, str) or len(source.encode("utf-8")) > 450_000:
        raise Rejected(f"{label}须为不超过 450 KB 的 CSV 文本")
    reader = csv.reader(io.StringIO(source.removeprefix(BOM), newline=""), strict=True)
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


def mapped_rows(source, label, maximum, aliases, required):
    """Read a header whose column order and compatible names may vary."""
    if not isinstance(source, str) or len(source.encode("utf-8")) > 450_000:
        raise Rejected(f"{label}须为不超过 450 KB 的 CSV 文本")
    reader = csv.reader(io.StringIO(source.removeprefix(BOM), newline=""), strict=True)
    try:
        header = next(reader, None)
        if not header:
            raise Rejected(f"{label}缺少表头")
        normalized = [name.removeprefix(BOM).strip() for name in header]
        indexes = {}
        for logical, names in aliases.items():
            for name in names:
                if name in normalized:
                    indexes[logical] = normalized.index(name)
                    break
        missing = [name for name in required if name not in indexes]
        if missing:
            expected = ",".join(aliases[name][0] for name in missing)
            raise Rejected(f"{label}表头缺少必要列：{expected}")
        count = 0
        for values in reader:
            if not values:
                continue
            count += 1
            if len(values) != len(header) or count > maximum:
                raise Rejected(f"{label}第 {reader.line_num} 行列数不符或行数超限")
            record = {logical: values[index] if index < len(values) else ""
                      for logical, index in indexes.items()}
            yield reader.line_num, record
        if not count:
            raise Rejected(f"{label}没有数据行")
    except csv.Error as exc:
        raise Rejected(f"{label}第 {reader.line_num} 行 CSV 格式错误") from exc


def integer(value, name, low=0, high=10**8):
    if not INTEGER.fullmatch(value):
        raise Rejected(f"{name}须为整数")
    return number(int(value), name, low, high)
