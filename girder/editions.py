import json

from .draft import materialize
from .errors import Rejected
from .jsonwire import canonical, fingerprint
from .retests import load_retests
from .runs import require_revision, require_run
from .validation import fields, number


def release(store, run, data):
    fields(data, "revision", "签出请求")
    expected = number(data["revision"], "草稿代次")
    row, journal, _, report, retest_journal = materialize(store, run)
    require_revision(row, expected)
    if not report["ready"]:
        raise Rejected("尚有义务缺少有效履约，无法签出", 409)
    with store.transaction() as db:
        retest_records = load_retests(db, run)
    document = dict(input_hash=row["input_hash"], plan_hash=row["plan_hash"], run=run, revision=expected,
                    source=row["source"], journal=journal, retest_journal=retest_journal,
                    retest_records=retest_records, report=report)
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
