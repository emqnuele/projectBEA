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
