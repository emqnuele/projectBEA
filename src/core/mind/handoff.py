"""Handoff: what scrolled cold, in her own words — plus the hot turns verbatim.

Two parts, different jobs. The cold past becomes a short prose recap ("you
talked about food for two hours, marco hates pineapple..."): what happened,
threads still open, nothing else. The hot ongoing is NOT rewritten at all —
it travels verbatim as speaker-labelled turns ("marco: ciao / you: ei"),
because rewriting the last half hour is how a persona loses the moment.

Who she is never belongs here: soul.md is in context on every turn already.
"""

import asyncio
from typing import Any

from src.utils.logger import get_logger

logger = get_logger("bea.mind.handoff")

# cap: a handoff is a bridge, not a second window (~5-8k tokens)
MAX_HANDOFF_CHARS = 24_000

HANDOFF_SYSTEM = (
    "You keep a running memory for someone who cannot see the earlier part of "
    "her own context any more. Given the older turns below, write a short "
    "prose recap, at most 150 words, in the second person ('you talked "
    "about...'), covering what happened and what is still open. Facts and "
    "threads only — no commentary, no preamble, no identity, no people list. "
    "The recent turns are preserved verbatim elsewhere: cover the older part "
    "only, do not repeat them."
)

HANDOFF_HEADER = "[EARLIER]"


def normalize_handoff(text: object) -> str:
    """A worker reply into clean prose. Empty when there is nothing to carry."""
    if not isinstance(text, str):
        return ""
    return text.strip()[:MAX_HANDOFF_CHARS]


def render_handoff(prose: str) -> str:
    """The handoff as the block opening the next window."""
    prose = normalize_handoff(prose)
    if not prose:
        return ""
    return f"{HANDOFF_HEADER}\n{prose}"


def build_handoff_payload(cold_text: str, previous_handoff: str = "") -> str:
    """User payload for the worker: previous recap plus what went cold."""
    if previous_handoff.strip():
        return f"PREVIOUS RECAP:\n{previous_handoff}\n\nOLDER TURNS:\n{cold_text}"
    return cold_text


class HandoffWorker:
    """Runs the handoff in the background when the window fills up.

    Trigger at 120k, rest near ~42k, loop never blocked: while the worker
    thinks, new turns keep appending, and whatever arrived mid-flight is
    carried into the next window verbatim. A failed worker call keeps the
    old window intact — losing a bridge must never lose the turns it was for.
    """

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm
        self.running = False
        self.last_prose = ""
        self.swaps = 0

    async def maybe_swap(self, ctx: Any) -> str:
        """One handoff if due and idle. Returns the prose, or nothing."""
        if self.running or self._llm is None:
            return ""
        if not ctx.status()["needs_handoff"]:
            return ""
        self.running = True
        try:
            seen = len(ctx.messages())
            cold, _ = ctx.snapshot_for_handoff()
            if not cold:
                return ""
            cold_text = format_turns([e.payload for e in cold])
            reply = await self._llm.complete([
                {"role": "system", "content": HANDOFF_SYSTEM},
                {"role": "user", "content": build_handoff_payload(cold_text, self.last_prose)},
            ], tools=None)
            prose = normalize_handoff(getattr(reply, "content", ""))
            if not prose:
                return ""
            ctx.swap(render_handoff(prose), incoming=ctx.messages()[seen:])
            self.last_prose = prose
            self.swaps += 1
            return prose
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Handoff failed, keeping the old window: {e}")
            return ""
        finally:
            self.running = False


def format_turns(messages: list) -> str:
    """Hot turns as speaker-labelled lines, verbatim, newest last.

    `messages` are plain {"role", "content"} dicts; user content already
    carries the speaker ("[marco] ciao"), bea lines are hers.
    """
    lines = []
    for m in messages:
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        if m.get("role") == "assistant":
            lines.append(f"you: {content}")
        else:
            lines.append(content)
    return "\n".join(lines)
