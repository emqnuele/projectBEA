import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

from src.core.skills.social.roster import RosterEntry
from src.utils.logger import get_logger

logger = get_logger("bea.skills.social.people")

# how many distinct sessions before a regular earns a card
REGULAR_SESSION_THRESHOLD = 3

# keep cards lean so they never bloat the prompt
MAX_FACTS_STORED = 12
MAX_FACTS_SHOWN = 6


def should_promote(entry: RosterEntry) -> bool:
    """A tally earns a rich PersonCard when the person made themselves matter:
    money, becoming a regular, a real 1:1, or Bea deciding so in-character."""
    if entry.promoted:
        return False
    return (
        entry.donation_total > 0
        or entry.marked_by_bea
        or entry.had_1on1
        or entry.session_count >= REGULAR_SESSION_THRESHOLD
    )


def promotion_reason(entry: RosterEntry) -> str:
    if entry.donation_total > 0:
        return "donated"
    if entry.marked_by_bea:
        return "you marked them"
    if entry.had_1on1:
        return "had a 1:1 with you"
    if entry.session_count >= REGULAR_SESSION_THRESHOLD:
        return "a regular"
    return "memorable"


def record_person(roster, people, name: str, session_id: Optional[str] = None,
                  *, force: bool = False):
    """Record a sighting of a named person; return their card ONLY if they earn one.

    Bea knows who she's talking to even if the platform never gave us a stable id
    (e.g. someone she names in the UI or a transcript). We synthesize a
    `named:<name>` identity so the tally always persists. `force=True` is Bea's
    explicit in-character decision (the `remember_person` tool, trigger #4) and
    promotes immediately. Without it the normal thresholds apply — so the dreamer
    builds a tally for everyone it names but only mints a card for real regulars
    (3+ sessions), donors, 1:1s, or people Bea marked. Returns a PersonCard or None.
    """
    name = name.strip()
    if not name:
        return None

    card = people.find_by_name(name)
    if card:
        return card

    entry = roster.find_by_name(name)
    if entry is None:
        entry = roster.record(
            identity=f"named:{name.lower()}", display_name=name, platform="named",
            session_id=session_id,
        )
    elif session_id:
        # another sighting in a distinct session grows the "regular" signal
        entry = roster.record(
            identity=entry.identity, display_name=name, platform=entry.platform,
            session_id=session_id,
        )

    if force:
        roster.mark(entry.identity)
    entry = roster.get(entry.identity)

    if should_promote(entry):
        card = people.create_from_entry(entry, reason=promotion_reason(entry))
        roster.set_promoted(entry.identity, card.person_id)
        return card
    return None


def resolve_or_create_card(roster, people, name: str):
    """Bea explicitly decided this person matters: always persist (force-promote)."""
    return record_person(roster, people, name, force=True)


@dataclass
class PersonCard:
    """Rich, deduplicated memory of a regular/memorable person."""

    person_id: str
    identities: List[str]
    display_names: List[str]
    facts: List[str] = field(default_factory=list)
    bea_attitude: str = ""           # how Bea feels about them
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


class PeopleStore:
    """JSON-backed map person_id -> PersonCard, with an identity index."""

    def __init__(self, path: str = "data/memory/people.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cards: Dict[str, PersonCard] = {}
        self._by_identity: Dict[str, str] = {}  # identity -> person_id
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for pid, data in raw.items():
                card = PersonCard(**data)
                self._cards[pid] = card
                for ident in card.identities:
                    self._by_identity[ident] = pid
            logger.info(f"PeopleStore: loaded {len(self._cards)} cards.")
        except Exception as e:
            logger.error(f"PeopleStore: failed to load: {e}")

    def _save(self) -> None:
        try:
            data = {k: asdict(v) for k, v in self._cards.items()}
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"PeopleStore: failed to save: {e}")

    def get_by_identity(self, identity: str) -> Optional[PersonCard]:
        pid = self._by_identity.get(identity)
        return self._cards.get(pid) if pid else None

    def find_by_name(self, name: str) -> Optional[PersonCard]:
        name_low = name.strip().lower()
        for card in self._cards.values():
            if any(name_low == n.lower() for n in card.display_names):
                return card
        for card in self._cards.values():
            if any(name_low in n.lower() for n in card.display_names):
                return card
        return None

    def create_from_entry(self, entry: RosterEntry, reason: str = "",
                          seed_facts: Optional[List[str]] = None,
                          attitude: str = "") -> PersonCard:
        card = PersonCard(
            person_id=str(uuid.uuid4()),
            identities=[entry.identity],
            display_names=[entry.display_name],
            facts=list(seed_facts or []),
            bea_attitude=attitude,
            promoted_reason=reason,
        )
        self._cards[card.person_id] = card
        self._by_identity[entry.identity] = card.person_id
        self._save()
        return card

    def add_fact(self, person_id: str, fact: str) -> None:
        card = self._cards.get(person_id)
        if not card or not fact.strip():
            return
        if fact not in card.facts:
            card.facts.append(fact)
            # keep only the most recent facts so a card never grows unbounded
            card.facts = card.facts[-MAX_FACTS_STORED:]
            card.last_updated = time.time()
            self._save()

    def set_attitude(self, person_id: str, attitude: str) -> None:
        card = self._cards.get(person_id)
        if card:
            card.bea_attitude = attitude
            card.last_updated = time.time()
            self._save()

    def all(self) -> List[PersonCard]:
        return list(self._cards.values())
