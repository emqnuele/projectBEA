import datetime
from typing import Dict, List, Optional

from src.core.agent.tools import Tool
from src.core.perception.types import Perception, PerceptionKind
from src.core.skills.base import Skill
from src.core.skills.social.roster import RosterStore, RosterEntry
from src.core.skills.social.people import (
    PeopleStore, PersonCard, should_promote, promotion_reason, resolve_or_create_card,
)
from src.utils.logger import get_logger

logger = get_logger("bea.skills.social")

# never describe more than a handful of people at once
MAX_CARDS_INJECTED = 5


class SocialMemory(Skill):
    """Bea's memory of the people around her.

    Everyone gets a cheap tally (roster); only the ones who make themselves
    matter — donors, regulars, real 1:1s, or people Bea decides to remember —
    earn a rich PersonCard. Cards for whoever is in the current batch are injected
    so Bea recognises people instead of searching for them.
    """

    name = "social"
    skill_name = "social_memory"

    def initialize(self) -> None:
        cfg = self.config.skills.get("social_memory", {})
        self.roster = RosterStore(cfg.get("roster_path", "data/memory/roster.json"))
        self.people = PeopleStore(cfg.get("people_path", "data/memory/people.json"))

    # --- per-batch hook: tally + promote + inject --------------------------

    def context_for(self, batch) -> Optional[str]:
        if not self.active:
            return None

        session_id = getattr(getattr(self.context, "history_manager", None), "session_id", None)
        present_cards: Dict[str, PersonCard] = {}

        for p in batch:
            author = getattr(p, "author", None)
            if not author or author.is_owner:
                continue

            is_1on1 = p.kind == PerceptionKind.VOICE or bool(p.meta.get("is_dm"))
            donation = float(author.extra.get("amount", 0) or 0)

            entry = self.roster.record(
                identity=author.identity,
                display_name=author.display_name,
                platform=author.platform,
                session_id=session_id,
                is_1on1=is_1on1,
                donation=donation,
            )
            self._maybe_promote(entry)

            card = self.people.get_by_identity(author.identity)
            if card:
                present_cards[card.person_id] = card

        if not present_cards:
            return None

        # cap how many people we describe at once so the prompt stays lean
        cards = list(present_cards.values())[:MAX_CARDS_INJECTED]
        lines = "\n".join(c.render() for c in cards)
        return f"[WHO YOU'RE TALKING TO]\n{lines}"

    def _maybe_promote(self, entry: RosterEntry) -> Optional[PersonCard]:
        if not should_promote(entry):
            return None
        reason = promotion_reason(entry)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        card = self.people.create_from_entry(
            entry, reason=reason, seed_facts=[f"first noticed {today} ({reason})"]
        )
        self.roster.set_promoted(entry.identity, card.person_id)
        logger.info(f"SocialMemory: promoted {entry.display_name} ({reason}).")
        return card

    # --- tools --------------------------------------------------------------

    def tools(self) -> List[Tool]:
        if not self.active:
            return []
        return [
            Tool(
                "remember_person",
                "Decide to remember someone you're talking to (because they stood out, "
                "you like them, or they annoy you). Give their display name and what to "
                "remember about them.",
                {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "note": {"type": "string", "description": "a fact worth keeping"},
                    "attitude": {"type": "string", "description": "how you feel about them (optional)"},
                }, "required": ["name", "note"]},
                self._tool_remember_person,
            ),
            Tool(
                "recall_person",
                "Recall what you know about a specific person by their display name.",
                {"type": "object", "properties": {"name": {"type": "string"}},
                 "required": ["name"]},
                self._tool_recall_person,
            ),
        ]

    def _tool_remember_person(self, name: str, note: str, attitude: str = "") -> str:
        # Bea decided to remember them, so this always persists (creates the card
        # by name if the platform never gave us a stable identity)
        card = resolve_or_create_card(self.roster, self.people, name)
        if not card:
            return f"Couldn't pin down '{name}'."
        self.people.add_fact(card.person_id, note)
        if attitude:
            self.people.set_attitude(card.person_id, attitude)
        return f"Noted about {card.primary_name}: {note}"

    def _tool_recall_person(self, name: str) -> str:
        card = self.people.find_by_name(name)
        if card:
            return card.render()
        entry = self.roster.find_by_name(name)
        if entry:
            return (f"{entry.display_name}: seen {entry.message_count} times across "
                    f"{entry.session_count} session(s). Nothing memorable noted yet.")
        return f"You don't know anyone called '{name}'."
