from dataclasses import asdict

from .errors import Rejected
from .review import exclusions
from .trace import reading_row
from .windows import WindowIndex

PAGE_SIZE = 50


def read_filter(params):
    keys = {"kind", "state", "match", "page"}
    if not params.keys() <= keys or any(len(values) != 1 for values in params.values()):
        raise Rejected("原始行查询参数重复或无效")
    values = {key: entries[0] for key, entries in params.items()}
    kind = values.get("kind", "reading")
    state = values.get("state", "all")
    match = values.get("match", "").strip()
    page = values.get("page", "1")
    if kind not in ("reading", "position") or state not in ("all", "active", "excluded", "outside"):
        raise Rejected("原始行类别或状态无效")
    if state == "outside" and kind != "reading":
        raise Rejected("仅采样行存在窗外记录")
    if len(match) > 40 or len(page) > 5 or not page.isascii() or not page.isdigit() or int(page) < 1:
        raise Rejected("原始行搜索词或页码无效")
    return kind, state, match.casefold(), int(page)


def identify_reading(row, excluded, windows, outside_reasons):
    if row.id in excluded:
        return reading_row(row) | {"state": "excluded", "hold": None, "phase": None, "reason": None}
    if row.id in outside_reasons:
        return reading_row(row) | {"state": "outside", "hold": None, "phase": None,
                                   "reason": outside_reasons[row.id]}
    hold, phase = windows.find(row.tick)
    return reading_row(row) | {"state": "active", "hold": hold, "phase": phase, "reason": None}


def outside_reasons(survey, excluded):
    windows = WindowIndex(survey.plan.holds)
    reasons = {}
    for row in survey.readings.values():
        if row.id in excluded:
            continue
        if row.sync_state == "no_sync_evidence":
            reasons[row.id] = "no_sync_evidence"
        elif windows.find(row.tick) is None:
            reasons[row.id] = "outside_window"
    return reasons


def inventory(survey, journal, params):
    kind, state, match, requested_page = read_filter(params)
    excluded = exclusions(journal)[kind]
    is_reading = kind == "reading"
    rows = survey.readings if is_reading else survey.positions
    windows = WindowIndex(survey.plan.holds) if is_reading else None
    reasons = outside_reasons(survey, excluded) if is_reading else {}
    matches = []
    for row in rows.values():
        subject = row.channel if is_reading else row.axle
        if match and match not in row.id.casefold() and match not in subject.casefold():
            continue
        if is_reading:
            entry = identify_reading(row, excluded, windows, reasons)
        else:
            entry = asdict(row) | {"state": "excluded" if row.id in excluded else "active", "reason": None}
        if state == "all" or entry["state"] == state:
            matches.append(entry)
    pages = max(1, (len(matches) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(requested_page, pages)
    offset = (page - 1) * PAGE_SIZE
    return dict(kind=kind, total=len(matches), page=page, pages=pages, rows=matches[offset:offset + PAGE_SIZE])
