"""Being somewhere on purpose: reaching people, and meaning to.

Every other skill answers where it was spoken to. This one is what lets her
start something: write to a person wherever they are, and decide to come back
to it later. It is the difference between a chat endpoint and someone who says
"I'll ask you tomorrow" and then does.
"""

import time
from typing import List, Optional

from src.core.agent.tools import Tool
from src.core.persona import persona_of
from src.core.skills.base import Skill
from src.core.social.reach import Reach
from src.utils.logger import get_logger

logger = get_logger("bea.skills.presence")

# she is allowed to be forgetful, not to build a backlog she will never clear
MAX_OPEN_INTENTIONS = 20

# a reminder she means to act on, not a calendar: a week out is a different tool
MAX_DELAY_MINUTES = 7 * 24 * 60


class PresenceSkill(Skill):
    """Her address book and her own intentions, as tools."""

    name = "social:presence"
    skill_name = None  # core: without it she can only ever answer

    def initialize(self) -> None:
        memory = self.context.memory
        self.agenda = memory.agenda
        # the registry itself, not a snapshot: skills register one after another
        # and this one is built in the middle of that loop
        self.reach = Reach(memory=memory, surfaces=self.context.surface_registry,
                           persona=persona_of(self.config))

    @property
    def _cross_platform(self) -> bool:
        return bool(getattr(self.config, "rhythm", {}).get("cross_platform", True))

    # --- what she is reminded of --------------------------------------------

    def live_state(self) -> Optional[str]:
        if not self.active:
            return None
        return self.agenda.render() or None

    @property
    def context_section(self) -> Optional[str]:
        if not self.active:
            return None
        lines = [
            "## PEOPLE, NOT CHANNELS",
            "You know people, and people are in more than one place. The same person "
            "can be on Discord and on Telegram, and it is the same person.",
            "- `remember_to` is how you hold on to something past the end of a "
            "conversation. Use it the way you would say 'I'll ask you tomorrow' — and "
            "then you actually will, because it comes back to you.",
        ]
        if self._cross_platform:
            lines.insert(2, (
                "- `message_person` writes to someone privately, wherever you can reach "
                "them. Leaving a call and then texting them about it is a normal thing "
                "to do, not a trick."
            ))
            lines.insert(3, "- `where_can_i_reach` tells you where someone is before you try.")
        return "\n".join(lines)

    # --- tools ---------------------------------------------------------------

    def tools(self) -> List[Tool]:
        if not self.active:
            return []
        tools = [Tool(
            "remember_to",
            "Decide to do something later. It comes back to you when the time is up, "
            "and you decide then what to actually say.",
            {"type": "object", "properties": {
                "what": {"type": "string", "description": "a note to yourself"},
                "in_minutes": {"type": "integer", "description": "how long from now"},
                "who": {"type": "string", "description": "optional: who it is about"}},
             "required": ["what", "in_minutes"]},
            self._tool_remember_to,
        )]
        if self._cross_platform:
            tools.extend([
                Tool(
                    "where_can_i_reach",
                    "Where you can write to someone: every account of theirs you know, "
                    "and whether that platform is on right now.",
                    {"type": "object", "properties": {"who": {"type": "string"}},
                     "required": ["who"]},
                    self._tool_where,
                ),
                Tool(
                    "message_person",
                    "Write to someone privately, wherever you can reach them. Each LINE "
                    "becomes its own message.",
                    {"type": "object", "properties": {
                        "who": {"type": "string"},
                        "text": {"type": "string"},
                        "platform": {"type": "string",
                                     "description": "optional: discord, telegram…"}},
                     "required": ["who", "text"]},
                    self._tool_message,
                ),
            ])
        return tools

    async def _tool_where(self, who: str) -> str:
        return self.reach.describe(who)

    async def _tool_message(self, who: str, text: str, platform: str = "") -> str:
        result = await self.reach.message(who, text, platform=platform)
        if not result.ok:
            return f"FAILED: {result.error}"
        return f"Written to {who} on {result.platform}."

    async def _tool_remember_to(self, what: str, in_minutes: int, who: str = "") -> str:
        try:
            minutes = int(in_minutes)
        except (TypeError, ValueError):
            return "FAILED: in_minutes must be a number."
        if minutes <= 0:
            return "FAILED: that is in the past. Just do it now."
        if minutes > MAX_DELAY_MINUTES:
            return "FAILED: that is too far off to hold on to."

        person_id = ""
        if who:
            card = self.reach.find(who)
            if card is None:
                return f"FAILED: you don't know anyone called '{who}'."
            person_id = card.person_id

        if len(self.agenda.pending()) >= MAX_OPEN_INTENTIONS:
            return "FAILED: you already have more open intentions than you will get to."

        item = self.agenda.add(what, due_ts=time.time() + minutes * 60, person_id=person_id)
        if item is None:
            return "FAILED: nothing to remember."
        return f"Noted. It comes back to you in {minutes} minutes."
