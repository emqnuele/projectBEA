"""Token budget for the one sliding context window.

The single source of truth for how much past fits in the live window: a
ceiling, a handoff trigger and the hot present kept verbatim, all in tokens.
Pure functions plus a small value object, no IO, no asyncio.

The owner sets one number — the ceiling — and the rest of the shape follows it
(`budget_for`). What actually decides how much she remembers is the *trigger*,
not the ceiling: raising the ceiling alone would move nothing, because the
handoff would still fire at the same place. The gap between the two is the
room she keeps talking in while a handoff is being written. Anyone who wants
the numbers apart can still pin them one by one; 0 means "follow the
ceiling".
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# what the owner may choose as a ceiling. The floor is not cosmetic: below it
# the handoff fires before the hot present is even full, and she lives in a
# permanent recap. The roof is where provider context windows run out.
WINDOW_MIN_TOKENS = 150_000
WINDOW_MAX_TOKENS = 500_000
WINDOW_STEP_TOKENS = 10_000

# the shape of the window as fractions of its ceiling, at the proportions the
# defaults were tuned to: 150k ceiling -> 120k trigger, 30k hot.
# handing the ceiling to the owner means handing them these too, or the knob
# is a placebo
TRIGGER_RATIO = 0.8
HOT_RATIO = 0.2

# fallback when no tokenizer is available: ~4 chars per token for latin text
CHARS_PER_TOKEN = 4

# per-message framing overhead (role, boundaries, tool envelope)
MESSAGE_OVERHEAD_TOKENS = 8

# cached encoding handle: resolved once so budgeting never pays import +
# encoding setup per message and never blocks the loop on repeated work
_ENCODING: Any = None
_ENCODING_RESOLVED = False


def _encoding() -> Optional[Any]:
    """the cl100k encoder, or none when tiktoken is missing. resolved once."""
    global _ENCODING, _ENCODING_RESOLVED
    if _ENCODING_RESOLVED:
        return _ENCODING
    _ENCODING_RESOLVED = True
    try:
        import importlib

        tiktoken = importlib.import_module("tiktoken")
        _ENCODING = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _ENCODING = None
    return _ENCODING


def estimate_tokens(text: str) -> int:
    """Rough token count for budgeting, not billing.

    Tries tiktoken when installed, otherwise chars/4. Deterministic either
    way for a given input on a given machine.
    """
    if not text:
        return 0
    enc = _encoding()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    return max(1, len(text) // CHARS_PER_TOKEN)


def truncate_to_budget(text: str, max_tokens: int) -> str:
    """shrinks one oversized message to the ceiling instead of pinning the window.

    entries are atomic, so without this a single paste larger than max_tokens
    bricks the budget forever: the valve needs len > 1 and the handoff finds
    no cold. callers keep the head, which is where the request usually lives.
    """
    if estimate_tokens(text) + MESSAGE_OVERHEAD_TOKENS <= max_tokens:
        return text

    # Fast path: cap by chars first to avoid O(N log N) encoding of multi-MB pastes
    max_chars = max_tokens * 4
    if len(text) > max_chars:
        text = text[:max_chars]
    marker = "[...truncated to the context ceiling]"
    marker_tokens = estimate_tokens(marker)
    # binary search on chars: estimate_tokens is monotonic, a handful of
    # iterations converges without blocking on huge inputs
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if estimate_tokens(text[:mid]) + MESSAGE_OVERHEAD_TOKENS + marker_tokens <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    # token boundaries can merge across the cut, so verify the joined string
    # and back off geometrically until it provably fits
    while lo > 0 and (estimate_tokens(text[:lo] + marker)
                      + MESSAGE_OVERHEAD_TOKENS > max_tokens):
        lo = (lo * 9) // 10
    return text[:lo] + marker


@dataclass
class TokenBudget:
    """Ceiling and handoff trigger of the sliding window."""

    max_tokens: int = 150_000
    trigger_tokens: int = 120_000

    def __post_init__(self) -> None:
        self.max_tokens = max(1_000, int(self.max_tokens))
        self.trigger_tokens = max(1_000, int(self.trigger_tokens))
        # clamp, never crash: a bad config must degrade to a sane budget,
        # not take the whole startup down (and assert vanishes under -O)
        if self.trigger_tokens > self.max_tokens:
            self.trigger_tokens = self.max_tokens

    def needs_handoff(self, total: int) -> bool:
        """The window is full enough to start the background handoff."""
        return total >= self.trigger_tokens

    def over_max(self, total: int) -> bool:
        """Hard ceiling: trim cold at once, never block the loop on it."""
        return total > self.max_tokens


def clamp_ceiling(ceiling: Any) -> int:
    """The ceiling the owner asked for, brought inside what is supported.

    Clamps rather than raises: a config written by an older build, or by hand,
    must degrade to a working window instead of taking the start-up down.
    """
    try:
        value = int(ceiling)
    except (TypeError, ValueError):
        return WINDOW_MIN_TOKENS
    return max(WINDOW_MIN_TOKENS, min(WINDOW_MAX_TOKENS, value))


def _derived(ceiling: int, ratio: float) -> int:
    """One share of the ceiling, rounded to a round number of tokens."""
    return max(1_000, int(round(ceiling * ratio / 1_000.0)) * 1_000)


def budget_for(ceiling: Any, *, trigger: Any = 0,
               hot: Any = 0) -> Tuple["TokenBudget", int]:
    """The whole shape of the window from one ceiling. Returns (budget, hot).

    `trigger` and `hot` are overrides for whoever wants them apart: 0 — the
    default — means "follow the ceiling", so moving the one slider moves the
    whole window and nothing silently stays behind. A pinned trigger is still
    clamped by `TokenBudget`, which never lets it pass the ceiling.
    """
    ceiling = clamp_ceiling(ceiling)

    def pinned_or(raw: Any, ratio: float) -> int:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 0
        return value if value > 0 else _derived(ceiling, ratio)

    budget = TokenBudget(
        max_tokens=ceiling,
        trigger_tokens=pinned_or(trigger, TRIGGER_RATIO),
    )
    return budget, pinned_or(hot, HOT_RATIO)


def budget_from_config(cc: Any) -> Tuple["TokenBudget", int]:
    """The window shape a `consciousness` config block asks for.

    One reader for the whole engine: the mind builds its window from this at
    start-up and re-reads it on every reload, so a value changed in the
    dashboard and a value typed into config.json can never mean two different
    windows.
    """
    get = cc.get if hasattr(cc, "get") else (lambda *_: 0)
    return budget_for(
        get("context_max_tokens", WINDOW_MIN_TOKENS),
        trigger=get("handoff_trigger_tokens", 0),
        hot=get("hot_tokens", 0),
    )


@dataclass
class BudgetEntry:
    """One atomic unit the splitter may keep or compress, never halve."""

    tokens: int = 0
    ts: float = 0.0
    payload: Any = field(default=None)
    seq: int = 0
    # the entry as the model reads it, rendered once: the window replays every turn
    wire: Optional[List[Dict[str, Any]]] = field(default=None, compare=False, repr=False)


def split_hot_cold(entries: List[BudgetEntry], *,
                   hot_tokens: int = 30_000) -> Tuple[List[BudgetEntry], List[BudgetEntry]]:
    """Splits old (compressible) from ongoing (kept verbatim).

    Walks from the newest entry back, keeping everything until the token
    allowance is spent — the newest entry always, however large. Age plays no
    part: a conversation that paused for an hour is still the conversation,
    and summarizing it because the clock moved is how a persona loses the
    thread she was in.
    """
    hot: List[BudgetEntry] = []
    hot_total = 0
    for entry in reversed(entries):
        if hot and hot_total + entry.tokens > hot_tokens:
            break
        hot.append(entry)
        hot_total += entry.tokens
    hot.reverse()
    cold = entries[: len(entries) - len(hot)]
    return cold, hot
