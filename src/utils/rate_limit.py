"""A sliding window over the last N seconds: "may I send one more?".

Twitch times an account out for thirty minutes when it goes over twenty
messages in thirty seconds, and the humanizer sends one message per line — so
a long answer in a busy moment can trip it. `clock` is injected so the window
is deterministic under test.
"""

import time
from collections import deque
from typing import Callable, Deque, Optional


class SlidingWindow:
    """Allows `limit` events per `per_seconds`, counted over a moving window."""

    def __init__(self, *, limit: int, per_seconds: float,
                 clock: Optional[Callable[[], float]] = None) -> None:
        self.limit = max(1, int(limit))
        self.per_seconds = float(per_seconds)
        self._clock = clock or time.monotonic
        self._stamps: Deque[float] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - self.per_seconds
        while self._stamps and self._stamps[0] <= cutoff:
            self._stamps.popleft()

    def allow(self) -> bool:
        """Records one event and says whether it was within the budget."""
        now = self._clock()
        self._prune(now)
        if len(self._stamps) >= self.limit:
            return False
        self._stamps.append(now)
        return True

    def retry_after(self) -> float:
        """Seconds until there is room again; 0.0 when there already is."""
        now = self._clock()
        self._prune(now)
        if len(self._stamps) < self.limit:
            return 0.0
        return max(0.0, self._stamps[0] + self.per_seconds - now)
