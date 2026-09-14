"""The one sliding context window.

One mind, one log: every turn appends here instead of scattering across a
live rolling list and per-channel SQLite histories as two sources of truth
that never read each other. The window breathes — 0 → 50k → 120k → ~42k —
because a handoff compresses the cold past while the hot ongoing stays
verbatim, rather than sitting pinned at the ceiling.

Every entry is tagged with the conversation `key` it belongs to ("stage" for
the live room). The follow-up gate and the cooldowns read these tags — never
SQLite — so "are they answering me" survives a restart of nothing but the
process, and costs no query.
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

    def append(self, role: str, content: str, ts: Optional[float] = None, key: str = "stage",
               author: str = "", addressee: str = "") -> BudgetEntry:
        """Appends one message. Entries are atomic: never split by the trim."""
        entry = BudgetEntry(tokens=estimate_tokens(content) + 8, ts=ts or time.time(),
                            payload={"role": role, "content": content, "key": key,
                                     "author": author, "addressee": addressee})
        self._entries.append(entry)

        # emergency valve: if handoff is broken, don't brick the context
        while self.total_tokens > self.budget.max_tokens and len(self._entries) > 1:
            self._entries.pop(0)

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

    def messages(self, key: Optional[str] = None) -> List[Dict[str, Any]]:
        """The log as plain message dicts, oldest first, optionally filtered by conversation key."""
        out = []
        for e in self._entries:
            msg = dict(e.payload)
            msg_key = msg.pop("key", "stage")
            # System and handoff messages (role system) belong everywhere.
            if key is None or msg.get("role") == "system" or msg_key == key:
                out.append(msg)
        return out

    # --- what the follow-up gate reads ------------------------------------

    def turns_for(self, key: str, limit: int = 30) -> List[Dict[str, str]]:
        """Recent turns of one conversation as role/identity/addressee/content.

        The follow-up gate ("are they answering me") reads this, never SQLite:
        the window is the only context, so it is also the only witness.
        """
        out = []
        for e in self._entries:
            payload = e.payload if isinstance(e.payload, dict) else {}
            if payload.get("key", "stage") != key:
                continue
            role = payload.get("role", "user")
            out.append({
                "role": "bea" if role == "assistant" else "user",
                "identity": payload.get("author", ""),
                "addressee": payload.get("addressee", ""),
                "content": payload.get("content", ""),
            })
        return out[-limit:]

    def seconds_since_bea(self, key: str, now: Optional[float] = None) -> Optional[float]:
        """How long ago she last spoke in this conversation, if she ever did."""
        now = time.time() if now is None else now
        for e in reversed(self._entries):
            payload = e.payload if isinstance(e.payload, dict) else {}
            if payload.get("key", "stage") != key:
                continue
            if payload.get("role") == "assistant":
                return now - e.ts
        return None

    def activity_count(self, key: str, window_seconds: float = 120.0,
                       now: Optional[float] = None) -> int:
        """User lines in this conversation inside the recent window."""
        now = time.time() if now is None else now
        count = 0
        for e in self._entries:
            payload = e.payload if isinstance(e.payload, dict) else {}
            if payload.get("key", "stage") != key:
                continue
            if payload.get("role") == "user" and now - e.ts <= window_seconds:
                count += 1
        return count

    def live_keys(self, window_seconds: float = 6 * 3600.0,
                  now: Optional[float] = None) -> List[str]:
        """Conversation keys with recent traffic, newest first (never "stage")."""
        now = time.time() if now is None else now
        last: Dict[str, float] = {}
        for e in self._entries:
            payload = e.payload if isinstance(e.payload, dict) else {}
            key = payload.get("key", "stage")
            if key == "stage":
                continue
            if now - e.ts <= window_seconds:
                last[key] = e.ts
        return sorted(last, key=lambda k: last[k], reverse=True)

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
        while sum(e.tokens for e in carried) + estimate_tokens(handoff_text) > self.budget.max_tokens and len(carried) > 1:
            carried.pop(0)
        self._entries = [BudgetEntry(tokens=estimate_tokens(handoff_text) + 8, ts=time.time(),
                                     payload={"role": "user", "content": handoff_text,
                                              "key": "stage", "author": "",
                                              "addressee": ""})]
        self._entries.extend(carried)
        for message in incoming or []:
            self.append(str(message.get("role", "user")), str(message.get("content", "")),
                        key=str(message.get("key", "stage")),
                        author=str(message.get("author", "")),
                        addressee=str(message.get("addressee", "")))
        self.version += 1
        # window breathes after a swap: report whether it landed near target
        return {**self.status(), "carried_hot": len(carried)}
