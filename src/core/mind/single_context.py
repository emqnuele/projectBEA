"""The one sliding context window.

One mind, one log: every turn appends here instead of scattering across a
live rolling list and per-channel SQLite histories as two sources of truth
that never read each other. The window breathes — 0 → 50k → 120k → ~42k —
because a handoff compresses the cold past while the hot ongoing stays
verbatim, rather than sitting pinned at the ceiling.
"""

import time
from typing import Any, Dict, List, Optional, Tuple

from src.core.mind.token_budget import BudgetEntry, TokenBudget, estimate_tokens, split_hot_cold

# verbatim overlap carried across a swap so a sentence or decision is never
# cut in half at the boundary
SWAP_OVERLAP_TOKENS = 5_000


class SingleContext:
    """Versioned, token-budgeted, append-only context log."""

    def __init__(self, budget: Optional[TokenBudget] = None, *, hot_tokens: int = 30_000,
                 hot_seconds: float = 1800.0):
        self.budget = budget or TokenBudget()
        self.hot_tokens = max(1_000, int(hot_tokens))
        self.hot_seconds = max(60.0, float(hot_seconds))
        self.version = 0
        self._entries: List[BudgetEntry] = []

    # --- writing ----------------------------------------------------------

    def append(self, role: str, content: str, ts: Optional[float] = None) -> BudgetEntry:
        """Appends one message. Entries are atomic: never split by the trim."""
        entry = BudgetEntry(tokens=estimate_tokens(content) + 8, ts=ts or time.time(),
                            payload={"role": role, "content": content})
        self._entries.append(entry)
        return entry

    # --- reading ----------------------------------------------------------

    @property
    def total_tokens(self) -> int:
        """Current window size in tokens."""
        return sum(e.tokens for e in self._entries)

    def status(self) -> Dict[str, Any]:
        """Budget state for the dashboard and the handoff trigger."""
        total = self.total_tokens
        return {
            "version": self.version,
            "total_tokens": total,
            "max_tokens": self.budget.max_tokens,
            "trigger_tokens": self.budget.trigger_tokens,
            "target_tokens": self.budget.target_tokens,
            "needs_handoff": self.budget.needs_handoff(total),
            "over_max": self.budget.over_max(total),
        }

    def messages(self) -> List[Dict[str, Any]]:
        """The log as plain message dicts, oldest first."""
        return [dict(e.payload) for e in self._entries]

    # --- handoff ----------------------------------------------------------

    def snapshot_for_handoff(self, now: Optional[float] = None) -> Tuple[List[BudgetEntry], List[BudgetEntry]]:
        """Splits compressible past (cold) from ongoing present (hot)."""
        return split_hot_cold(self._entries, hot_tokens=self.hot_tokens,
                              hot_seconds=self.hot_seconds, now=now if now is not None else time.time())

    def swap(self, handoff_text: str, incoming: Optional[List[Dict[str, str]]] = None,
             now: Optional[float] = None) -> Dict[str, Any]:
        """Starts the next window: handoff + hot + overlap + incoming buffer.

        The cold past is gone; its essence survives in `handoff_text`. The hot
        ongoing is carried verbatim.         Perceptions that arrived mid-handoff are
        prepended from `incoming` so nothing is lost in flight.
        """
        _, hot = self.snapshot_for_handoff(now=now)
        carried = list(hot)
        # emergency valve: hot alone past the ceiling trims its oldest turns
        while sum(e.tokens for e in carried) + len(handoff_text) // 4 > self.budget.max_tokens and len(carried) > 1:
            carried.pop(0)
        self._entries = [BudgetEntry(tokens=estimate_tokens(handoff_text) + 8, ts=time.time(),
                                     payload={"role": "system", "content": handoff_text})]
        self._entries.extend(carried)
        for message in incoming or []:
            self.append(str(message.get("role", "user")), str(message.get("content", "")))
        self.version += 1
        # window breathes after a swap: report whether it landed near target
        return {**self.status(), "carried_hot": len(carried)}
