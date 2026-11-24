from .errors import Rejected
from .intake import parse_survey
from .runs import require_revision, snapshot
from .validation import fields, key, number, text


def exclusions(events):
    groups = {"position": set(), "reading": set()}
    for event in events:
        group = groups[event["kind"]]
        if event["action"] == "exclude":
            group.add(event["row_id"])
        else:
            group.discard(event["row_id"])
    return groups


def adjudicate(store, run, data):
    fields(data, "revision kind row_id action reason", "裁定")
    expected = number(data["revision"], "草稿代次")
    kind, action = data["kind"], data["action"]
    if kind not in ("position", "reading") or action not in ("exclude", "restore"):
        raise Rejected("只可排除或恢复驻位行和采样行")
    identity = key(data["row_id"], "原始行号")
    reason = text(data["reason"], "裁定理由", 160)
    row, journal = snapshot(store, run)
    require_revision(row, expected)
    survey = parse_survey(row["source"])
    available = survey.positions if kind == "position" else survey.readings
    if identity not in available:
        raise Rejected("找不到该原始行", 404)
    if (identity in exclusions(journal)[kind]) == (action == "exclude"):
        raise Rejected("该原始行已处在所请求的状态", 409)
    with store.transaction(write=True) as db:
        if db.execute("UPDATE girder_runs SET revision = revision + 1 WHERE id = ? AND revision = ?",
                      (run, expected)).rowcount != 1:
            raise Rejected("草稿已变化，请刷新后重试", 409)
        db.execute("INSERT INTO girder_votes VALUES (?, ?, ?, ?, ?, ?)",
                   (run, expected + 1, kind, identity, action, reason))
    return {"id": run, "revision": expected + 1}
