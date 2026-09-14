"""Token budget for the one sliding context window.

Today the trim is by message count (30 live, 16 scoped) and no counter exists,
so a 150k ceiling is a slogan rather than something enforced. This module is
the counter: pure functions plus a small value object, no IO, no asyncio.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

# fallback when no tokenizer is available: ~4 chars per token for latin text
CHARS_PER_TOKEN = 4

# per-message framing overhead (role, boundaries, tool envelope)
MESSAGE_OVERHEAD_TOKENS = 8


def estimate_tokens(text: str) -> int:
    """Rough token count for budgeting, not billing.

    Tries tiktoken when installed, otherwise chars/4. Deterministic either
    way for a given input on a given machine.
    """
    if not text:
        return 0
    try:
        import importlib

        tiktoken = importlib.import_module("tiktoken")
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return max(1, len(text) // CHARS_PER_TOKEN)


def message_tokens(message: Dict[str, Any]) -> int:
    """Tokens carried by one context message, framing included."""
    total = MESSAGE_OVERHEAD_TOKENS
    total += estimate_tokens(str(message.get("content") or ""))
    tool_calls = message.get("tool_calls") or []
    for call in tool_calls:
        total += estimate_tokens(str(call))
    return total


def conversation_tokens(messages: List[Dict[str, Any]]) -> int:
    """Total tokens of a message list."""
    return sum(message_tokens(m) for m in messages)


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
        if self.trigger_tokens > self.max_tokens:
            self.trigger_tokens = self.max_tokens

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


def split_hot_cold(entries: List[BudgetEntry], *, hot_tokens: int = 30_000,
                   hot_seconds: float = 1800.0, now: float = 0.0) -> Tuple[List[BudgetEntry], List[BudgetEntry]]:
    """Splits old (compressible) from ongoing (kept verbatim).

    Walks from the newest entry back, keeping everything until both the token
    allowance and the time window are spent. What is happening right now is
    never compressed: cutting the last half hour to save tokens is how a
    persona loses consciousness of the moment.
    """
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
