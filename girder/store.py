import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS girder_runs (
    id INTEGER PRIMARY KEY,
    plan_hash TEXT NOT NULL,
    input_hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    source TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS girder_journal (
    run INTEGER NOT NULL REFERENCES girder_runs(id),
    revision INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    scope TEXT NOT NULL CHECK(scope IN ('manual', 'ticket')),
    ticket TEXT,
    kind TEXT NOT NULL CHECK(kind IN ('reading', 'position')),
    row_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('exclude', 'restore')),
    reason TEXT NOT NULL,
    PRIMARY KEY(run, revision, seq)
);
CREATE INDEX IF NOT EXISTS girder_journal_run ON girder_journal(run, revision, seq);
CREATE TABLE IF NOT EXISTS girder_editions (
    id INTEGER PRIMARY KEY,
    run INTEGER NOT NULL REFERENCES girder_runs(id),
    revision INTEGER NOT NULL,
    digest TEXT NOT NULL,
    document TEXT NOT NULL,
    UNIQUE(run, revision)
);
"""

MIGRATE_VOTES = """
INSERT INTO girder_journal (run, revision, seq, scope, ticket, kind, row_id, action, reason)
SELECT run, revision, 0, 'manual', NULL, kind, row_id, action, reason
FROM girder_votes
"""


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
            self.migrate_votes(db)

    @staticmethod
    def migrate_votes(db):
        # 旧库使用逐行裁定表；把既有手工裁定原样迁入统一裁定流水。
        if db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'girder_votes'").fetchone():
            db.execute(MIGRATE_VOTES)
            db.execute("DROP TABLE girder_votes")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self, write=False):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
