import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set

from src.utils.logger import get_logger

logger = get_logger("bea.skills.social.roster")


@dataclass
class RosterEntry:
    """A lightweight tally for one identity (platform:native_id).

    This is NOT a memory — it carries no LLM-generated content. It just counts
    so the system can decide WHO is worth a rich PersonCard. Cheap to keep for
    everyone, even thousands of chatters.
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
    sessions: List[str] = field(default_factory=list)  # distinct session ids seen in

    @property
    def session_count(self) -> int:
        return len(self.sessions)


class RosterStore:
    """JSON-backed map identity -> RosterEntry. No vectors, no model calls."""

    def __init__(self, path: str = "data/memory/roster.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: Dict[str, RosterEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for identity, data in raw.items():
                self._entries[identity] = RosterEntry(**data)
            logger.info(f"RosterStore: loaded {len(self._entries)} identities.")
        except Exception as e:
            logger.error(f"RosterStore: failed to load: {e}")

    def _save(self) -> None:
        try:
            data = {k: asdict(v) for k, v in self._entries.items()}
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"RosterStore: failed to save: {e}")

    def get(self, identity: str) -> Optional[RosterEntry]:
        return self._entries.get(identity)

    def record(self, *, identity: str, display_name: str, platform: str,
               session_id: Optional[str] = None, is_1on1: bool = False,
               donation: float = 0.0) -> RosterEntry:
        """Register one observation of an identity. Returns the updated entry."""
        entry = self._entries.get(identity)
        if entry is None:
            entry = RosterEntry(identity=identity, display_name=display_name, platform=platform)
            self._entries[identity] = entry

        now = time.time()
        entry.last_seen = now
        entry.display_name = display_name or entry.display_name
        entry.message_count += 1
        if is_1on1:
            entry.had_1on1 = True
        if donation > 0:
            entry.donation_total += donation
        if session_id and session_id not in entry.sessions:
            entry.sessions.append(session_id)

        self._save()
        return entry

    def mark(self, identity: str) -> Optional[RosterEntry]:
        """Bea explicitly noticed this person (in-character mark)."""
        entry = self._entries.get(identity)
        if not entry:
            return None
        entry.marked_by_bea = True
        self._save()
        return entry

    def set_promoted(self, identity: str, person_id: str) -> None:
        entry = self._entries.get(identity)
        if entry:
            entry.promoted = True
            entry.person_id = person_id
            self._save()

    def find_by_name(self, name: str) -> Optional[RosterEntry]:
        """Best-effort resolve a display name to an entry (most recent match)."""
        name_low = name.strip().lower()
        matches = [e for e in self._entries.values() if e.display_name.lower() == name_low]
        if not matches:
            matches = [e for e in self._entries.values() if name_low in e.display_name.lower()]
        if not matches:
            return None
        return max(matches, key=lambda e: e.last_seen)

    def all(self) -> List[RosterEntry]:
        return list(self._entries.values())
