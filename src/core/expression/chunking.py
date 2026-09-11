"""Cutting a spoken turn into pieces that can be synthesised one at a time.

The cheapest latency win there is. Synthesising a whole turn means the room
hears nothing until the last word has been generated; synthesising the first
sentence and sending it means the time to first sound stops depending on how
much she had to say.

A boundary is a place a person would breathe, so it is also a place where a seam
between two synthesised pieces is inaudible. Cutting anywhere else is worse than
not cutting at all.

`SpeechChunker` does this while the line is still being written, so the first
piece can be on its way before the last one exists. `split_for_speech` is the
same rules applied to a line that is already finished, and is implemented on top
of the chunker so the two can never disagree about where a seam belongs.
"""

import re
from typing import List, Optional

from src.core.expression.tags import open_tag, strip, visible_len

# a sentence ends on . ! ? … — but only when what follows is a space or the end,
# so "3.14" and "gg.wp" stay one thought. Closing quotes and brackets belong to
# the sentence they close: cutting before them strands a lone `"` on the next
# piece, which is how a seam becomes audible.
_SENTENCE_END = re.compile(r"[.!?…][\"'”’)\]]*(?=\s|$)")

# a deliberate break in the line she wrote
_HARD_BREAK = re.compile(r"\n+")

# below this a piece is not worth its own synthesis round trip: "Ok." on its own
# costs a whole request and buys nothing
MIN_CHARS = 24

# the exception, and the reason any of this exists: the FIRST piece is what the
# room is waiting on, so it goes as soon as it is a whole thought rather than
# waiting to be a substantial one
FIRST_MIN_CHARS = 8

# above this we cut at the last comma rather than wait for a full stop that may
# never come — some models write one long breathless line
MAX_CHARS = 220

# where a forced cut stops being a pause and starts being a stumble: below a
# third of the budget, a comma is too far back to be worth landing on
_COMMA_FLOOR = 3


class SpeechChunker:
    """Cuts a line into synthesis-sized pieces while it is still arriving.

    `push` returns whatever is ready to be spoken now, which is usually nothing.
    `flush` returns the remainder once the line is known to be complete.
    """

    def __init__(self, min_chars: int = MIN_CHARS, first_min_chars: int = FIRST_MIN_CHARS,
                 max_chars: int = MAX_CHARS) -> None:
        self.min_chars = min_chars
        self.first_min_chars = first_min_chars
        self.max_chars = max_chars
        self._buffer = ""
        self._emitted = 0

    @property
    def pending(self) -> str:
        """What has arrived and has not been spoken yet."""
        return self._buffer

    def push(self, delta: str) -> List[str]:
        """Take more of the line; return the pieces that are ready to synthesise."""
        self._buffer += delta or ""
        ready: List[str] = []
        while True:
            piece = self._take()
            if piece is None:
                return ready
            ready.append(piece)

    def flush(self) -> List[str]:
        """The line is finished: return whatever is left, cut if it is over-long."""
        ready: List[str] = []
        while visible_len(self._buffer) > self.max_chars:
            piece = self._force()
            if piece is None:
                break
            ready.append(piece)
        rest = self._buffer.strip()
        self._buffer = ""
        if rest:
            self._emitted += 1
            ready.append(rest)
        return ready

    # --- internals ----------------------------------------------------------

    @property
    def _minimum(self) -> int:
        return self.first_min_chars if self._emitted == 0 else self.min_chars

    def _take(self) -> Optional[str]:
        """One piece, or None when the line has not reached a seam worth cutting."""
        cut = self._boundary()
        if cut is not None:
            head, self._buffer = self._buffer[:cut[0]], self._buffer[cut[1]:]
            self._emitted += 1
            return head.strip()

        if visible_len(self._buffer) >= self.max_chars:
            return self._force()
        return None

    def _boundary(self) -> Optional[tuple]:
        """The earliest seam with enough to say on its left, as (end, resume).

        Earliest rather than latest: a seam found now is a sentence that can be
        on its way now, and everything after it still has the whole rest of the
        line to catch up in.
        """
        minimum = self._minimum
        for match in self._seams():
            end, resume = match
            head = self._buffer[:end]
            if open_tag(head):
                continue
            if visible_len(head) >= minimum:
                return end, resume
        return None

    def _seams(self) -> List[tuple]:
        """Every confirmed place the line could be cut, in order, as (end, resume).

        A full stop sitting at the very end of what has arrived so far is not a
        seam: the stream may be halfway through "3.14". The whitespace that
        settles it comes with the next delta, and the end of the line itself is
        handled by `flush`.
        """
        seams = [(m.end(), m.end()) for m in _SENTENCE_END.finditer(self._buffer)
                 if m.end() < len(self._buffer)]
        seams += [(m.start(), m.end()) for m in _HARD_BREAK.finditer(self._buffer)]
        return sorted(seams)

    def _force(self) -> Optional[str]:
        """Cut an over-long stretch where a pause would sound deliberate."""
        window = self._buffer[:self._cut_ceiling()]
        cut = max(window.rfind(", "), window.rfind("; "))
        # how far back that comma is has to be measured in words, not in raw
        # characters: a window with three tags in it is not a longer window, and
        # counting them would accept a comma that is really much too early
        if cut > 0 and visible_len(window[:cut]) >= self.max_chars // _COMMA_FLOOR:
            cut += 1  # the comma belongs to the pause, not to what comes after
        else:
            cut = window.rfind(" ")
        if cut <= 0 or open_tag(self._buffer[:cut]):
            return None  # one very long word: leave it whole rather than cut inside it

        head, self._buffer = self._buffer[:cut], self._buffer[cut:].strip()
        self._emitted += 1
        return head.strip()

    def _cut_ceiling(self) -> int:
        """Where `max_chars` of speech falls in the raw text.

        Direction does not count against the budget — a line with three tags in
        it is not a longer line — so the ceiling has to be walked rather than
        assumed.
        """
        spoken = 0
        inside = False
        for index, char in enumerate(self._buffer):
            if char == "<":
                inside = True
            elif char == ">":
                inside = False
            elif not inside:
                spoken += 1
                if spoken >= self.max_chars:
                    return index + 1
        return len(self._buffer)


def split_for_speech(text: str, min_chars: int = MIN_CHARS,
                     max_chars: int = MAX_CHARS) -> List[str]:
    """Split a finished line into synthesis-sized pieces.

    The trailing scrap is glued to the piece before it, which a stream cannot do
    — by the time the line ends, the piece before it has already been spoken.
    """
    text = (text or "").strip()
    if not text:
        return []

    chunker = SpeechChunker(min_chars=min_chars, first_min_chars=min_chars,
                            max_chars=max_chars)
    pieces = chunker.push(text) + chunker.flush()

    if len(pieces) > 1 and visible_len(pieces[-1]) < min_chars:
        scrap = pieces.pop()
        pieces[-1] = f"{pieces[-1]} {scrap}"
    return pieces or [text]


def spoken_prefix(text: str, played_ms: int, total_ms: int) -> str:
    """The part of a line that actually reached the room before she was cut off.

    Proportional on characters and then rounded back to a word: speech is not
    uniform, so this is an approximation — but "roughly where she stopped" is
    the whole difference between her knowing she was interrupted and her
    carrying on as if the room had heard the end of the sentence.
    """
    text = strip(text or "")
    if not text or total_ms <= 0:
        return ""
    if played_ms >= total_ms:
        return text

    cut = max(0, min(len(text), round(len(text) * played_ms / total_ms)))
    window = text[:cut]
    space = window.rfind(" ")
    return (window[:space] if space > 0 else window).strip()
