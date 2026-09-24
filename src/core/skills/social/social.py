from typing import Dict, List, Optional, Tuple

from src.core.agent.tools import Tool
from src.core.memory.store import PersonCard, RosterEntry
from src.core.perception.types import PerceptionKind
from src.core.skills.base import Skill
from src.core.skills.social.people import (
    merge_cards,
    promote_entry,
    promotion_reason,
    resolve_or_create_card,
    should_promote,
)
from src.core.timeline import today_in_timezone
from src.utils.logger import get_logger

logger = get_logger("bea.skills.social")

# never describe more than a handful of people at once
MAX_CARDS_INJECTED = 5

# names cost almost nothing each, but a busy twitch chat is a hundred of them
MAX_NAMES_INJECTED = 10


class SocialMemory(Skill):
    """Bea's memory of the people around her.

    Everyone gets a cheap tally; donors, regulars, real 1:1s and whoever she
    decides to remember earn a rich card. Cards for the current batch are
    injected, so she recognises people instead of looking them up.
    """

    name = "social"
    skill_name = "social_memory"

    def initialize(self) -> None:
        # one store: promoting someone is a single transaction
        memory = self.brain.memory
        self.roster = memory.roster
        self.people = memory.people
        # who is in front of her right now, for tools that act on the speaker
        self._last_speakers: List[Tuple[str, str]] = []

    # --- per-batch hook: tally + promote + inject --------------------------

    def context_for(self, batch) -> Optional[str]:
        if not self.active:
            return None

        session_id = getattr(getattr(self.context, "history_manager", None), "session_id", None)
        present_cards: Dict[str, PersonCard] = {}
        # everyone in the room, card or no card: a person she has not met yet
        # used to be invisible in her context, which is how a regular gets made
        present_names: Dict[str, str] = {}

        for p in batch:
            author = getattr(p, "author", None)
            if not author or author.is_owner:
                continue
            present_names.setdefault(author.identity, author.display_name)

            if p.meta.get("tallied"):
                # a high-volume surface counts every message itself, including the
                # ones that never reach here: counting again would double them
                card = self.people.get_by_identity(author.identity)
                if card:
                    present_cards[card.person_id] = card
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

        self._last_speakers = list(present_names.items())

        blocks = []

        if present_cards:
            # cap how many people we describe at once so the prompt stays lean
            cards = list(present_cards.values())[:MAX_CARDS_INJECTED]
            blocks.append(
                "[WHO YOU'RE TALKING TO]\n" + "\n".join(c.render() for c in cards)
            )

        known = {i for c in present_cards.values() for i in c.identities}
        strangers = [name for identity, name in present_names.items() if identity not in known]
        if strangers:
            shown = strangers[:MAX_NAMES_INJECTED]
            line = ", ".join(shown)
            if len(strangers) > len(shown):
                line += f" and {len(strangers) - len(shown)} more"
            blocks.append(
                f"[WHO'S HERE]\n{line} — you don't have a card on any of them yet."
            )

        return "\n\n".join(blocks) or None

    def _maybe_promote(self, entry: RosterEntry) -> Optional[PersonCard]:
        if not should_promote(entry):
            return None
        reason = promotion_reason(entry)
        today = today_in_timezone(str(getattr(self.config, "timezone", "") or ""))
        return promote_entry(self.roster, self.people, entry, reason=reason,
                             seed_facts=[f"first noticed {today} ({reason})"])

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
            Tool(
                "link_person",
                "Declare that someone talking to you right now is a person you "
                "already know under another name (a minecraft player telling "
                "you who they are, a new account of a regular). Only when they "
                "told you so themselves — never a guess.",
                {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "speaking_as": {
                        "type": "string",
                        "description": "the name they appear with right now, "
                                       "to pick among several speakers (optional)",
                    },
                }, "required": ["name"]},
                self._tool_link_person,
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

    def _tool_link_person(self, name: str, speaking_as: str = "") -> str:
        """Links whoever is in front of her to an existing card.

        Links only, never creates: remembering someone new is remember_person's
        job, and someone she never heard of is a no-op rather than a card.
        """
        card = self.people.find_by_name((name or "").strip())
        if not card:
            return f"You don't know anyone called '{name}'."
        found = self._speaker_identity((speaking_as or "").strip())
        if found is None:
            return "I can't tell who is speaking right now — say who you mean."
        identity, display = found
        previous = self.people.get_by_identity(identity)
        self.roster.link(identity=identity, display_name=display,
                         platform=identity.split(":")[0] if ":" in identity else "",
                         person_id=card.person_id)
        self._fold_if_orphaned(previous, card)
        return f"Noted: {display} is {card.primary_name}."

    def _fold_if_orphaned(self, previous: Optional[PersonCard], card: PersonCard) -> None:
        """The card the speaker was on, folded in once nothing points at it.

        Left behind it keeps its facts and no identity: nothing reads it
        again, the dashboard shows it forever, and the boot repair cannot
        tell which name it belonged with.
        """
        if previous is None or previous.person_id == card.person_id:
            return
        left = self.people.get(previous.person_id)
        if left is not None and not left.identities:
            merge_cards(self.people, card, left)
            logger.info(f"SocialMemory: folded {left.primary_name} into {card.primary_name}.")

    def _speaker_identity(self, speaking_as: str) -> Optional[Tuple[str, str]]:
        """The (identity, display name) talking right now, or None.

        One speaker in front of her needs no disambiguation; several do, by
        the name they appear with.
        """
        speakers = list(getattr(self, "_last_speakers", []) or [])
        if speaking_as:
            low = speaking_as.lower()
            for identity, display in speakers:
                if low in (display or "").lower() or low in identity.lower():
                    return identity, display
            return None
        if len(speakers) == 1:
            return speakers[0]
        return None
