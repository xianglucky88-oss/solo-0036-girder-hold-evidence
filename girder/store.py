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
CREATE TABLE IF NOT EXISTS girder_votes (
    run INTEGER NOT NULL REFERENCES girder_runs(id),
    revision INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('reading', 'position')),
    row_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('exclude', 'restore')),
    reason TEXT NOT NULL,
    PRIMARY KEY(run, revision)
);
CREATE TABLE IF NOT EXISTS girder_editions (
    id INTEGER PRIMARY KEY,
    run INTEGER NOT NULL REFERENCES girder_runs(id),
    revision INTEGER NOT NULL,
    digest TEXT NOT NULL,
    document TEXT NOT NULL,
    UNIQUE(run, revision)
);
CREATE TABLE IF NOT EXISTS girder_retests (
    id INTEGER PRIMARY KEY,
    run INTEGER NOT NULL REFERENCES girder_runs(id),
    revision INTEGER NOT NULL,
    retest_id TEXT NOT NULL,
    label TEXT NOT NULL,
    case_id TEXT NOT NULL,
    hold TEXT NOT NULL,
    positions TEXT NOT NULL,
    readings TEXT NOT NULL,
    UNIQUE(run, retest_id)
);
CREATE TABLE IF NOT EXISTS girder_retest_votes (
    run INTEGER NOT NULL REFERENCES girder_runs(id),
    revision INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('retest_position', 'retest_reading')),
    row_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('exclude', 'restore')),
    reason TEXT NOT NULL,
    retest_id TEXT NOT NULL,
    PRIMARY KEY(run, revision)
);
CREATE TABLE IF NOT EXISTS girder_substitutions (
    run INTEGER NOT NULL REFERENCES girder_runs(id),
    revision INTEGER NOT NULL,
    hold TEXT NOT NULL,
    retest_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY(run, revision)
);
"""


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

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
