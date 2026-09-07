"""Cutting a spoken turn into pieces that can be synthesised one at a time.

The cheapest latency win there is. Synthesising a whole turn means the room
hears nothing until the last word has been generated; synthesising the first
sentence and sending it means the time to first sound stops depending on how
much she had to say.

A boundary is a place a person would breathe, so it is also a place where a seam
between two synthesised pieces is inaudible. Cutting anywhere else is worse than
not cutting at all.
"""

import re
from typing import List

# a sentence ends on . ! ? … or a newline, but only when what follows is a
# space or the end — "3.14" and "gg.wp" are one thought, not two
_BOUNDARY = re.compile(r"(?<=[.!?…])[\"'”’)\]]*(?=\s|$)|\n+")

# below this a piece is not worth its own synthesis round trip: "Ok." on its own
# costs a whole request and buys nothing
MIN_CHARS = 24
# above this we cut at the last comma rather than wait for a full stop that may
# never come — some models write one long breathless line
MAX_CHARS = 220


def split_for_speech(text: str, min_chars: int = MIN_CHARS,
                     max_chars: int = MAX_CHARS) -> List[str]:
    """Splits a line into synthesis-sized pieces at places a person would breathe."""
    text = (text or "").strip()
    if not text:
        return []

    pieces = [p.strip() for p in _BOUNDARY.split(text) if p and p.strip()]
    merged = _merge_short(pieces, min_chars)

    out: List[str] = []
    for piece in merged:
        out.extend(_break_long(piece, max_chars))
    return out or [text]


def _merge_short(pieces: List[str], min_chars: int) -> List[str]:
    """Glues a too-short piece onto the next one, or onto the previous if it is last."""
    out: List[str] = []
    pending = ""
    for piece in pieces:
        pending = f"{pending} {piece}".strip() if pending else piece
        if len(pending) >= min_chars:
            out.append(pending)
            pending = ""
    if pending:
        if out:
            out[-1] = f"{out[-1]} {pending}"
        else:
            out.append(pending)
    return out


def _break_long(piece: str, max_chars: int) -> List[str]:
    """Cuts an over-long piece at the last comma before the limit, else at a space."""
    out: List[str] = []
    while len(piece) > max_chars:
        window = piece[:max_chars]
        cut = max(window.rfind(", "), window.rfind("; "))
        if cut < max_chars // 3:
            cut = window.rfind(" ")
        if cut <= 0:
            break  # one very long word: leave it whole rather than cut inside it
        out.append(piece[:cut + 1].strip())
        piece = piece[cut + 1:].strip()
    if piece:
        out.append(piece)
    return out
