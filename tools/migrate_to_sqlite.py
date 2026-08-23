#!/usr/bin/env python
"""One-shot migration of the five old stores into `data/bea.db`.

Reads `roster.json`, `people.json`, `recent.json`, `self.md`,
`self_profile.json`, `dreamed.json`, the session files and the Chroma diary
collection, and writes them into the unified database.

Idempotent: re-running it changes nothing that is already there, so it is safe
to run again after a partial failure. `--dry-run` reports what would move
without touching anything.

    uv run python tools/migrate_to_sqlite.py --dry-run
    uv run python tools/migrate_to_sqlite.py
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.memory.embedder import DEFAULT_MODEL, FastEmbedEmbedder  # noqa: E402
from src.core.memory.rag import SOURCE_PERSON  # noqa: E402
from src.core.memory.store import MemoryStore  # noqa: E402


class Report:
    """Counts what moved, so the run says something useful when it finishes."""

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.counts: Dict[str, int] = {}
        self.skipped: Dict[str, int] = {}
        self.problems: List[str] = []

    def moved(self, what: str, n: int = 1) -> None:
        self.counts[what] = self.counts.get(what, 0) + n

    def skip(self, what: str, n: int = 1) -> None:
        self.skipped[what] = self.skipped.get(what, 0) + n

    def problem(self, message: str) -> None:
        self.problems.append(message)

    def render(self) -> str:
        head = "WOULD MIGRATE (dry run)" if self.dry_run else "MIGRATED"
        lines = [head]
        for what, n in sorted(self.counts.items()):
            lines.append(f"  {what:<22} {n}")
        if self.skipped:
            lines.append("already present (skipped)")
            for what, n in sorted(self.skipped.items()):
                lines.append(f"  {what:<22} {n}")
        if self.problems:
            lines.append("problems")
            lines.extend(f"  - {p}" for p in self.problems)
        return "\n".join(lines)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"! could not read {path}: {e}")
        return default


# --- the pieces -------------------------------------------------------------


def migrate_roster(store: MemoryStore, memory_dir: Path, report: Report) -> Dict[str, str]:
    """Roster first: people cards hang off identities, so they must exist."""
    data = load_json(memory_dir / "roster.json", {})
    person_by_identity: Dict[str, str] = {}

    for identity, entry in data.items():
        if store.roster.get(identity):
            report.skip("roster entries")
            continue
        if report.dry_run:
            report.moved("roster entries")
            continue

        platform = entry.get("platform", "unknown")
        native_id = identity.split(":", 1)[1] if ":" in identity else identity
        with store.db.cursor() as cur:
            cur.execute(
                "INSERT INTO identities (identity, person_id, platform, native_id, "
                "display_name, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (identity, None, platform, native_id, entry.get("display_name", ""),
                 float(entry.get("first_seen", time.time())),
                 float(entry.get("last_seen", time.time()))),
            )
            cur.execute(
                "INSERT INTO roster (identity, message_count, donation_total, had_1on1, "
                "marked_by_bea, promoted) VALUES (?, ?, ?, ?, ?, ?)",
                (identity, int(entry.get("message_count", 0)),
                 float(entry.get("donation_total", 0.0)),
                 1 if entry.get("had_1on1") else 0,
                 1 if entry.get("marked_by_bea") else 0,
                 1 if entry.get("promoted") else 0),
            )
            for session_id in entry.get("sessions", []) or []:
                cur.execute(
                    "INSERT OR IGNORE INTO roster_sessions (identity, session_id) VALUES (?, ?)",
                    (identity, session_id),
                )
        if entry.get("person_id"):
            person_by_identity[identity] = entry["person_id"]
        report.moved("roster entries")

    return person_by_identity


def migrate_people(store: MemoryStore, memory_dir: Path, report: Report) -> None:
    data = load_json(memory_dir / "people.json", {})

    for person_id, card in data.items():
        if store.people.get(person_id):
            report.skip("person cards")
            continue
        if report.dry_run:
            report.moved("person cards")
            report.moved("facts", len(card.get("facts", []) or []))
            continue

        names = card.get("display_names", []) or []
        now = time.time()
        with store.db.cursor() as cur:
            cur.execute(
                "INSERT INTO people (person_id, primary_name, attitude, promoted_reason, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (person_id, names[0] if names else "", card.get("bea_attitude", ""),
                 card.get("promoted_reason", ""),
                 float(card.get("created_at", now)), float(card.get("last_updated", now))),
            )
            for identity in card.get("identities", []) or []:
                # an identity the roster never had: keep the link anyway, a card
                # without its identity is unreachable from a perception
                cur.execute(
                    "INSERT INTO identities (identity, person_id, platform, native_id, "
                    "display_name, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(identity) DO UPDATE SET person_id = excluded.person_id",
                    (identity, person_id, identity.split(":", 1)[0],
                     identity.split(":", 1)[-1], names[0] if names else "", now, now),
                )
                cur.execute(
                    "INSERT OR IGNORE INTO roster (identity) VALUES (?)", (identity,)
                )
            for fact in card.get("facts", []) or []:
                cur.execute(
                    "INSERT OR IGNORE INTO facts (person_id, text, source, created_at) "
                    "VALUES (?, ?, 'migrated', ?)", (person_id, fact, now),
                )
                report.moved("facts")
        report.moved("person cards")


def migrate_hot_facts(store: MemoryStore, memory_dir: Path, report: Report) -> None:
    data = load_json(memory_dir / "recent.json", [])
    now = time.time()

    for fact in data:
        text, source = fact.get("text", ""), fact.get("source", "dreamer")
        if not text:
            continue
        if float(fact.get("expires_at", 0)) <= now:
            report.skip("hot facts (expired)")
            continue
        if report.dry_run:
            report.moved("hot facts")
            continue
        store.db.execute(
            "INSERT OR IGNORE INTO hot_facts (text, source, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (text, source, float(fact.get("created_at", now)), float(fact["expires_at"])),
        )
        report.moved("hot facts")


def migrate_self(store: MemoryStore, memory_dir: Path, report: Report) -> None:
    self_path = memory_dir / "self.md"
    if self_path.exists():
        existing = set(store.selflore.facts())
        for line in self_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("- "):
                continue
            fact = line[2:].strip()
            if not fact:
                continue
            if fact in existing:
                report.skip("self facts")
                continue
            if not report.dry_run:
                store.selflore.append_fact(fact)
            report.moved("self facts")

    profile = load_json(memory_dir / "self_profile.json", {})
    if profile:
        if not report.dry_run:
            store.selflore.update_profile(profile)
        report.moved("profile keys", len(profile))


def migrate_sessions(store: MemoryStore, conversations_dir: Path, memory_dir: Path,
                     report: Report) -> None:
    dreamed = set(load_json(memory_dir / "dreamed.json", []))

    for path in sorted(conversations_dir.glob("session_*.json")):
        data = load_json(path, {})
        session_id = data.get("session_id") or path.stem
        started = _parse_time(data.get("start_time")) or path.stat().st_mtime
        if report.dry_run:
            report.moved("sessions")
            continue
        store.sessions.record(session_id, started_at=started)
        if data.get("title"):
            store.sessions.set_title(session_id, data["title"])
        if session_id in dreamed:
            store.sessions.mark_dreamed(session_id)
        report.moved("sessions")

    # sessions that were dreamed but whose file is gone must stay marked, or the
    # dreamer would happily re-dream them from nothing
    for session_id in dreamed:
        if not report.dry_run:
            store.sessions.mark_dreamed(session_id)


def migrate_diaries(store: MemoryStore, chroma_path: Path, report: Report) -> None:
    """Pulls the diary entries out of Chroma and re-embeds them locally.

    The old collection used an English-only model; the text is what matters and
    it is stored in the clear, so re-embedding loses nothing and gains Italian.
    """
    if not chroma_path.exists():
        return
    try:
        import chromadb
    except ImportError:
        report.problem("chromadb is not installed: diary entries were not migrated")
        return

    try:
        client = chromadb.PersistentClient(path=str(chroma_path))
        collections = [c.name for c in client.list_collections()]
    except Exception as e:
        report.problem(f"could not open Chroma at {chroma_path}: {e}")
        return

    for name in ("bea_diary_local", "bea_diary"):
        if name not in collections:
            continue
        try:
            collection = client.get_collection(name)
            data = collection.get(include=["documents", "metadatas"])
        except Exception as e:
            report.problem(f"could not read collection {name}: {e}")
            continue

        ids = data.get("ids") or []
        documents = data.get("documents") or []
        metadatas = data.get("metadatas") or []

        for entry_id, document, meta in zip(ids, documents, metadatas, strict=False):
            if not document:
                continue
            meta = meta or {}
            session_id = str(meta.get("session_id") or entry_id.replace("diary_", ""))
            if store.rag is not None and store.rag.exists("diary", session_id):
                report.skip("diary entries")
                continue
            if report.dry_run:
                report.moved("diary entries")
                continue
            if store.rag is None:
                report.problem("no embedder available: diary entries were not migrated")
                return
            store.rag.remember(
                scope="diary", scope_key=session_id, text=document,
                who=str(meta.get("user_id", "") or ""), source=SOURCE_PERSON,
                tags=str(meta.get("tags", "") or ""),
                created_at=float(meta.get("timestamp") or time.time()),
            )
            report.moved("diary entries")
        break  # the local collection wins; the legacy one was already folded in


def _parse_time(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except Exception:
        return None


# --- entry point ------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default="data/bea.db", help="target database")
    parser.add_argument("--memory-dir", default="data/memory", help="where the json stores live")
    parser.add_argument("--conversations-dir", default="data/conversations")
    parser.add_argument("--chroma-path", default="data/memory_db")
    parser.add_argument("--embed-model", default=DEFAULT_MODEL)
    parser.add_argument("--no-diaries", action="store_true",
                        help="skip the Chroma diary collection (it is the slow part)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would move without writing anything")
    args = parser.parse_args()

    report = Report(args.dry_run)
    memory_dir = Path(args.memory_dir)
    embedder = None if args.no_diaries else FastEmbedEmbedder(args.embed_model)
    store = MemoryStore(args.db if not args.dry_run else ":memory:", embedder=embedder)

    if not args.dry_run and store.rag is not None:
        store.rag.ensure_model(args.embed_model)

    migrate_roster(store, memory_dir, report)
    migrate_people(store, memory_dir, report)
    migrate_hot_facts(store, memory_dir, report)
    migrate_self(store, memory_dir, report)
    migrate_sessions(store, Path(args.conversations_dir), memory_dir, report)
    if not args.no_diaries:
        migrate_diaries(store, Path(args.chroma_path), report)

    store.close()
    print(report.render())
    if not args.dry_run:
        print(f"\nDatabase: {args.db}")
        print("The old json files were left untouched; remove them once you are satisfied.")
    return 1 if report.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
