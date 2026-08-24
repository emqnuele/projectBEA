"""The facade over `bea.db`: people, roster, conversations, hot facts, self-lore.

Keeps the shapes the rest of the code already speaks (`RosterEntry`,
`PersonCard`), so the storage underneath stays swappable.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.memory.db import Database
from src.core.memory.plan import StreamPlan
from src.utils.logger import get_logger

logger = get_logger("bea.memory.store")

# how many distinct sessions before a regular earns a card
REGULAR_SESSION_THRESHOLD = 3

# keep cards lean so they never bloat the prompt
MAX_FACTS_STORED = 12
MAX_FACTS_SHOWN = 6


@dataclass
class RosterEntry:
    """A tally for one identity (platform:native_id).

    Not a memory: no generated content, just counts, so it is cheap to keep for
    every chatter.
    """

    identity: str
    display_name: str
    platform: str
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    message_count: int = 0
    donation_total: float = 0.0
    had_1on1: bool = False
    marked_by_bea: bool = False
    promoted: bool = False
    person_id: Optional[str] = None
    session_count: int = 0


@dataclass
class PersonCard:
    """Rich, deduplicated memory of a regular or otherwise memorable person."""

    person_id: str
    identities: List[str] = field(default_factory=list)
    display_names: List[str] = field(default_factory=list)
    facts: List[str] = field(default_factory=list)
    bea_attitude: str = ""
    promoted_reason: str = ""
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    @property
    def primary_name(self) -> str:
        return self.display_names[0] if self.display_names else self.person_id

    def render(self) -> str:
        line = f"- **{self.primary_name}**"
        if self.bea_attitude:
            line += f" (you: {self.bea_attitude})"
        if self.facts:
            line += ": " + "; ".join(self.facts[-MAX_FACTS_SHOWN:])
        return line


@dataclass
class HotFact:
    """A volatile 'right now' fact that decays. Kept few and always in context."""

    text: str
    created_at: float
    expires_at: float
    source: str

    @property
    def alive(self) -> bool:
        return time.time() < self.expires_at


# --- roster -----------------------------------------------------------------


class RosterStore:
    """The tally for every identity Bea has ever seen."""

    def __init__(self, db: Database):
        self.db = db

    def get(self, identity: str) -> Optional[RosterEntry]:
        row = self.db.query_one(
            "SELECT i.identity, i.display_name, i.platform, i.first_seen, i.last_seen, "
            "       i.person_id, r.message_count, r.donation_total, r.had_1on1, "
            "       r.marked_by_bea, r.promoted "
            "FROM identities i JOIN roster r ON r.identity = i.identity "
            "WHERE i.identity = ?",
            (identity,),
        )
        return self._entry(row) if row else None

    def record(self, *, identity: str, display_name: str, platform: str,
               session_id: Optional[str] = None, is_1on1: bool = False,
               donation: float = 0.0) -> RosterEntry:
        """Registers one sighting. An INSERT, not a rewrite of the whole roster."""
        now = time.time()
        native_id = identity.split(":", 1)[1] if ":" in identity else identity

        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO identities (identity, platform, native_id, display_name, "
                "first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(identity) DO UPDATE SET last_seen = excluded.last_seen, "
                # a blank new name must not wipe the one we have
                "display_name = CASE WHEN excluded.display_name != '' "
                "  THEN excluded.display_name ELSE identities.display_name END",
                (identity, platform, native_id, display_name or "", now, now),
            )
            cur.execute(
                "INSERT INTO roster (identity, message_count, donation_total, had_1on1) "
                "VALUES (?, 1, ?, ?) "
                "ON CONFLICT(identity) DO UPDATE SET "
                "  message_count = roster.message_count + 1, "
                "  donation_total = roster.donation_total + excluded.donation_total, "
                "  had_1on1 = MAX(roster.had_1on1, excluded.had_1on1)",
                (identity, max(0.0, donation), 1 if is_1on1 else 0),
            )
            if session_id:
                cur.execute(
                    "INSERT OR IGNORE INTO roster_sessions (identity, session_id) VALUES (?, ?)",
                    (identity, session_id),
                )
        entry = self.get(identity)
        assert entry is not None  # just written
        return entry

    def mark(self, identity: str) -> Optional[RosterEntry]:
        """Bea explicitly noticed this person (an in-character decision)."""
        self.db.execute("UPDATE roster SET marked_by_bea = 1 WHERE identity = ?", (identity,))
        return self.get(identity)

    def set_promoted(self, identity: str, person_id: str) -> None:
        with self.db.cursor() as cur:
            cur.execute("UPDATE roster SET promoted = 1 WHERE identity = ?", (identity,))
            cur.execute("UPDATE identities SET person_id = ? WHERE identity = ?",
                        (person_id, identity))

    def find_by_name(self, name: str) -> Optional[RosterEntry]:
        """Best-effort name resolution; the most recently seen match wins."""
        low = name.strip().lower()
        if not low:
            return None
        row = self.db.query_one(
            "SELECT identity FROM identities WHERE LOWER(display_name) = ? "
            "ORDER BY last_seen DESC LIMIT 1", (low,),
        ) or self.db.query_one(
            "SELECT identity FROM identities WHERE LOWER(display_name) LIKE ? "
            "ORDER BY last_seen DESC LIMIT 1", (f"%{low}%",),
        )
        return self.get(row["identity"]) if row else None

    def all(self) -> List[RosterEntry]:
        rows = self.db.query(
            "SELECT i.identity, i.display_name, i.platform, i.first_seen, i.last_seen, "
            "       i.person_id, r.message_count, r.donation_total, r.had_1on1, "
            "       r.marked_by_bea, r.promoted "
            "FROM identities i JOIN roster r ON r.identity = i.identity "
            "ORDER BY i.last_seen DESC"
        )
        return [self._entry(r) for r in rows]

    def regulars(self, limit: int = 20) -> List[RosterEntry]:
        """The people she has actually seen around — a query, not a full scan."""
        rows = self.db.query(
            "SELECT i.identity FROM identities i JOIN roster r ON r.identity = i.identity "
            "ORDER BY r.message_count DESC LIMIT ?", (limit,),
        )
        return [e for r in rows if (e := self.get(r["identity"])) is not None]

    def _entry(self, row) -> RosterEntry:
        sessions = self.db.scalar(
            "SELECT COUNT(*) FROM roster_sessions WHERE identity = ?", (row["identity"],)
        )
        return RosterEntry(
            identity=row["identity"],
            display_name=row["display_name"] or "",
            platform=row["platform"],
            first_seen=float(row["first_seen"]),
            last_seen=float(row["last_seen"]),
            message_count=int(row["message_count"]),
            donation_total=float(row["donation_total"]),
            had_1on1=bool(row["had_1on1"]),
            marked_by_bea=bool(row["marked_by_bea"]),
            promoted=bool(row["promoted"]),
            person_id=row["person_id"],
            session_count=int(sessions),
        )


# --- people -----------------------------------------------------------------


class PeopleStore:
    """The rich cards, and the identities that map onto them."""

    def __init__(self, db: Database):
        self.db = db

    def get(self, person_id: str) -> Optional[PersonCard]:
        row = self.db.query_one("SELECT * FROM people WHERE person_id = ?", (person_id,))
        return self._card(row) if row else None

    def get_by_identity(self, identity: str) -> Optional[PersonCard]:
        row = self.db.query_one(
            "SELECT p.* FROM people p JOIN identities i ON i.person_id = p.person_id "
            "WHERE i.identity = ?", (identity,),
        )
        return self._card(row) if row else None

    def find_by_name(self, name: str) -> Optional[PersonCard]:
        low = name.strip().lower()
        if not low:
            return None
        row = self.db.query_one(
            "SELECT * FROM people WHERE LOWER(primary_name) = ?", (low,)
        ) or self.db.query_one(
            "SELECT p.* FROM people p JOIN identities i ON i.person_id = p.person_id "
            "WHERE LOWER(i.display_name) = ? LIMIT 1", (low,)
        ) or self.db.query_one(
            "SELECT * FROM people WHERE LOWER(primary_name) LIKE ? LIMIT 1", (f"%{low}%",)
        )
        return self._card(row) if row else None

    def create_from_entry(self, entry: RosterEntry, reason: str = "",
                          seed_facts: Optional[List[str]] = None,
                          attitude: str = "") -> PersonCard:
        person_id = str(uuid.uuid4())
        now = time.time()
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO people (person_id, primary_name, attitude, promoted_reason, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (person_id, entry.display_name, attitude, reason, now, now),
            )
            cur.execute("UPDATE identities SET person_id = ? WHERE identity = ?",
                        (person_id, entry.identity))
            for fact in seed_facts or []:
                cur.execute(
                    "INSERT OR IGNORE INTO facts (person_id, text, source, created_at) "
                    "VALUES (?, ?, 'seed', ?)", (person_id, fact, now),
                )
        card = self.get(person_id)
        assert card is not None
        return card

    def add_fact(self, person_id: str, fact: str, source: str = "dreamer") -> None:
        fact = (fact or "").strip()
        if not fact or not self.db.query_one(
            "SELECT 1 FROM people WHERE person_id = ?", (person_id,)
        ):
            return
        now = time.time()
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO facts (person_id, text, source, created_at) "
                "VALUES (?, ?, ?, ?)", (person_id, fact, source, now),
            )
            # a card that grows forever eats the prompt: keep the recent facts
            cur.execute(
                "DELETE FROM facts WHERE person_id = ? AND id NOT IN ("
                "  SELECT id FROM facts WHERE person_id = ? ORDER BY id DESC LIMIT ?)",
                (person_id, person_id, MAX_FACTS_STORED),
            )
            cur.execute("UPDATE people SET updated_at = ? WHERE person_id = ?", (now, person_id))

    def set_attitude(self, person_id: str, attitude: str) -> None:
        self.db.execute("UPDATE people SET attitude = ?, updated_at = ? WHERE person_id = ?",
                        (attitude, time.time(), person_id))

    def link_identity(self, person_id: str, identity: str) -> None:
        """Same person, another platform. Never automatic — always a decision."""
        self.db.execute("UPDATE identities SET person_id = ? WHERE identity = ?",
                        (person_id, identity))

    def all(self) -> List[PersonCard]:
        rows = self.db.query("SELECT * FROM people ORDER BY updated_at DESC")
        return [self._card(r) for r in rows]

    def profile_due(self, person_id: str, total: int, *, first: int, every: int) -> bool:
        """Should this person's card be (re)built?

        The first one early (until it exists she has no idea who they are),
        refreshes far rarer.
        """
        row = self.db.query_one(
            "SELECT profiled_count FROM people WHERE person_id = ?", (person_id,)
        )
        if row is None:
            return False
        last = int(row["profiled_count"])
        return total >= first if last == 0 else total - last >= every

    def mark_profiled(self, person_id: str, total: int) -> None:
        self.db.execute(
            "UPDATE people SET profiled_count = ?, updated_at = ? WHERE person_id = ?",
            (total, time.time(), person_id),
        )

    def _card(self, row) -> PersonCard:
        pid = row["person_id"]
        idents = self.db.query(
            "SELECT identity, display_name FROM identities WHERE person_id = ? "
            "ORDER BY last_seen DESC", (pid,),
        )
        facts = self.db.query(
            "SELECT text FROM facts WHERE person_id = ? ORDER BY id", (pid,)
        )
        names = [row["primary_name"]] if row["primary_name"] else []
        names += [r["display_name"] for r in idents
                  if r["display_name"] and r["display_name"] not in names]
        return PersonCard(
            person_id=pid,
            identities=[r["identity"] for r in idents],
            display_names=names,
            facts=[f["text"] for f in facts],
            bea_attitude=row["attitude"] or "",
            promoted_reason=row["promoted_reason"] or "",
            created_at=float(row["created_at"]),
            last_updated=float(row["updated_at"]),
        )


# --- hot facts --------------------------------------------------------------


class HotFacts:
    """'Right now' facts with a TTL. Self-pruning; no sweeper job needed."""

    def __init__(self, db: Database):
        self.db = db

    def add(self, text: str, ttl_seconds: float, source: str = "dreamer") -> None:
        text = (text or "").strip()
        if not text:
            return
        now = time.time()
        self.db.execute(
            "INSERT INTO hot_facts (text, source, created_at, expires_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(text, source) DO UPDATE SET created_at = excluded.created_at, "
            "expires_at = excluded.expires_at",
            (text, source, now, now + ttl_seconds),
        )

    def active(self) -> List[HotFact]:
        rows = self.db.query(
            "SELECT text, source, created_at, expires_at FROM hot_facts "
            "WHERE expires_at > ? ORDER BY created_at DESC", (time.time(),),
        )
        return [HotFact(r["text"], float(r["created_at"]), float(r["expires_at"]), r["source"])
                for r in rows]

    def clear_source(self, source: str) -> None:
        self.db.execute("DELETE FROM hot_facts WHERE source = ?", (source,))

    def prune(self) -> int:
        rows = self.db.query("SELECT id FROM hot_facts WHERE expires_at <= ?", (time.time(),))
        if rows:
            self.db.execute("DELETE FROM hot_facts WHERE expires_at <= ?", (time.time(),))
        return len(rows)

    def render(self, max_items: int = 6) -> str:
        facts = self.active()[:max_items]
        if not facts:
            return ""
        lines = "\n".join(f"- {f.text}" for f in facts)
        return f"[RIGHT NOW]\n{lines}"


# --- self -------------------------------------------------------------------


class SelfLore:
    """What Bea has learned about HERSELF — separate from her soul, which never moves."""

    def __init__(self, db: Database):
        self.db = db

    def facts(self) -> List[str]:
        return [r["text"] for r in self.db.query("SELECT text FROM self_facts ORDER BY id")]

    def append_fact(self, fact: str) -> bool:
        fact = (fact or "").strip().lstrip("- ").strip()
        if not fact:
            return False
        before = self.db.scalar("SELECT COUNT(*) FROM self_facts")
        self.db.execute(
            "INSERT OR IGNORE INTO self_facts (text, created_at) VALUES (?, ?)",
            (fact, time.time()),
        )
        return self.db.scalar("SELECT COUNT(*) FROM self_facts") > before

    def render_for_prompt(self, max_facts: int = 15) -> str:
        """Capped view: a growing self-lore must never take over the context."""
        facts = self.facts()[-max_facts:]
        return "\n".join(f"- {f}" for f in facts) if facts else ""

    def render(self) -> str:
        return self.render_for_prompt(max_facts=1000)

    def profile(self) -> Dict[str, Any]:
        return {r["key"]: r["value"] for r in self.db.query("SELECT key, value FROM self_profile")}

    def update_profile(self, data: Dict[str, Any]) -> None:
        for key, value in (data or {}).items():
            if value in (None, ""):
                continue
            self.db.execute(
                "INSERT INTO self_profile (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(key), str(value)),
            )


# --- conversations ----------------------------------------------------------


class Conversations:
    """Per-channel history and its rolling summary."""

    def __init__(self, db: Database):
        self.db = db

    def add(self, *, conversation_key: str, role: str, content: str,
            platform: str = "", channel_id: str = "", author_identity: Optional[str] = None,
            display_name: str = "", ts: Optional[float] = None) -> int:
        return self.db.execute(
            "INSERT INTO messages (conversation_key, platform, channel_id, author_identity, "
            "display_name, role, content, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (conversation_key, platform, channel_id, author_identity, display_name,
             role, content, ts if ts is not None else time.time()),
        )

    def history(self, conversation_key: str, limit: int = 20) -> List[Dict[str, Any]]:
        """The last `limit` messages, oldest first (reading order)."""
        rows = self.db.query(
            "SELECT display_name, role, content, ts, author_identity FROM messages "
            "WHERE conversation_key = ? ORDER BY id DESC LIMIT ?", (conversation_key, limit),
        )
        return [dict(r) for r in reversed(rows)]

    def count(self, conversation_key: str) -> int:
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM messages WHERE conversation_key = ?", (conversation_key,)
        ))

    def message_count_for(self, identity: str) -> int:
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM messages WHERE author_identity = ? AND role = 'user'",
            (identity,),
        ))

    def messages_by(self, identity: str, limit: int = 60) -> List[str]:
        rows = self.db.query(
            "SELECT content FROM messages WHERE author_identity = ? AND role = 'user' "
            "ORDER BY id DESC LIMIT ?", (identity, limit),
        )
        return [r["content"] for r in reversed(rows)]

    def participants(self, conversation_key: str, limit: int = 10) -> List[str]:
        rows = self.db.query(
            "SELECT DISTINCT author_identity FROM messages WHERE conversation_key = ? "
            "AND author_identity IS NOT NULL ORDER BY id DESC LIMIT ?",
            (conversation_key, limit),
        )
        return [r["author_identity"] for r in rows]

    def seconds_since_bea_spoke(self, conversation_key: str,
                                now: Optional[float] = None) -> Optional[float]:
        ts = self.db.scalar(
            "SELECT MAX(ts) FROM messages WHERE conversation_key = ? AND role = 'bea'",
            (conversation_key,), default=None,
        )
        return None if ts is None else (now if now is not None else time.time()) - float(ts)

    def recent_activity(self, conversation_key: str, window_seconds: float = 120.0,
                        now: Optional[float] = None) -> int:
        """`now` is injectable so callers with their own clock stay consistent."""
        reference = now if now is not None else time.time()
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM messages WHERE conversation_key = ? AND role = 'user' "
            "AND ts >= ?", (conversation_key, reference - window_seconds),
        ))

    # --- summaries ----------------------------------------------------------

    def summary(self, conversation_key: str) -> str:
        return str(self.db.scalar(
            "SELECT summary FROM summaries WHERE conversation_key = ?",
            (conversation_key,), default="",
        ))

    def save_summary(self, conversation_key: str, summary: str) -> None:
        self.db.execute(
            "INSERT INTO summaries (conversation_key, summary, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(conversation_key) DO UPDATE SET summary = excluded.summary, "
            "updated_at = excluded.updated_at",
            (conversation_key, summary, time.time()),
        )

    def summary_due(self, conversation_key: str, every: int) -> bool:
        """Have `every` messages passed since the last summary?

        A delta, not a modulo: the counter jumps by more than one, so an exact
        multiple would be stepped over and never fire.
        """
        total = self.count(conversation_key)
        last = int(self.db.scalar(
            "SELECT last_count FROM summaries WHERE conversation_key = ?",
            (conversation_key,), default=0,
        ))
        return total - last >= every

    def mark_summarized(self, conversation_key: str) -> None:
        self.db.execute(
            "INSERT INTO summaries (conversation_key, last_count, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(conversation_key) DO UPDATE SET last_count = excluded.last_count, "
            "updated_at = excluded.updated_at",
            (conversation_key, self.count(conversation_key), time.time()),
        )

    def prune(self, keep_per_conversation: int = 500) -> int:
        """Caps history per conversation. A twitch channel would grow forever."""
        removed = 0
        for row in self.db.query("SELECT DISTINCT conversation_key FROM messages"):
            key = row["conversation_key"]
            excess = self.count(key) - keep_per_conversation
            if excess <= 0:
                continue
            self.db.execute(
                "DELETE FROM messages WHERE id IN ("
                "  SELECT id FROM messages WHERE conversation_key = ? ORDER BY id ASC LIMIT ?)",
                (key, excess),
            )
            removed += excess
        return removed


# --- sessions ---------------------------------------------------------------


class Sessions:
    def __init__(self, db: Database):
        self.db = db

    def record(self, session_id: str, started_at: Optional[float] = None) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO sessions (session_id, started_at) VALUES (?, ?)",
            (session_id, started_at if started_at is not None else time.time()),
        )

    def set_title(self, session_id: str, title: str) -> None:
        self.db.execute(
            "INSERT INTO sessions (session_id, title, started_at) VALUES (?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET title = excluded.title",
            (session_id, title, time.time()),
        )

    def mark_dreamed(self, session_id: str) -> None:
        self.db.execute(
            "INSERT INTO sessions (session_id, started_at, dreamed) VALUES (?, ?, 1) "
            "ON CONFLICT(session_id) DO UPDATE SET dreamed = 1",
            (session_id, time.time()),
        )

    def dreamed(self) -> set:
        return {r["session_id"] for r in
                self.db.query("SELECT session_id FROM sessions WHERE dreamed = 1")}

    def last_ended_at(self, exclude: Optional[str] = None) -> Optional[float]:
        row = self.db.query_one(
            "SELECT MAX(started_at) AS t FROM sessions WHERE session_id != ?",
            (exclude or "",),
        )
        return float(row["t"]) if row and row["t"] is not None else None


# --- the whole thing --------------------------------------------------------


class MemoryStore:
    """One handle for everything Bea remembers."""

    def __init__(self, path: str = "data/bea.db", embedder=None, **rag_kwargs):
        self.db = Database(path).init()
        self.roster = RosterStore(self.db)
        self.people = PeopleStore(self.db)
        self.hot = HotFacts(self.db)
        self.selflore = SelfLore(self.db)
        self.conversations = Conversations(self.db)
        self.sessions = Sessions(self.db)
        self.plan = StreamPlan(self.db)

        self.rag = None
        if embedder is not None:
            from src.core.memory.rag import Rag
            self.rag = Rag(self.db, embedder, **rag_kwargs)

    def close(self) -> None:
        self.db.close()
