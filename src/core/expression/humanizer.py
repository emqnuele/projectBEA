"""Human delivery of written messages: split by line, then type them out.

Each line becomes its own message, sent after a delay proportional to its
length with a "typing…" indicator in between. A paragraph arriving instantly in
one block reads as a machine.

`split` and `delay_for` are pure; `deliver` takes injected callables so a test
can record what went out.
"""

import asyncio
import random
import re
from typing import Awaitable, Callable, List, NamedTuple, Optional

# discord's per-message ceiling. Telegram allows 4096 and twitch only 500, so
# each platform overrides it — this is the safe default, not the truth
HARD_LIMIT = 2000

# past this, a single line gets broken by sentence — more human than one wall
SOFT_SPLIT_THRESHOLD = 350


class Chunk(NamedTuple):
    """One message to send."""

    kind: str
    value: str


def _hard_split(text: str, limit: int = HARD_LIMIT) -> List[str]:
    """Breaks text over the platform limit, preferring sentence boundaries."""
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if len(current) + len(sentence) + 1 <= limit:
            current = f"{current} {sentence}".strip()
            continue
        if current:
            chunks.append(current)
        # a single sentence can still be over the limit: cut it bluntly
        while len(sentence) > limit:
            chunks.append(sentence[:limit])
            sentence = sentence[limit:]
        current = sentence
    if current:
        chunks.append(current)
    return chunks


def _soft_split_long(line: str, limit: int = HARD_LIMIT) -> List[str]:
    """A long line, still under the limit: split by sentence to look human."""
    if len(line) <= min(SOFT_SPLIT_THRESHOLD, limit):
        return [line]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
    return sentences if len(sentences) > 1 else [line]


class TextHumanizer:
    def __init__(
        self,
        chars_per_second: float = 18.0,
        max_typing_delay: float = 4.0,
        min_delay: float = 0.3,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Optional[random.Random] = None,
        hard_limit: int = HARD_LIMIT,
    ) -> None:
        self.cps = max(1.0, chars_per_second)
        self.max_delay = max_typing_delay
        self.min_delay = min_delay
        self.hard_limit = max(1, int(hard_limit))
        self._sleep = sleep
        self._rng = rng or random.Random()

    # --- pure ---------------------------------------------------------------

    def split(self, text: str) -> List[Chunk]:
        """Model text to a list of messages: one line, one message."""
        if not text or not text.strip():
            return []
        chunks: List[Chunk] = []
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            for soft in _soft_split_long(line, self.hard_limit):
                chunks.extend(Chunk("text", h) for h in _hard_split(soft, self.hard_limit))
        return chunks

    def delay_for(self, text: str) -> float:
        base = len(text) / self.cps
        variance = self._rng.uniform(0.7, 1.3)
        return min(self.max_delay, max(self.min_delay, base * variance))

    # --- delivery -----------------------------------------------------------

    async def deliver(
        self,
        text: str,
        *,
        send_text: Callable[[str], Awaitable],
        send_typing: Optional[Callable[[], Awaitable]] = None,
    ) -> List[str]:
        """Sends `text` as several messages, with typing and delays between them.

        Returns what was actually sent: a chunk that failed to send never
        happened, and history must not record it.
        """
        sent: List[str] = []

        for chunk in self.split(text):
            if send_typing is not None:
                try:
                    await send_typing()
                except Exception:  # typing is cosmetic: never fail a message over it
                    pass
            await self._sleep(self.delay_for(chunk.value))
            try:
                await send_text(chunk.value)
            except Exception:
                break
            sent.append(chunk.value)

        return sent
