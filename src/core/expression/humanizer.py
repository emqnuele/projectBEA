"""Human delivery of written messages: split by line, then type them out.

The model produces several lines; each becomes its own message, sent after a
delay proportional to its length with random variance and a "typing…" indicator
in between. On Discord or Telegram this is the whole difference between a person
and a webhook — a paragraph arriving instantly in one block reads as a machine.

`split` and `delay_for` are pure and testable; `deliver` takes injected
callables so a test can record exactly what went out.

Ported from riba/engine/humanizer.py, without the sticker layer (Bea is
primarily a voice, and stickers are telegram-shaped).
"""

import asyncio
import random
import re
from typing import Awaitable, Callable, List, NamedTuple, Optional

# discord's per-message ceiling; telegram's is 4096, so this is the safe one
HARD_LIMIT = 2000

# past this, a single line gets broken by sentence — more human than one wall
SOFT_SPLIT_THRESHOLD = 350


class Chunk(NamedTuple):
    """One message to send."""

    kind: str    # "text"
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


def _soft_split_long(line: str) -> List[str]:
    """A long line, still under the limit: split by sentence to look human."""
    if len(line) <= SOFT_SPLIT_THRESHOLD:
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
    ) -> None:
        self.cps = max(1.0, chars_per_second)
        self.max_delay = max_typing_delay
        self.min_delay = min_delay
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
            for soft in _soft_split_long(line):
                chunks.extend(Chunk("text", h) for h in _hard_split(soft))
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

        Returns what was *actually* sent. History must record what went out, not
        what was generated: a chunk that failed to send never happened, and
        writing it into the transcript teaches her she said something she didn't.
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
