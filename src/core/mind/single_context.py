"""The one sliding context window.

One mind, one log: every turn appends here instead of scattering across a
live rolling list and per-channel SQLite histories as two sources of truth
that never read each other. The window breathes — 0 → 50k → 120k → ~50k —
because a handoff compresses the cold past while the hot ongoing stays
verbatim, rather than sitting pinned at the ceiling.

Every entry is tagged with the conversation `key` it belongs to ("stage" for
the live room). The follow-up gate and the cooldowns read these tags — never
SQLite — so "are they answering me" survives a restart of nothing but the
process, and costs no query.
"""

import time
from typing import Any, Dict, List, Optional, Tuple

from src.core.mind.token_budget import (
    MESSAGE_OVERHEAD_TOKENS,
    BudgetEntry,
    TokenBudget,
    estimate_tokens,
    split_hot_cold,
    truncate_to_budget,
)

# verbatim overlap carried across a swap so a sentence or decision is never
# cut in half at the boundary
SWAP_OVERLAP_TOKENS = 5_000


class SingleContext:
    """Versioned, token-budgeted, append-only context log.

    Single-threaded by contract: every `append` and every swap runs on the
    event loop thread, so the synchronous swap is atomic and no lock is
    needed. Never append from a surface callback or worker thread — a
    threaded write racing a swap would be silently lost.
    """

    def __init__(self, budget: Optional[TokenBudget] = None, *, hot_tokens: int = 30_000,
                 hot_seconds: float = 1800.0):
        self.budget = budget or TokenBudget()
        # the hot present can never exceed the ceiling: promising more verbatim
        # than fits forces the swap to silently drop the present it just kept
        self.hot_tokens = min(max(1_000, int(hot_tokens)), max(1_000, self.budget.max_tokens))
        self.hot_seconds = max(60.0, float(hot_seconds))
        self.version = 0
        self._entries: List[BudgetEntry] = []
        # running total: total_tokens is o(1), never a scan per append
        self._total = 0
        self._next_seq = 1
        # tokens dropped by the emergency valve without ever being summarized:
        # cumulative, so unsummarized amnesia stays auditable from status()
        self.evicted_tokens = 0

    def __len__(self) -> int:
        return len(self._entries)

    def entry_count(self) -> int:
        """number of entries without building the message list."""
        return len(self._entries)

    def last_seq(self) -> int:
        """The sequence number of the most recent entry."""
        return self._next_seq - 1

    def entries_after(self, seq: int) -> List[BudgetEntry]:
        """entry objects appended after `seq`, keys intact.

        the handoff buffer round-trips through this, never through
        `messages()` — which strips keys — so mid-flight perceptions keep
        their conversation attribution across a swap.
        """
        return [e for e in self._entries if e.seq > seq]

    # --- writing ----------------------------------------------------------

    def append(self, role: str, content: str, ts: Optional[float] = None, key: str = "stage",
               author: str = "", addressee: str = "") -> BudgetEntry:
        """Appends one message. Entries are atomic: never split by the trim."""
        content = truncate_to_budget(content, self.budget.max_tokens)
        entry = BudgetEntry(tokens=estimate_tokens(content) + MESSAGE_OVERHEAD_TOKENS,
                            ts=ts or time.time(),
                            payload={"role": role, "content": content, "key": key,
                                     "author": author, "addressee": addressee},
                            seq=self._next_seq)
        self._next_seq += 1
        self._entries.append(entry)
        self._total += entry.tokens

        # emergency valve: if handoff is broken, don't brick the context.
        # system entries (the [earlier] bridge) are pinned: trimming the one
        # thing that reconstructs the past first defeats the handoff.
        while self._total > self.budget.max_tokens and len(self._entries) > 1:
            self._evict_oldest()
        # pathological single entry still over the ceiling (prose reserve,
        # estimator skew): shrink it in place rather than pinning the window
        if self._total > self.budget.max_tokens and len(self._entries) == 1:
            only = self._entries[0]
            payload = only.payload if isinstance(only.payload, dict) else {}
            shrunk = truncate_to_budget(str(payload.get("content", "")),
                                        self.budget.max_tokens)
            self._total -= only.tokens
            only.tokens = estimate_tokens(shrunk) + MESSAGE_OVERHEAD_TOKENS
            if isinstance(only.payload, dict):
                only.payload["content"] = shrunk
            self._total += only.tokens

        return entry

    def _evict_oldest(self) -> None:
        """drops the oldest evictable entry, sparing the continuity bridge."""
        for i, e in enumerate(self._entries):
            payload = e.payload if isinstance(e.payload, dict) else {}
            if payload.get("role") != "system":
                self._total -= e.tokens
                self.evicted_tokens += e.tokens
                del self._entries[i]
                return
        oldest = self._entries.pop(0)
        self._total -= oldest.tokens
        self.evicted_tokens += oldest.tokens

    # --- reading ----------------------------------------------------------

    @property
    def total_tokens(self) -> int:
        """Current window size in tokens."""
        return self._total

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
            "valve_evicted_tokens": self.evicted_tokens,
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
                              hot_seconds=self.hot_seconds, now=now)

    @staticmethod
    def apply_overlap(cold: List[BudgetEntry], hot: List[BudgetEntry],
                      overlap_tokens: int = SWAP_OVERLAP_TOKENS) -> Tuple[List[BudgetEntry], List[BudgetEntry]]:
        """Moves the cold tail into the carried set verbatim.

        Returns (cold_to_summarize, carried): the newest cold entries worth up
        to `overlap_tokens` travel verbatim so a sentence or decision is never
        cut in half at the boundary, and are excluded from the prose summary
        so they are not stored twice.
        """
        overlap: List[BudgetEntry] = []
        total = 0
        while cold and total + cold[-1].tokens <= overlap_tokens:
            entry = cold.pop()
            overlap.append(entry)
            total += entry.tokens
        overlap.reverse()
        return cold, overlap + list(hot)

    def swap_with_snapshot(self, handoff_text: str, hot: List[BudgetEntry],
                           incoming: Optional[List[BudgetEntry]] = None,
                           now: Optional[float] = None) -> Dict[str, Any]:
        """Starts the next window from one pre-handoff snapshot.

        Single-snapshot rule: `hot` and `incoming` must come from the same
        snapshot (entries at/after the snapshot point). Entries arriving
        mid-handoff are in `incoming` only — never re-snapshotted — so they
        cannot be duplicated into `hot` and back. Everything here is
        synchronous: no await, no thread handoff, the loop never yields
        mid-swap and no lock can block it.
        """
        _ = now
        # old continuity bridges never travel verbatim: the past they carry is
        # already chained through the worker's prose, so keeping them would
        # stack a bridge per swap and burn budget on stale recap
        carried = [e for e in hot
                   if not (isinstance(e.payload, dict) and e.payload.get("role") == "system")]
        seen_seqs = {e.seq for e in carried}
        fresh: List[BudgetEntry] = []
        for e in incoming or []:
            if e.seq not in seen_seqs:
                seen_seqs.add(e.seq)
                fresh.append(e)
        prose_tokens = estimate_tokens(handoff_text) + MESSAGE_OVERHEAD_TOKENS if handoff_text else 0
        combined = carried + fresh
        total_combined = sum(e.tokens for e in combined)
        # hard ceiling first: the window must fit max_tokens even when the
        # hot floor is large; the bridge is pinned, hot yields
        while (total_combined + prose_tokens > self.budget.max_tokens
               and combined):
            total_combined -= combined.pop(0).tokens
        # resting size: settle near target_tokens instead of pinning at the
        # trigger, keeping at least the newest hot entry
        while (total_combined + prose_tokens > self.budget.target_tokens
               and len(combined) > 1):
            total_combined -= combined.pop(0).tokens
        # how many hot entries survived the trim (combined pops from the front,
        # so hot goes first and fresh survives longest)
        kept_seqs = {e.seq for e in combined}
        kept_hot = sum(1 for e in carried if e.seq in kept_seqs)
        new_entries: List[BudgetEntry] = []
        if handoff_text:
            new_entries.append(BudgetEntry(
                tokens=prose_tokens, ts=time.time(),
                payload={"role": "system", "content": handoff_text,
                         "key": "stage", "author": "", "addressee": ""},
                seq=0))
        new_entries.extend(combined)
        self._entries = new_entries
        self._total = sum(e.tokens for e in new_entries)
        self.version += 1
        # window breathes after a swap: report whether it landed near target
        return {**self.status(), "carried_hot": kept_hot}

    def swap(self, handoff_text: str, incoming: Optional[List[Dict[str, str]]] = None,
             now: Optional[float] = None) -> Dict[str, Any]:
        """Starts the next window: handoff + hot + overlap + incoming buffer.

        Deprecated: kept for backwards compatibility (tests, external callers).
        The live loop path uses `swap_with_snapshot` with entry objects so keys
        survive — dict-style `incoming` cannot carry them through `messages()`.
        Snapshots once and treats dict-style `incoming` as brand-new entries.
        """
        _, hot = self.snapshot_for_handoff(now=now)
        entries: List[BudgetEntry] = []
        for message in incoming or []:
            if isinstance(message, BudgetEntry):
                entries.append(message)
                continue
            content = truncate_to_budget(str(message.get("content", "")),
                                         self.budget.max_tokens)
            entries.append(BudgetEntry(
                tokens=estimate_tokens(content) + MESSAGE_OVERHEAD_TOKENS,
                ts=time.time(),
                payload={"role": str(message.get("role", "user")),
                         "content": content,
                         "key": str(message.get("key", "stage")),
                         "author": str(message.get("author", "")),
                         "addressee": str(message.get("addressee", ""))},
                seq=self._next_seq))
            self._next_seq += 1
        return self.swap_with_snapshot(handoff_text, hot, entries, now=now)
