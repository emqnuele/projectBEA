"""Who earns a rich memory, and why.

Pure decisions over the roster tally: no IO, the store does that. Only the
people who made themselves matter earn a card, so the prompt never fills up
with strangers.
"""

import time
from typing import List, Optional

from src.core.memory.store import (
    MAX_FACTS_SHOWN,
    MAX_FACTS_STORED,
    REGULAR_SESSION_THRESHOLD,
    PersonCard,
    RosterEntry,
)
from src.utils.logger import get_logger

logger = get_logger("bea.skills.social.people")

# the identity synthesized for someone known only by a name
NAMED_PREFIX = "named:"

__all__ = [
    "should_promote", "promotion_reason", "record_person", "resolve_or_create_card",
    "promote_entry", "repair_duplicate_cards", "card_for_identity", "is_placeholder",
    "merge_cards", "NAMED_PREFIX",
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
            identity=f"{NAMED_PREFIX}{name.lower()}", display_name=name, platform="named",
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
        return promote_entry(roster, people, entry)
    return None


def resolve_or_create_card(roster, people, name: str) -> Optional[PersonCard]:
    """Bea decided this person matters: always persist (force-promote)."""
    return record_person(roster, people, name, force=True)


def promote_entry(roster, people, entry: RosterEntry, *, reason: str = "",
                  seed_facts: Optional[List[str]] = None) -> Optional[PersonCard]:
    """The single choke point for minting a card from a roster tally.

    Three callers used to mint three ways — the dream by name, the live prompt
    and a strong reaction by identity — and minting by identity is how one
    human on two surfaces became two cards. So the name is checked first: an
    exact case-insensitive match on a card this tally shared a session with,
    or on a card known only by that name, links the identity to that card
    instead of minting. Exact, never substring or guess: two accounts sharing
    a first name and never an evening stay two cards.
    """
    if entry.promoted:
        return people.get_by_identity(entry.identity)
    twin = _same_person(people, entry)
    if twin is not None:
        roster.set_promoted(entry.identity, twin.person_id)
        logger.info(f"SocialMemory: linked {entry.identity} to {twin.primary_name}.")
        return people.get(twin.person_id)
    card = people.create_from_entry(
        entry, reason=reason or promotion_reason(entry), seed_facts=seed_facts)
    roster.set_promoted(entry.identity, card.person_id)
    logger.info(f"SocialMemory: promoted {entry.display_name} ({card.promoted_reason}).")
    return card


def card_for_identity(roster, people, entry: RosterEntry) -> Optional[PersonCard]:
    """The card an account already belongs to, or the one it has just earned.

    What the dream needs once it knows exactly who spoke: never a second
    sighting (the live path already counted it), only the card. An account
    that has not earned one yet still lands on a card known only by its
    exact name, because that card is about this person and the facts the
    dream is holding belong on it.
    """
    card = people.get_by_identity(entry.identity)
    if card is not None:
        return card
    if should_promote(entry):
        return promote_entry(roster, people, entry)
    placeholder = _placeholder_named(people, entry.display_name)
    if placeholder is None:
        return None
    roster.set_promoted(entry.identity, placeholder.person_id)
    logger.info(f"SocialMemory: linked {entry.identity} to {placeholder.primary_name}.")
    return people.get(placeholder.person_id)


def is_placeholder(card: PersonCard) -> bool:
    """A card known only by a name: no account on any platform behind it.

    Minted by `remember_person` or the dream for someone she only heard
    about, or left with no identity at all by a relink. It has no sessions
    to prove who it is, so the first account wearing exactly its name is
    taken to be that person.
    """
    return all(i.startswith(NAMED_PREFIX) for i in card.identities)


def _placeholder_named(people, name: str) -> Optional[PersonCard]:
    name = (name or "").strip()
    if len(name) < 2:
        return None
    return next((c for c in people.named_exactly(name) if is_placeholder(c)), None)


def _same_person(people, entry: RosterEntry) -> Optional[PersonCard]:
    """A card this tally already belongs to, or None.

    Same display name spelled exactly the same, and either a session in
    common — the same human reaches her from two surfaces in one sitting far
    more often than two homonyms share both a name and an evening — or a
    card with no account behind it, which has no sessions to share.
    """
    name = (entry.display_name or "").strip()
    if len(name) < 2:
        return None
    cards = people.named_exactly(name)
    for card in cards:
        if entry.identity in (card.identities or []):
            return card
    for card in cards:
        if _shared_session(people.db, entry.identity, set(card.identities or [])):
            return card
    return next((c for c in cards if is_placeholder(c)), None)


def _shared_session(db, identity: str, known: set) -> bool:
    """Did this identity show up in a session one of the card's did?"""
    if not known:
        return False
    mine = {r["session_id"] for r in db.query(
        "SELECT session_id FROM roster_sessions WHERE identity = ?", (identity,))}
    if not mine:
        return False
    placeholders = ",".join("?" for _ in known)
    theirs = {r["session_id"] for r in db.query(
        f"SELECT DISTINCT session_id FROM roster_sessions "
        f"WHERE identity IN ({placeholders})", tuple(known))}
    return bool(mine & theirs)


def repair_duplicate_cards(roster, people) -> int:
    """Merges cards sharing one exact name that are provably one person.

    Runs at every boot, not once: it is cheap (a GROUP BY over the cards) and
    idempotent, and a duplicate can still arrive from a restored backup or a
    database written by an older version. Provably means a shared session,
    or one of the two being known only by name (see `is_placeholder`). The
    card with more facts survives; facts move over (UNIQUE drops the dupes),
    identities repoint at the survivor, an empty attitude fills in, warmth
    and profile counters keep the max. Returns how many cards were folded.
    Two accounts that never shared a session are left alone: they may be two
    homonyms, and merging those is worse than a duplicate.
    """
    merged = 0
    for low in _duplicate_names(people):
        cards = people.named_exactly(low)
        if len(cards) < 2:
            continue
        cards.sort(key=lambda c: (-len(c.facts), c.created_at))
        survivor = cards[0]
        for loser in cards[1:]:
            if loser.person_id == survivor.person_id:
                continue
            if not _provably_one(people, survivor, loser):
                continue
            _fold(people, survivor, loser)
            updated = people.get(survivor.person_id)
            survivor = updated if updated is not None else survivor
            merged += 1
    return merged


def _provably_one(people, survivor: PersonCard, loser: PersonCard) -> bool:
    if is_placeholder(survivor) or is_placeholder(loser):
        return True
    return any(_shared_session(people.db, i, set(survivor.identities))
               for i in loser.identities)


def merge_cards(people, survivor: PersonCard, loser: PersonCard) -> Optional[PersonCard]:
    """Folds `loser` into `survivor` and returns the survivor as it is now."""
    if survivor.person_id == loser.person_id:
        return survivor
    _fold(people, survivor, loser)
    return people.get(survivor.person_id)


def _duplicate_names(people) -> List[str]:
    """Lowercased primary names held by more than one card."""
    return [r["low"] for r in people.db.query(
        "SELECT LOWER(primary_name) AS low FROM people "
        "GROUP BY low HAVING COUNT(*) > 1")]


def _fold(people, survivor: PersonCard, loser: PersonCard) -> None:
    """Folds a duplicate card into its survivor."""
    now = time.time()
    with people.db.cursor() as cur:
        cur.execute(
            "INSERT OR IGNORE INTO facts (person_id, text, source, created_at) "
            "SELECT ?, text, source, created_at FROM facts WHERE person_id = ?",
            (survivor.person_id, loser.person_id),
        )
        cur.execute("UPDATE identities SET person_id = ? WHERE person_id = ?",
                    (survivor.person_id, loser.person_id))
        if not (survivor.bea_attitude or "").strip() and (loser.bea_attitude or "").strip():
            cur.execute("UPDATE people SET attitude = ? WHERE person_id = ?",
                        (loser.bea_attitude, survivor.person_id))
        # warmth comes off the card already decayed to now, so the clock has
        # to move with it: left where it was, inherited warmth would keep
        # decaying from a reading taken weeks ago and fade far too fast
        cur.execute(
            "UPDATE people SET warmth = MAX(warmth, ?), warmth_at = ?, "
            "profiled_count = MAX(profiled_count, ?), updated_at = ? "
            "WHERE person_id = ?",
            (loser.warmth, now, _profiled_count(people, loser.person_id), now,
             survivor.person_id),
        )
        cur.execute("DELETE FROM facts WHERE person_id = ?", (loser.person_id,))
        cur.execute("DELETE FROM people WHERE person_id = ?", (loser.person_id,))
    _prune_facts(people, survivor.person_id)


def _profiled_count(people, person_id: str) -> int:
    return int(people.db.scalar(
        "SELECT profiled_count FROM people WHERE person_id = ?", (person_id,),
        default=0))


def _prune_facts(people, person_id: str) -> None:
    """A merged card keeps the newest facts, never more than the cap."""
    people.db.execute(
        "DELETE FROM facts WHERE person_id = ? AND id NOT IN ("
        "  SELECT id FROM facts WHERE person_id = ? ORDER BY id DESC LIMIT ?)",
        (person_id, person_id, MAX_FACTS_STORED),
    )
