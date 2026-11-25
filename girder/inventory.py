from dataclasses import asdict

from .errors import Rejected
from .review import effective_reasons, exclusions
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


def identify(row, excluded, windows, reasons):
    assignment = windows.find(row.tick) if windows else (row.hold, None)
    if row.id in excluded:
        state = "excluded"
    elif assignment is None:
        state = "outside"
    else:
        state = "active"
    hold, phase = assignment or (None, None)
    entry = asdict(row) | {"state": state, "hold": hold, "phase": phase}
    if state == "excluded":
        entry["reasons"] = reasons[row.id]
    return entry


def inventory(survey, journal, params):
    kind, state, match, requested_page = read_filter(params)
    excluded = exclusions(journal)[kind]
    reasons = effective_reasons(journal)[kind]
    readings = kind == "reading"
    rows = survey.readings if readings else survey.positions
    windows = WindowIndex(survey.plan.holds) if readings else None
    matches = []
    for row in rows.values():
        subject = row.channel if readings else row.axle
        if match and match not in row.id.casefold() and match not in subject.casefold():
            continue
        entry = identify(row, excluded, windows, reasons)
        if state == "all" or entry["state"] == state:
            matches.append(entry)
    pages = max(1, (len(matches) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(requested_page, pages)
    offset = (page - 1) * PAGE_SIZE
    return dict(kind=kind, total=len(matches), page=page, pages=pages, rows=matches[offset:offset + PAGE_SIZE])
