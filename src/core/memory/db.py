"""SQLite handle: one file, schema bootstrapped on open.

Operations are serialized by a lock because db work happens both on the event
loop and inside `asyncio.to_thread`. sqlite-vec is loaded when available and
accelerates recall; everything still works without it.
"""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, List, Optional

from src.utils.logger import get_logger

logger = get_logger("bea.memory.db")

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# (table, column, type) for columns added after a table already exists:
# CREATE TABLE IF NOT EXISTS will not add them, so they need a guarded ALTER
_MIGRATIONS: List[tuple] = []


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
        with self._lock:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            conn.commit()
        self._apply_migrations()
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

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Runs a write; returns lastrowid."""
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.lastrowid

    def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> int:
        """Bulk write: one commit for the whole batch."""
        with self.cursor() as cur:
            cur.executemany(sql, seq)
            return cur.rowcount

    def query(self, sql: str, params: Iterable[Any] = ()) -> List[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def scalar(self, sql: str, params: Iterable[Any] = (), default: Any = 0) -> Any:
        row = self.query_one(sql, params)
        if row is None:
            return default
        value = row[0]
        return default if value is None else value
