"""Token budget for the one sliding context window.

The single source of truth for how much past fits in the live window: a
ceiling, a handoff trigger and a resting size, all in tokens. Pure functions
plus a small value object, no IO, no asyncio.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

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
    """Ceiling, trigger and resting size of the sliding window."""

    max_tokens: int = 150_000
    trigger_tokens: int = 120_000
    target_tokens: int = 50_000

    def __post_init__(self) -> None:
        self.max_tokens = max(1_000, int(self.max_tokens))
        self.trigger_tokens = max(1_000, int(self.trigger_tokens))
        self.target_tokens = max(1_000, int(self.target_tokens))
        # clamp, never crash: a bad config must degrade to a sane budget,
        # not take the whole startup down (and assert vanishes under -O)
        if self.trigger_tokens > self.max_tokens:
            self.trigger_tokens = self.max_tokens
        if self.target_tokens > self.trigger_tokens:
            self.target_tokens = self.trigger_tokens

    def needs_handoff(self, total: int) -> bool:
        """The window is full enough to start the background handoff."""
        return total >= self.trigger_tokens

    def over_max(self, total: int) -> bool:
        """Hard ceiling: trim cold at once, never block the loop on it."""
        return total > self.max_tokens


@dataclass
class BudgetEntry:
    """One atomic unit the splitter may keep or compress, never halve."""

    tokens: int = 0
    ts: float = 0.0
    payload: Any = field(default=None)
    seq: int = 0


def split_hot_cold(entries: List[BudgetEntry], *, hot_tokens: int = 30_000,
                    hot_seconds: float = 1800.0, now: Optional[float] = None) -> Tuple[List[BudgetEntry], List[BudgetEntry]]:
    """Splits old (compressible) from ongoing (kept verbatim).

    Walks from the newest entry back, keeping everything until both the token
    allowance and the time window are spent. What is happening right now is
    never compressed: cutting the last half hour to save tokens is how a
    persona loses consciousness of the moment.
    """
    import time as _time

    now = _time.time() if now is None else now
    hot: List[BudgetEntry] = []
    hot_total = 0
    for entry in reversed(entries):
        if hot and (hot_total + entry.tokens > hot_tokens or now - entry.ts > hot_seconds):
            break
        hot.append(entry)
        hot_total += entry.tokens
    hot.reverse()
    cold = entries[: len(entries) - len(hot)]
    return cold, hot
