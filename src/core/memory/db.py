"""SQLite handle: one file, schema bootstrapped on open.

Operations are serialized by a lock because db work happens both on the event
loop and inside `asyncio.to_thread`. sqlite-vec is loaded when available and
accelerates recall; everything still works without it.
"""

import sqlite3
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Union

from src.utils.logger import get_logger

logger = get_logger("bea.memory.db")

# what sqlite3 will actually bind. Deliberately not `Iterable`: a generator
# satisfies that and then fails at the driver, which has to be able to count
# the parameters before it runs the statement.
Params = Union[Sequence[Any], Mapping[str, Any]]

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# how long to wait for another writer before giving up. Without it the default
# is zero: two threads reaching the file at once and one of them simply raises,
# which is a lost memory rather than a slow one
BUSY_TIMEOUT_MS = 5000

# 64MB of page cache, as the negative-kibibyte spelling sqlite wants
CACHE_SIZE_KIB = -65536

# windows is stingier about mapped memory than the others, and a map it will
# not give back is a map that falls back to ordinary reads anyway
MMAP_BYTES = 128 * 1024 * 1024 if sys.platform == "win32" else 256 * 1024 * 1024

# (table, column, type) for columns added after a table already exists:
# CREATE TABLE IF NOT EXISTS will not add them, so they need a guarded ALTER
_MIGRATIONS: List[tuple] = [
    ("messages", "addressee_identity", "TEXT NOT NULL DEFAULT ''"),
    # the stream grew three columns when it stopped being only what was said
    ("messages", "kind", "TEXT NOT NULL DEFAULT 'chat'"),
    ("messages", "surface", "TEXT NOT NULL DEFAULT ''"),
    ("messages", "session_id", "TEXT NOT NULL DEFAULT ''"),
    # in the schema but never here, so any database older than it crashed the
    # profiler on every conversation turn
    ("people", "profiled_count", "INTEGER NOT NULL DEFAULT 0"),
    ("people", "warmth", "REAL NOT NULL DEFAULT 0"),
    ("people", "warmth_at", "REAL NOT NULL DEFAULT 0"),
]


class Database:
    def __init__(self, path: str = "data/bea.db") -> None:
        self.path = str(path)
        self.vec_enabled = False
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

    # --- lifecycle ----------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        conn.execute(f"PRAGMA cache_size={CACHE_SIZE_KIB}")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute(f"PRAGMA mmap_size={MMAP_BYTES}")
        self._try_load_vec(conn)
        self._conn = conn
        return conn

    def _try_load_vec(self, conn: sqlite3.Connection) -> None:
        try:
            conn.enable_load_extension(True)
            import sqlite_vec

            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
            self.vec_enabled = True
            logger.info("sqlite-vec loaded: accelerated recall available.")
        except Exception as e:
            self.vec_enabled = False
            logger.info(f"sqlite-vec unavailable ({e}); recall falls back to python cosine.")

    def init(self) -> "Database":
        conn = self.connect()
        # columns before the script, not after: the script creates indexes, an
        # index names columns, and an index over a column an older file does
        # not have yet makes sqlite raise instead of skipping the statement.
        # On a fresh file there is nothing to migrate and the script does it all.
        self._apply_migrations()
        with self._lock:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            conn.commit()
        logger.info(f"Memory schema ready ({self.path}).")
        return self

    def _apply_migrations(self) -> None:
        """Adds missing columns to tables that already exist. Idempotent."""
        for table, column, ctype in _MIGRATIONS:
            with self._lock:
                conn = self.connect()
                existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                if not existing or column in existing:
                    continue
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ctype}")
                conn.commit()
                logger.info(f"Migration: added {table}.{column}")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # --- serialized access --------------------------------------------------

    @contextmanager
    def cursor(self):
        """A cursor for writing: commits on the way out, rolls back on a raise."""
        conn = self.connect()
        with self._lock:
            cur = conn.cursor()
            try:
                yield cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()

    @contextmanager
    def reading(self):
        """A cursor for reading. No commit, because there is nothing to commit.

        Worth almost nothing in time — 1.3µs a read became 1.1µs — and worth
        having anyway: committing after a SELECT says the statement might have
        written something, and the next person to read this code deserves to be
        told the truth about which of these two helpers changes the file.
        """
        conn = self.connect()
        with self._lock:
            cur = conn.cursor()
            try:
                yield cur
            finally:
                cur.close()

    def execute(self, sql: str, params: Params = ()) -> int:
        """Runs a write; returns the new rowid, or 0 when the statement made none."""
        with self.cursor() as cur:
            cur.execute(sql, params)
            # only an INSERT has one; an UPDATE or a DELETE leaves it undefined
            return cur.lastrowid or 0

    def executemany(self, sql: str, seq: Iterable[Params]) -> int:
        """Bulk write: one commit for the whole batch."""
        with self.cursor() as cur:
            cur.executemany(sql, seq)
            return cur.rowcount

    def query(self, sql: str, params: Params = ()) -> List[sqlite3.Row]:
        with self.reading() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def query_one(self, sql: str, params: Params = ()) -> Optional[sqlite3.Row]:
        with self.reading() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def scalar(self, sql: str, params: Params = (), default: Any = 0) -> Any:
        row = self.query_one(sql, params)
        if row is None:
            return default
        value = row[0]
        return default if value is None else value
