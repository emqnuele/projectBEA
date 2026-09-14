"""Starting a conversation, instead of only ever answering one.

Not "post every N minutes": a periodic check looks at the conversations that
are alive, skips the ones she just spoke in, stays out of quiet hours, and then
only sometimes goes ahead. `rng` and `clock` are injected for the tests.
"""

import random
import time
from datetime import datetime
from typing import Callable, List, Optional

from src.core.attention.rules import in_quiet_hours
from src.utils.logger import get_logger

logger = get_logger("bea.mind.spontaneous")

# how far back "this conversation is alive" looks
ACTIVITY_WINDOW = 1800.0

# older than this and writing there is a bot with a timer, not spontaneity
STALE_AFTER = 6 * 3600.0


class SpontaneousPresence:
    """Occasionally opens a conversation that is alive but has gone quiet."""

    def __init__(self, *, config, memory, bus, window=None,
                 rng: Optional[random.Random] = None,
                 clock: Optional[Callable[[], float]] = None):
        self.config = config
        self.memory = memory
        self.bus = bus
        # the one sliding window: liveness comes from here, never sqlite —
        # the durable log is append-only and must not drive live decisions
        self.window = window
        self._rng = rng or random.Random()
        self._clock = clock or time.time

    @property
    def _cfg(self) -> dict:
        return getattr(self.config, "rhythm", {}) or {}

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.get("spontaneous_enabled", True))

    @property
    def probability(self) -> float:
        return float(self._cfg.get("spontaneous_probability", 0.15))

    @property
    def min_silence(self) -> float:
        return float(self._cfg.get("spontaneous_min_silence", 3600.0))

    @property
    def min_activity(self) -> int:
        return int(self._cfg.get("spontaneous_min_activity", 3))

    @property
    def quiet_hours(self) -> tuple:
        q = getattr(self.config, "attention", {}).get("quiet_hours", [3, 9])
        return int(q[0]), int(q[1])

    # --- the decision (pure given its inputs) -------------------------------

    def is_eligible(self, *, hour: int, seconds_since_bea: Optional[float],
                    activity: int) -> bool:
        if in_quiet_hours(hour, *self.quiet_hours):
            return False
        if activity < self.min_activity:
            return False  # a dead room: she would be talking to nobody
        if seconds_since_bea is not None and seconds_since_bea < self.min_silence:
            return False  # she spoke recently; saying more is not presence, it is noise
        return True

    # --- the pass -----------------------------------------------------------

    def candidates(self) -> List[str]:
        """Conversations recent enough to be worth considering at all."""
        if self.window is None:
            return []
        return self.window.live_keys(window_seconds=STALE_AFTER, now=self._clock())

    async def run_once(self) -> int:
        """Checks every live conversation; returns how many she opened."""
        from src.core.perception.types import Perception, PerceptionKind

        if not self.enabled:
            return 0
        window = self.window
        if window is None:
            return 0
        hour = datetime.fromtimestamp(self._clock()).hour
        started = 0

        # window reads are cheap and synchronous: no thread hop, the loop
        # never waits on its own memory
        for key in self.candidates():
            try:
                now = self._clock()
                since = window.seconds_since_bea(key, now=now)
                activity = window.activity_count(key, ACTIVITY_WINDOW, now=now)
            except Exception as e:
                logger.warning(f"Spontaneous: could not read '{key}': {e}")
                continue

            if not self.is_eligible(hour=hour, seconds_since_bea=since, activity=activity):
                continue
            if self._rng.random() >= self.probability:
                continue

            logger.info(f"Spontaneous: opening '{key}' on her own.")
            self.bus.put(Perception(
                kind=PerceptionKind.SYSTEM,
                surface="spontaneous",
                content="[NOBODY IS TALKING TO YOU] Nothing new here — this one has just gone quiet, and you thought of it. If there is something you actually want to say, say it: pick up something from earlier, ask about a thing someone left hanging, complain about your day. If nothing genuinely comes to mind, say_nothing.",
                meta={"conversation_key": key}
            ))
            started += 1

        return started
