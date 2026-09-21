"""Opening a database written by an older version must not be a hard error.

The schema script and the column migrations are two halves of the same open,
and the order between them is load-bearing: the script creates indexes, an
index names columns, and a column a migration has not added yet makes sqlite
raise rather than skip.
"""

import sqlite3

from src.core.memory.db import Database

# `messages` exactly as it was before the stream grew kind/surface/session_id
OLD_MESSAGES = """
CREATE TABLE messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_key TEXT NOT NULL,
    platform         TEXT NOT NULL DEFAULT '',
    channel_id       TEXT NOT NULL DEFAULT '',
    author_identity  TEXT,
    display_name     TEXT NOT NULL DEFAULT '',
    role             TEXT NOT NULL,
    content          TEXT NOT NULL,
    ts               REAL NOT NULL
);
"""


def _old_database(path) -> str:
    conn = sqlite3.connect(str(path))
    conn.executescript(OLD_MESSAGES)
    conn.execute(
        "INSERT INTO messages (conversation_key, role, content, ts) VALUES (?, ?, ?, ?)",
        ("discord:999", "user", "ciao bea", 1.0),
    )
    conn.commit()
    conn.close()
    return str(path)


def test_an_older_database_opens_and_keeps_what_was_in_it(tmp_path):
    path = _old_database(tmp_path / "bea.db")

    db = Database(path).init()
    try:
        columns = {r["name"] for r in db.query("PRAGMA table_info(messages)")}
        assert {"kind", "surface", "session_id", "addressee_identity"} <= columns
        assert db.scalar("SELECT COUNT(*) FROM messages") == 1
    finally:
        db.close()


def test_a_row_written_before_the_stream_existed_reads_back(tmp_path):
    path = _old_database(tmp_path / "bea.db")

    db = Database(path).init()
    try:
        row = db.query_one("SELECT * FROM messages")
        assert row["content"] == "ciao bea"
        assert row["kind"] == "chat"
        assert row["session_id"] == ""
    finally:
        db.close()


# `summaries` exactly as the schema used to create it, with a stale row inside
OLD_SUMMARIES = """
CREATE TABLE summaries (
    conversation_key TEXT PRIMARY KEY,
    summary          TEXT NOT NULL DEFAULT '',
    last_count       INTEGER NOT NULL DEFAULT 0,
    updated_at       REAL NOT NULL
);
"""


def _database_with_summaries(path) -> str:
    conn = sqlite3.connect(str(path))
    conn.executescript(OLD_MESSAGES + OLD_SUMMARIES)
    conn.execute(
        "INSERT INTO messages (conversation_key, role, content, ts) VALUES (?, ?, ?, ?)",
        ("discord:999", "user", "ciao bea", 1.0),
    )
    conn.execute(
        "INSERT INTO summaries (conversation_key, summary, last_count, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("discord:999", "stale recap", 30, 1.0),
    )
    conn.commit()
    conn.close()
    return str(path)


def _tables(db) -> set:
    return {r["name"] for r in db.query(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_an_update_drops_the_retired_summaries_table_but_keeps_the_stream(tmp_path):
    path = _database_with_summaries(tmp_path / "bea.db")

    db = Database(path).init()
    try:
        assert "summaries" not in _tables(db)
        assert db.scalar("SELECT COUNT(*) FROM messages") == 1
    finally:
        db.close()


def test_a_fresh_database_never_creates_the_retired_table(tmp_path):
    db = Database(str(tmp_path / "bea.db")).init()
    try:
        assert "summaries" not in _tables(db)
    finally:
        db.close()


def test_the_drop_is_a_noop_on_the_second_open(tmp_path):
    path = _database_with_summaries(tmp_path / "bea.db")

    first = Database(path).init()
    first.close()
    second = Database(path).init()
    try:
        assert "summaries" not in _tables(second)
        assert second.scalar("SELECT COUNT(*) FROM messages") == 1
    finally:
        second.close()
