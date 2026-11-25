import json

from .errors import Rejected
from .intake import parse_survey
from .jsonwire import canonical, fingerprint, parse_json


def require_run(db, run):
    row = db.execute("SELECT * FROM girder_runs WHERE id = ?", (run,)).fetchone()
    if row is None:
        raise Rejected("找不到这份试验资料", 404)
    return dict(row)


def require_revision(run, expected):
    if run["revision"] != expected:
        raise Rejected("草稿已变化，请刷新后重试", 409)


def submit(store, data):
    if isinstance(data, dict) and isinstance(data.get("plan"), str):
        data = data | {"plan": parse_json(data["plan"].removeprefix("\ufeff").encode("utf-8"))}
    survey = parse_survey(data)
    digest = fingerprint(data)
    with store.transaction(write=True) as db:
        cur = db.execute("INSERT INTO girder_runs (plan_hash, input_hash, label, source) VALUES (?, ?, ?, ?) "
                         "ON CONFLICT(input_hash) DO NOTHING",
                         (fingerprint(data["plan"]), digest, survey.plan.label, canonical(data)))
        row = db.execute("SELECT id, revision FROM girder_runs WHERE input_hash = ?", (digest,)).fetchone()
        return dict(row) | {"created": cur.rowcount == 1}


def list_runs(store):
    with store.transaction() as db:
        rows = db.execute("SELECT id, label, revision, input_hash FROM girder_runs ORDER BY id DESC")
        return [dict(row) for row in rows]


def snapshot(store, run):
    with store.transaction() as db:
        row = require_run(db, run)
        events = db.execute("SELECT revision, seq, scope, ticket, kind, row_id, action, reason FROM girder_journal "
                            "WHERE run = ? ORDER BY revision, seq", (run,))
        journal = [dict(event) for event in events]
    row["source"] = json.loads(row["source"])
    return row, journal
