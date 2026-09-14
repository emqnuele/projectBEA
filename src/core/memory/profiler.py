"""Background passes that keep the person cards and summaries fresh.

Two count-triggered jobs on the `background` model, both run after she has
already answered so neither is in the way of a reply: the person profile and
the rolling conversation summary. Waiting for the nightly dreamer instead would
leave a regular a stranger all evening.
"""

import asyncio
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("bea.memory.profiler")

# messages from one person before their first card gets built
FIRST_PROFILE_AT = 20
# and before it is refreshed
REPROFILE_EVERY = 50

# how much history each pass reads
PROFILE_WINDOW = 60

PERSON_PROMPT = """You keep short notes about the people around you.
From the messages below, extract what is worth remembering about this person.

Return JSON only:
{"facts": ["short factual note", ...], "attitude": "one short line on how you feel about them"}

Rules:
- at most 4 facts, one short line each
- only things they actually revealed; never invent
- skip anything already obvious or generic
- "attitude" is optional; leave it out if nothing changed
"""


class Profiler:
    def __init__(self, llm, store, *, first_profile_at: int = FIRST_PROFILE_AT,
                 reprofile_every: int = REPROFILE_EVERY):
        self.llm = llm
        self.store = store
        self.first_profile_at = first_profile_at
        self.reprofile_every = reprofile_every

    # --- people -------------------------------------------------------------

    async def maybe_profile(self, identity: str) -> bool:
        """Rebuilds this person's card if enough of their messages piled up."""
        card = self.store.people.get_by_identity(identity)
        if card is None:
            return False
        total = self.store.conversations.message_count_for(identity)
        if not self.store.people.profile_due(
            card.person_id, total, first=self.first_profile_at, every=self.reprofile_every
        ):
            return False

        messages = self.store.conversations.messages_by(identity, limit=PROFILE_WINDOW)
        if not messages:
            return False

        known = "; ".join(card.facts) or "(nothing yet)"
        payload = (f"PERSON: {card.primary_name}\nWHAT YOU ALREADY KNOW: {known}\n\n"
                   "THEIR MESSAGES:\n" + "\n".join(f"- {m}" for m in messages))
        data = await self._ask(PERSON_PROMPT, payload)
        if data is None:
            return False

        for fact in (data.get("facts") or [])[:4]:
            text = str(fact).strip()
            if text:
                self.store.people.add_fact(card.person_id, text, source="profiler")
        attitude = str(data.get("attitude", "")).strip()
        if attitude:
            self.store.people.set_attitude(card.person_id, attitude)

        # marked even on an empty result: otherwise every message retries
        self.store.people.mark_profiled(card.person_id, total)
        logger.info(f"Profiler: refreshed the card for {card.primary_name}.")
        return True

    # --- shared -------------------------------------------------------------

    async def _ask(self, system: str, payload: str) -> Optional[dict]:
        try:
            data = await self.llm.complete_json(payload, system)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Profiler: generation failed: {e}")
            return None
        return data if isinstance(data, dict) else None
