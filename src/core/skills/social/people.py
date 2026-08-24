"""Who earns a rich memory, and why.

Pure decisions over the roster tally: no IO, the store does that. Only the
people who made themselves matter earn a card, so the prompt never fills up
with strangers.
"""

from typing import Optional

from src.core.memory.store import (
    MAX_FACTS_SHOWN,
    MAX_FACTS_STORED,
    REGULAR_SESSION_THRESHOLD,
    PersonCard,
    RosterEntry,
)
from src.utils.logger import get_logger

logger = get_logger("bea.skills.social.people")

__all__ = [
    "should_promote", "promotion_reason", "record_person", "resolve_or_create_card",
    "PersonCard", "RosterEntry", "REGULAR_SESSION_THRESHOLD",
    "MAX_FACTS_STORED", "MAX_FACTS_SHOWN",
]


def should_promote(entry: RosterEntry) -> bool:
    """A tally earns a rich card when the person made themselves matter:
    money, becoming a regular, a real 1:1, or Bea deciding so in character."""
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
                  *, force: bool = False) -> Optional[PersonCard]:
    """Records a sighting of a named person; returns their card only if earned.

    A `named:<name>` identity is synthesized for people the platform gave no
    stable id for. `force=True` is her explicit decision and promotes at once;
    otherwise the normal thresholds apply.
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
    if entry is None:
        return None

    if should_promote(entry):
        card = people.create_from_entry(entry, reason=promotion_reason(entry))
        roster.set_promoted(entry.identity, card.person_id)
        return card
    return None


def resolve_or_create_card(roster, people, name: str) -> Optional[PersonCard]:
    """Bea decided this person matters: always persist (force-promote)."""
    return record_person(roster, people, name, force=True)
