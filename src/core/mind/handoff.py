"""Handoff: what scrolled cold, in her own words — plus the hot turns verbatim.

Two parts, different jobs. The cold past becomes a short prose recap ("you
talked about food for two hours, marco hates pineapple..."): what happened,
threads still open, nothing else. The hot ongoing is NOT rewritten at all —
it travels verbatim as speaker-labelled turns ("marco: ciao / you: ei"),
because rewriting the last half hour is how a persona loses the moment.

Who she is never belongs here: soul.md is in context on every turn already.
"""

import asyncio
import math
import time
from typing import Any, List

from src.core.language import write_in
from src.utils.logger import get_logger

logger = get_logger("bea.mind.handoff")

# cap: a handoff is a bridge, not a second window (~5-8k tokens)
MAX_HANDOFF_CHARS = 24_000

# the most older turns one worker call is handed. A 500k window leaves ~300k
# to summarize, which in one call outlives the request timeout (85k took up to
# 48s, measured) or outgrows a background model's context — and a handoff that
# fails every time never frees the window at all. Parts are chained through
# the recap, the same way one swap already hands its recap to the next.
HANDOFF_PART_TOKENS = 60_000

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

# frame scaffolding is orientation, not history: summarizing it bakes our own
# headers into her memory as if they were things that happened.
# matched strictly: a user line that merely starts like scaffolding ("you are
# on fire today") is history, not framing, and must survive into the recap.
_SKIPPED_PREFIXES = (
    "[PERCEPTIONS",
    "[NEW INPUT",
    "[WHERE YOU ARE]",
    "[YOU WERE CUT OFF]",
)


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


def split_parts(entries: List[Any], limit: int) -> List[List[Any]]:
    """Older turns cut into parts of about the same size, about `limit` at most.

    Even rather than greedy: filling each part to the brim leaves a sliver of
    a last part, a whole worker call for a handful of lines. Each entry goes
    to the part its midpoint falls in, so an entry is never halved and one
    larger than a part simply is a part of its own.
    """
    total = sum(e.tokens for e in entries)
    if not entries:
        return []
    count = max(1, math.ceil(total / max(1, limit)))
    share = total / count
    parts: List[List[Any]] = [[] for _ in range(count)]
    before = 0
    for entry in entries:
        index = min(count - 1, int((before + entry.tokens / 2) / share)) if share else 0
        parts[index].append(entry)
        before += entry.tokens
    return [part for part in parts if part]


class HandoffWorker:
    """Runs the handoff in the background when the window fills up.

    Trigger at 120k, loop never blocked: while the worker thinks, new turns
    keep appending into the room left under the ceiling, and all of them — with
    the hot present — open the next window verbatim. A failed worker call keeps
    the old window intact — losing a bridge must never lose the turns it was for.
    """

    def __init__(self, llm: Any = None, *, noop_retry_seconds: float = 300.0,
                 language: str = "") -> None:
        self._llm = llm
        # the recap is prose dropped straight into her context: written in the
        # wrong language it is the single loudest pull away from the one the
        # conversation is actually in
        self.language = language
        self.running = False
        self.last_prose = ""
        self.swaps = 0
        # nothing compressible right now (cold empty): don't re-snapshot every
        # turn until this deadline — the trigger stays true but there is no
        # work to do, and a snapshot per turn is pure overhead
        self._noop_until = 0.0
        self.noop_retry_seconds = max(30.0, float(noop_retry_seconds))

    def set_llm(self, llm: Any) -> None:
        """binds the background client without touching privates from outside."""
        self._llm = llm

    def _back_off(self) -> str:
        self._noop_until = time.time() + self.noop_retry_seconds
        return ""

    async def maybe_swap(self, ctx: Any) -> str:
        """One handoff if due and idle. Returns the prose, or nothing."""
        if self.running or self._llm is None:
            return ""
        if not ctx.status()["needs_handoff"]:
            return ""
        if time.time() < self._noop_until:
            return ""
        self.running = True
        try:
            version = ctx.version
            cold, cut = ctx.handoff_cut()
            parts = [[e.payload for e in part
                      if not (isinstance(e.payload, dict) and e.payload.get("role") == "system")]
                     for part in split_parts(cold, HANDOFF_PART_TOKENS)]
            texts = [t for t in (format_turns(p) for p in parts) if t.strip()]
            if not texts:
                return self._back_off()
            began = time.perf_counter()
            before = ctx.total_tokens
            logger.info(f"Handoff started: window at {before:,} tokens, summarizing "
                        f"{sum(e.tokens for e in cold):,} older tokens in {len(texts)} part(s).")
            prose = self.last_prose
            for text in texts:
                reply = await self._llm.complete([
                    {"role": "system", "content": f"{HANDOFF_SYSTEM} {write_in(self.language)}"},
                    {"role": "user", "content": build_handoff_payload(text, prose)},
                ], tools=None)
                prose = normalize_handoff(getattr(reply, "content", ""))
                if not prose:
                    logger.warning("Handoff got an empty recap, keeping the old window.")
                    return self._back_off()
            # the consolidation empties the window while she sleeps: a recap of
            # the evening landing on top of that would put the evening back
            if ctx.version != version:
                logger.info("The window changed under the handoff; dropping its recap.")
                return ""
            landed = ctx.slide(render_handoff(prose), cut)
            self.last_prose = prose
            self.swaps += 1
            self._noop_until = 0.0
            logger.info(f"Handoff done in {time.perf_counter() - began:.1f}s: window "
                        f"{before:,} -> {landed['total_tokens']:,} tokens, "
                        f"{landed['carried']} line(s) carried verbatim.")
            return prose
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Handoff failed, keeping the old window: {e}")
            return self._back_off()
        finally:
            self.running = False


def _is_scaffolding(line: str, role: object) -> bool:
    """True when a line is our own framing, not something that happened.

    Bracketed frame headers never occur in genuine speech. Orientation lines
    match the template (`you are on x in conversation y`), never a bare
    prefix — `you are on fire today` is history. The `[EARLIER]`
    header is scaffolding only on system bridge entries (or as the bare
    header line); a user line continuing after it is theirs.
    """
    if line.startswith(_SKIPPED_PREFIXES):
        return True
    lowered = line.lower()
    if lowered.startswith("you are on ") and "in conversation" in lowered:
        return True
    if role == "system" and line.startswith(HANDOFF_HEADER):
        return True
    return line == HANDOFF_HEADER


def format_turns(messages: list) -> str:
    """Hot turns as speaker-labelled lines, verbatim, newest last.

    `messages` are plain {"role", "content"} dicts; user content already
    carries the speaker ("[marco] ciao"), bea lines are hers. Frame
    scaffolding (perception headers, orientation) is skipped: it describes
    the turn, it is not the turn.
    """
    lines = []
    for m in messages:
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        role = m.get("role")
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or _is_scaffolding(stripped, role):
                continue
            if role == "assistant":
                lines.append(f"you: {stripped}")
            else:
                lines.append(stripped)
    return "\n".join(lines)
