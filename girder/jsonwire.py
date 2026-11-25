import hashlib
import json
from fractions import Fraction

from .clockmap import format_clock
from .errors import Rejected


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"),
                      default=lambda item: format_clock(item) if isinstance(item, Fraction) else item)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Rejected(f"JSON 字段重复：{key}")
        result[key] = value
    return result


def reject_constant(value):
    raise Rejected(f"JSON 数值无效：{value}")


def parse_json(raw):
    try:
        source = raw.decode("utf-8")
        value = json.loads(source, object_pairs_hook=unique, parse_constant=reject_constant)
        # Escaped isolated surrogates survive decoding but cannot be valid stored UTF-8.
        canonical(value).encode("utf-8")
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise Rejected("请求须为有效的 UTF-8 JSON") from exc
    except ValueError as exc:
        if isinstance(exc, Rejected):
            raise
        raise Rejected("JSON 数值超出处理范围") from exc
