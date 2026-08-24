"""Twitch chat: high volume, so most of it is texture rather than input.

Every message updates the roster and feeds the attention gate, but only what
passes the gate reaches the mind. The rest becomes a live "chat is doing N
messages a minute and keeps saying X" line that costs nothing.

Cheers carry `bits`, which makes them a donation, which always deserves an
answer.
"""

import time
from collections import Counter, deque
from typing import Deque, List, Optional, Tuple

from src.core.agent.tools import Tool
from src.core.skills.platform import PlatformSkill
from src.core.skills.twitch.irc import ChatLine, TwitchIRC
from src.utils.logger import get_logger

logger = get_logger("bea.skills.twitch")

# window over which "how busy is chat" is measured
PULSE_WINDOW = 60.0

# words too common to say anything about what chat is on about
STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "to", "of", "in", "on",
    "it", "this", "that", "you", "your", "for", "with", "not", "so", "just", "like",
    "che", "non", "per", "con", "una", "uno", "del", "della", "come", "sono", "hai",
    "ma", "poi", "solo", "anche", "quando", "cosa", "questo", "quella", "sei",
    "lol", "lmao", "xd", "omg",
})

MIN_TERM_LEN = 4
TOP_TERMS = 3

# bits are worth a hundredth of a dollar each; the number is what matters, not
# the currency — a cheer is money and money always earns a reaction
BITS_TO_UNITS = 0.01


class TwitchSkill(PlatformSkill):
    """Reads a twitch channel; writes back only if a token was configured."""

    name = "chat:twitch"
    skill_name = "twitch"
    platform = "twitch"
    supports_reactions = False
    # chat is the audience in the room with her: she answers it out loud
    scoped_conversations = False

    def initialize(self) -> None:
        super().initialize()
        self.irc: Optional[TwitchIRC] = None
        # (timestamp, text) of everything seen recently, for the pulse line
        self._recent: Deque[Tuple[float, str]] = deque(maxlen=500)

    @property
    def skill_config(self) -> dict:
        return self.config.skills.get("twitch", {})

    def _token(self) -> str:
        import os
        return os.getenv("TWITCH_OAUTH_TOKEN", "") or self.skill_config.get("oauth_token", "")

    def _trigger_words(self) -> List[str]:
        return list(getattr(self.config, "attention", {}).get("trigger_words", ["bea"]))

    # --- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        if not self.enabled:
            logger.info("TwitchSkill stays inactive (twitch toggle off).")
            return
        channel = str(self.skill_config.get("channel", "") or "")
        if not channel:
            logger.error("Twitch channel not configured.")
            return

        self.irc = TwitchIRC(
            channel,
            nick=str(self.skill_config.get("nick", "") or ""),
            token=self._token(),
            on_message=self._on_message,
        )
        await self.irc.start()
        self.active = True
        logger.info(f"TwitchSkill started on #{channel}.")

    async def stop(self) -> None:
        self.active = False
        if self.irc:
            await self.irc.stop()
            self.irc = None
        logger.info("TwitchSkill stopped.")

    # --- senses -------------------------------------------------------------

    async def _on_message(self, line: ChatLine) -> None:
        if not self.active:
            return
        self._recent.append((time.time(), line.text))

        author = self.build_author(
            line.user_id or line.nick, line.name,
            subscriber=line.is_subscriber, moderator=line.is_moderator,
            **({"amount": line.bits * BITS_TO_UNITS, "currency": "bits"} if line.bits else {}),
        )

        # every message counts, whether or not it ever reaches the mind: that is
        # what makes a regular a regular
        self._tally(author)

        self.perceive_text(
            line.text,
            author=author,
            channel_id=line.channel,
            # chat is a room, not a conversation: low by default so only the
            # gate's presence score (or her name) pulls her in
            salience=0.9 if line.bits else 0.4,
            meta={"tallied": True, "bits": line.bits},
        )

    def _tally(self, author) -> None:
        memory = getattr(self.context, "memory", None)
        if memory is None:
            return
        try:
            session = getattr(getattr(self.context, "history_manager", None), "session_id", None)
            memory.roster.record(
                identity=author.identity, display_name=author.display_name,
                platform=self.platform, session_id=session,
                donation=float(author.extra.get("amount", 0) or 0),
            )
        except Exception as e:
            logger.warning(f"Twitch tally failed: {e}")

    # --- chat as texture ----------------------------------------------------

    def pulse(self) -> str:
        """How chat *feels* right now, in one line. No model call, always current.

        This is the piece that makes a high-volume chat affordable: Bea is aware
        of it continuously without deliberating over any of it.
        """
        cutoff = time.time() - PULSE_WINDOW
        recent = [text for ts, text in self._recent if ts >= cutoff]
        if not recent:
            return ""
        terms = self._top_terms(recent)
        line = f"chat: {len(recent)} messages in the last minute"
        return f"{line}, mostly about {', '.join(terms)}" if terms else line

    @staticmethod
    def _top_terms(messages: List[str], limit: int = TOP_TERMS) -> List[str]:
        counter: Counter = Counter()
        for text in messages:
            for word in text.lower().split():
                word = word.strip(".,!?;:\"'()[]")
                if len(word) >= MIN_TERM_LEN and word not in STOPWORDS:
                    counter[word] += 1
        # a word one person repeated is not what chat is about
        return [word for word, count in counter.most_common(limit) if count > 1]

    def live_state(self) -> Optional[str]:
        if not self.active:
            return None
        pulse = self.pulse()
        return f"[TWITCH CHAT]\n{pulse}" if pulse else None

    # --- transport ----------------------------------------------------------

    async def send_text(self, channel_id: str, text: str,
                        reply_to: Optional[str] = None) -> bool:
        if self.irc is None:
            return False
        return await self.irc.say(text)

    # --- prompt context -----------------------------------------------------

    @property
    def context_section(self) -> Optional[str]:
        if not self.active:
            return None
        return (
            "## TWITCH CHAT\n"
            "Your stream chat is scrolling past. You read it the way a streamer does: "
            "you take in the mood, and you pick out the lines that are actually for "
            "you. You are not expected to answer messages one by one — nobody could, "
            "and trying looks broken.\n"
            "- `twitch_say` writes one line in chat.\n"
            "- Someone cheering bits gave you money. Notice it."
        )

    def tools(self) -> List[Tool]:
        if not self.active or not self._token():
            return []
        return [Tool(
            "twitch_say",
            "Say one line in your twitch chat.",
            {"type": "object", "properties": {"text": {"type": "string"}},
             "required": ["text"]},
            self._tool_say,
        )]

    async def _tool_say(self, text: str) -> str:
        sent = await self.deliver(self.skill_config.get("channel", ""), text)
        return f"Said it ({len(sent)} line(s))." if sent else "FAILED: nothing was sent."

