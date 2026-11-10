"""SQLite persistence: daily grammar picks, journal entries, vocabulary/flashcards."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_grammar (
    day        TEXT NOT NULL,
    level      TEXT NOT NULL,
    grammar_id TEXT NOT NULL,
    PRIMARY KEY (day, level)
);
CREATE TABLE IF NOT EXISTS entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    day           TEXT NOT NULL,
    grammar_id    TEXT NOT NULL,
    text          TEXT NOT NULL,
    corrected     TEXT,
    feedback_json TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS words (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    word        TEXT NOT NULL UNIQUE,
    reading     TEXT,
    meaning     TEXT,
    pos         TEXT,
    example     TEXT,
    seen_count  INTEGER NOT NULL DEFAULT 1,
    -- spaced repetition (SM-2 style)
    ease        REAL NOT NULL DEFAULT 2.5,
    interval    INTEGER NOT NULL DEFAULT 0,
    reps        INTEGER NOT NULL DEFAULT 0,
    due         TEXT NOT NULL DEFAULT (date('now')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS entry_words (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    word_id  INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    PRIMARY KEY (entry_id, word_id)
);
"""


def db_path() -> Path:
    return Path(os.environ.get("JWA_DB_PATH", DEFAULT_DB))


def init_db() -> None:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
