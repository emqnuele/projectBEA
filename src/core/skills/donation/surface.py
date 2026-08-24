"""Donations: the one input that always deserves a reaction.

A webhook (StreamElements, Ko-fi, Streamlabs, a twitch cheer) becomes a
perception carrying the amount in `Author.extra`, which `is_addressed` turns
into an unconditional REACT.

A donor is also promoted to a person card immediately, so the next thing she
says already knows who they are.
"""

import time
from typing import Any, Dict, List, Optional

from src.core.agent.tools import Tool
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import Skill
from src.utils.logger import get_logger

logger = get_logger("bea.skills.donation")

# how long a donation stays a "right now" fact she can bring up
HOT_FACT_TTL = 3 * 3600.0


class DonationSkill(Skill):
    """Turns an incoming donation into a perception, a tally and a person card."""

    name = "donation"
    skill_name = "donations"
    platform = "donation"

    def initialize(self) -> None:
        self._seen: Dict[str, float] = {}   # webhook id -> when, for de-duplication

    @property
    def skill_config(self) -> dict:
        return self.config.skills.get("donations", {})

    def secret(self) -> str:
        import os
        return os.getenv("DONATION_SECRET", "") or self.skill_config.get("secret", "")

    def authorized(self, provided: Optional[str]) -> bool:
        """Anyone who can reach the endpoint could fake a donation; a shared
        secret is the minimum. With none configured the endpoint stays open,
        which is fine on loopback and nowhere else."""
        expected = self.secret()
        return not expected or provided == expected

    # --- the event ----------------------------------------------------------

    def receive(self, *, name: str, amount: float, currency: str = "EUR",
                message: str = "", platform: str = "donation",
                donor_id: Optional[str] = None, event_id: Optional[str] = None,
                ) -> Optional[Perception]:
        """Records a donation and puts it on the bus. Returns None on a duplicate.

        Providers retry webhooks; without de-duplication a retry would be a second
        donation, a second thank-you and a wrong total.
        """
        name = (name or "someone").strip() or "someone"
        amount = max(0.0, float(amount or 0))
        if event_id and event_id in self._seen:
            logger.info(f"Donation {event_id} already handled; ignoring the retry.")
            return None
        if event_id:
            self._seen[event_id] = time.time()
            self._prune_seen()

        author = Author(
            platform=platform,
            native_id=str(donor_id or name.lower()),
            display_name=name,
            extra={"amount": amount, "currency": currency, "message": message},
        )
        self._remember(author, amount, currency, message)

        rendered = f"[{name}] donated {amount:g} {currency}"
        if message:
            rendered += f' and said: "{message}"'
        perception = Perception(
            kind=PerceptionKind.CHAT,
            surface=self.name,
            content=rendered,
            salience=1.0,
            meta={"amount": amount, "currency": currency, "tallied": True,
                  "conversation_key": "stage"},
            author=author,
        )
        self.bus.put(perception)
        logger.info(f"Donation: {name} gave {amount:g} {currency}.")
        return perception

    def _remember(self, author: Author, amount: float, currency: str, message: str) -> None:
        """Tally, promote, and drop a hot fact she can mention for a while."""
        memory = getattr(self.context, "memory", None)
        if memory is None:
            return
        try:
            session = getattr(getattr(self.context, "history_manager", None), "session_id", None)
            entry = memory.roster.record(
                identity=author.identity, display_name=author.display_name,
                platform=author.platform, session_id=session, donation=amount,
            )
            card = memory.people.get_by_identity(author.identity)
            if card is None:
                # money is the strongest promotion trigger there is: no waiting
                # for the dreamer, she knows who they are on the next line
                card = memory.people.create_from_entry(entry, reason="donated")
                memory.roster.set_promoted(entry.identity, card.person_id)
            memory.people.add_fact(
                card.person_id, f"donated {amount:g} {currency}", source="donation",
            )
            if message:
                memory.people.add_fact(card.person_id, f'said: "{message}"', source="donation")
            memory.hot.add(
                f"{author.display_name} just donated {amount:g} {currency}",
                HOT_FACT_TTL, source="live",
            )
        except Exception as e:
            logger.error(f"Could not record the donation: {e}")

    def _prune_seen(self, keep_seconds: float = 86400.0) -> None:
        cutoff = time.time() - keep_seconds
        self._seen = {k: v for k, v in self._seen.items() if v >= cutoff}

    # --- prompt context -----------------------------------------------------

    async def start(self) -> None:
        await super().start()

    @property
    def context_section(self) -> Optional[str]:
        if not self.active:
            return None
        return (
            "## DONATIONS\n"
            "People can give you money. When it happens you always react — money is "
            "one of the very few things that genuinely delights you. Say their name."
        )

    def tools(self) -> List[Tool]:
        if not self.active:
            return []
        return [Tool(
            "recall_donors",
            "Check who has given you money, and how much. Use it when you want to "
            "single someone out — or shame everyone who hasn't.",
            {"type": "object", "properties": {
                "limit": {"type": "integer", "description": "how many, default 5"}},
             "required": []},
            self._tool_recall_donors,
        )]

    def _tool_recall_donors(self, limit: int = 5) -> str:
        memory = getattr(self.context, "memory", None)
        if memory is None:
            return "You can't remember anything right now."
        donors = [e for e in memory.roster.all() if e.donation_total > 0]
        if not donors:
            return "Nobody has ever given you a cent. Outrageous."
        donors.sort(key=lambda e: e.donation_total, reverse=True)
        lines = [f"- {e.display_name}: {e.donation_total:g}" for e in donors[:max(1, limit)]]
        return "Who has paid you:\n" + "\n".join(lines)

    def live_state(self) -> Optional[str]:
        return None

    def conversation_tools(self, channel_id: Optional[str],
                           reply_to: Optional[str] = None) -> List[Any]:
        return []
