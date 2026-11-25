from dataclasses import asdict

from .graded import DIRECTION_NAMES
from .errors import Rejected
from .review import exclusions
from .windows import FINAL_EMPTY, FIRST_EMPTY, PHASES, WindowIndex

PAGE_SIZE = 50
EMPTY_NAMES = {FIRST_EMPTY: "首空载", FINAL_EMPTY: "末段撤净"}
PHASE_NAMES = dict(zip(PHASES, ("空载", "驻载", "撤载")))


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


def graded_phase_names(plan):
    names = dict(EMPTY_NAMES)
    if plan.graded is not None:
        for step in plan.graded.steps:
            names[step.id] = f"{step.level} · {DIRECTION_NAMES[step.direction]}"
    return names


def identify(row, excluded, windows, plan=None):
    if windows is None:
        return asdict(row) | {"state": "excluded" if row.id in excluded else "active", "scope": "hold",
                              "owner": row.hold, "phase": None, "phase_label": None}
    assignment = windows.find(row.tick)
    if row.id in excluded:
        state = "excluded"
    elif assignment is None:
        state = "outside"
    else:
        state = "active"
    if assignment is None:
        return asdict(row) | {"state": state, "scope": None, "owner": None, "phase": None, "phase_label": None}
    scope, owner, phase = assignment
    label = PHASE_NAMES.get(phase) if scope == "hold" else graded_phase_names(plan).get(phase, phase)
    return asdict(row) | {"state": state, "scope": scope, "owner": owner, "phase": phase, "phase_label": label}


def inventory(survey, journal, params):
    kind, state, match, requested_page = read_filter(params)
    excluded = exclusions(journal)[kind]
    readings = kind == "reading"
    rows = survey.readings if readings else survey.positions
    windows = WindowIndex.for_plan(survey.plan) if readings else None
    matches = []
    for row in rows.values():
        subject = row.channel if readings else row.axle
        entry = identify(row, excluded, windows, survey.plan)
        if match:
            haystack = {row.id.casefold(), subject.casefold()}
            if entry["phase"]:
                haystack.add(str(entry["phase"]).casefold())
            if entry["phase_label"]:
                haystack.add(entry["phase_label"].casefold())
            if not any(match in item for item in haystack):
                continue
        if state == "all" or entry["state"] == state:
            matches.append(entry)
    pages = max(1, (len(matches) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(requested_page, pages)
    offset = (page - 1) * PAGE_SIZE
    return dict(kind=kind, total=len(matches), page=page, pages=pages, rows=matches[offset:offset + PAGE_SIZE])
