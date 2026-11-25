import json
from dataclasses import asdict

from .errors import Rejected
from .jsonwire import canonical
from .retest_input import parse_retest
from .runs import require_revision, require_run
from .validation import fields, key, text
from .windows import WindowIndex


def load_retests(db, run):
    rows = db.execute("SELECT retest_id, label, case_id, hold, positions, readings "
                      "FROM girder_retests WHERE run = ? ORDER BY id", (run,)).fetchall()
    result = []
    for row in rows:
        result.append(dict(row) | {"hold": json.loads(row["hold"]),
                                   "positions": json.loads(row["positions"]),
                                   "readings": json.loads(row["readings"])})
    return result


def retest_votes(db, run):
    events = db.execute("SELECT revision, kind, row_id, action, reason, retest_id "
                        "FROM girder_retest_votes WHERE run = ? ORDER BY revision", (run,)).fetchall()
    return [dict(event) for event in events]


def retest_exclusions(events):
    groups = {"retest_position": set(), "retest_reading": set()}
    for event in events:
        group = groups[event["kind"]]
        if event["action"] == "exclude":
            group.add(event["row_id"])
        else:
            group.discard(event["row_id"])
    return groups


def load_substitutions(db, run):
    rows = db.execute("SELECT revision, hold, retest_id, reason FROM girder_substitutions "
                      "WHERE run = ? ORDER BY revision", (run,)).fetchall()
    return [dict(row) for row in rows]


def _bump(db, run, expected):
    if db.execute("UPDATE girder_runs SET revision = revision + 1 WHERE id = ? AND revision = ?",
                  (run, expected)).rowcount != 1:
        raise Rejected("草稿已变化，请刷新后重试", 409)


def register(store, run, data, plan_provider):
    fields(data, "revision id label case before loaded after positions readings", "补测登记")
    expected = data["revision"]
    with store.transaction(write=True) as db:
        row = require_run(db, run)
        require_revision(row, expected)
        plan = plan_provider(row)
        existing = {item["retest_id"] for item in load_retests(db, run)}
        retest = parse_retest(plan, {key: value for key, value in data.items() if key != "revision"}, existing)
        # 全窗口互斥：计划轮与全部已登记补测轮的窗口不得重叠。
        all_holds = list(plan.holds) + _hold_objects(db, run, plan)
        all_holds.append(retest.hold)
        WindowIndex(all_holds)
        _bump(db, run, expected)
        db.execute("INSERT INTO girder_retests (run, revision, retest_id, label, case_id, hold, positions, readings) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (run, expected + 1, retest.id, retest.label, retest.case,
                    canonical(_hold_payload(retest.hold)),
                    canonical({row_id: asdict(row) for row_id, row in retest.positions.items()}),
                    canonical({row_id: asdict(row) for row_id, row in retest.readings.items()})))
    return {"id": run, "revision": expected + 1, "retest_id": retest.id}


def _hold_payload(hold):
    return dict(id=hold.id, case=hold.case,
                before=list(hold.windows[0]), loaded=list(hold.windows[1]), after=list(hold.windows[2]))


def _hold_objects(db, run, plan):
    from .retest_survey import build_retest_holds
    return build_retest_holds(plan, load_retests(db, run))


def adjudicate_retest(store, run, data):
    fields(data, "revision retest_id kind row_id action reason", "补测裁定")
    expected, retest_id = data["revision"], key(data["retest_id"], "补测编号")
    kind, action = data["kind"], data["action"]
    if kind not in ("retest_position", "retest_reading") or action not in ("exclude", "restore"):
        raise Rejected("只可排除或恢复补测驻位行和采样行")
    identity = key(data["row_id"], "原始行号")
    reason = text(data["reason"], "裁定理由", 160)
    with store.transaction(write=True) as db:
        row = require_run(db, run)
        require_revision(row, expected)
        target = db.execute("SELECT positions, readings FROM girder_retests WHERE run = ? AND retest_id = ?",
                            (run, retest_id)).fetchone()
        if target is None:
            raise Rejected("找不到该补测登记", 404)
        pool = json.loads(target["positions"]) if kind == "retest_position" else json.loads(target["readings"])
        if identity not in pool:
            raise Rejected("找不到该补测原始行", 404)
        excluded = retest_exclusions(retest_votes(db, run))[kind]
        if (identity in excluded) == (action == "exclude"):
            raise Rejected("该原始行已处在所请求的状态", 409)
        _bump(db, run, expected)
        db.execute("INSERT INTO girder_retest_votes "
                   "(run, revision, kind, row_id, action, reason, retest_id) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (run, expected + 1, kind, identity, action, reason, retest_id))
    return {"id": run, "revision": expected + 1}


def confirm(store, run, data, build_solution):
    """确认一项替补归属；仅当该边在当前最大匹配中为强制边时接受。"""
    fields(data, "revision hold retest_id reason", "替补确认")
    expected = data["revision"]
    hold = key(data["hold"], "缺证原轮号")
    retest_id = key(data["retest_id"], "补测轮号")
    reason = text(data["reason"], "确认理由", 160)
    with store.transaction(write=True) as db:
        row = require_run(db, run)
        require_revision(row, expected)
        already = {item["hold"]: item["retest_id"] for item in load_substitutions(db, run)}
        if hold in already:
            raise Rejected("该原轮义务已确认归属", 409)
        solution = build_solution(db, row)
        if solution["forced"].get(hold) != retest_id:
            raise Rejected("该归属在最大补齐安排中并不唯一，不能确认", 409)
        _bump(db, run, expected)
        db.execute("INSERT INTO girder_substitutions (run, revision, hold, retest_id, reason) VALUES (?, ?, ?, ?, ?)",
                   (run, expected + 1, hold, retest_id, reason))
    return {"id": run, "revision": expected + 1}
