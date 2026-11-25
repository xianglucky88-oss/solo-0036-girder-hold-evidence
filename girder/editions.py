import json

from .draft import materialize
from .errors import Rejected
from .jsonwire import canonical, fingerprint
from .runs import require_revision, require_run
from .validation import fields, number


def release(store, run, data):
    fields(data, "revision", "签出请求")
    expected = number(data["revision"], "草稿代次")
    row, journal, _, report = materialize(store, run)
    require_revision(row, expected)
    if not report["ready"]:
        placement_messages = []
        placement_details = []
        codes = set()
        for hold_id, placement in report.get("placement", {}).items():
            if placement.get("valid"):
                continue
            assignment_state = placement.get("assignment_state")
            if assignment_state == "ambiguous":
                message = f"{hold_id} 驻位归属歧义，存在多种合规归属"
                code = "assignment_ambiguous"
            elif assignment_state == "none":
                message = f"{hold_id} 无合规驻位归属"
                code = "no_compliant_assignment"
            else:
                message = f"{hold_id} 驻位证据无效"
                code = "placement_invalid"
            codes.add(code)
            placement_messages.append(message)
            placement_details.append(dict(hold=hold_id, code=code, message=message))
        detail = "；".join(placement_messages)
        message = "尚有轮次或测点缺少有效证据，无法签出"
        if detail:
            message += f"：{detail}"
        code = next(iter(codes)) if len(codes) == 1 else "release_blocked"
        raise Rejected(message, 409, code=code, details=placement_details or None)
    document = dict(input_hash=row["input_hash"], plan_hash=row["plan_hash"], run=run, revision=expected,
                    source=row["source"], journal=journal, report=report)
    digest = fingerprint(document)
    with store.transaction(write=True) as db:
        require_revision(require_run(db, run), expected)
        db.execute("INSERT INTO girder_editions (run, revision, digest, document) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT(run, revision) DO NOTHING", (run, expected, digest, canonical(document)))
        return dict(db.execute("SELECT id, digest FROM girder_editions WHERE run = ? AND revision = ?",
                               (run, expected)).fetchone())


def list_editions(store):
    with store.transaction() as db:
        rows = db.execute("SELECT e.id, e.run, e.revision, e.digest, r.label FROM girder_editions e "
                          "JOIN girder_runs r ON e.run = r.id ORDER BY e.id DESC")
        return [dict(row) for row in rows]


def read_edition(store, edition):
    with store.transaction() as db:
        row = db.execute("SELECT digest, document FROM girder_editions WHERE id = ?", (edition,)).fetchone()
    if row is None:
        raise Rejected("找不到该签出版", 404)
    return {"id": edition, "digest": row["digest"], "document": json.loads(row["document"])}
