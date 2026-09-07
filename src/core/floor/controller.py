"""The reflex layer: it watches the call and opens the door. It never speaks.

Deliberately *not* a second consumer of the perception bus, and deliberately not
a change to `Perception`. It watches state it owns — when someone last spoke,
whether she is making sound, who is in the room — and when the moment is right
it puts one perception on the bus, exactly like every other sense in the
project. The mind then decides whether there is anything worth saying, and
`stay_silent` remains a perfectly good answer.

That is what keeps this from being a second mind: it has no memory, no persona
and nothing to say. Switch it off and Bea is the same person with worse timing.
"""

import random
import time
from typing import Callable, Optional

from src.core.events import EventCategory
from src.core.floor.rules import FloorDecision, FloorState, decide
from src.core.perception.types import Perception, PerceptionKind
from src.utils.logger import get_logger

logger = get_logger("bea.floor")

# how long a take counts against the rolling limit
WINDOW_SECONDS = 60.0


class FloorController:
    """Decides when the door opens, on a clock of seconds rather than of turns."""

    def __init__(self, *, config, bus, channel, expression, surface_name: str = "voice:discord",
                 events=None, clock: Callable[[], float] = time.monotonic,
                 rng: Optional[random.Random] = None):
        self.config = config
        self.bus = bus
        self.channel = channel
        self.expression = expression
        self.surface_name = surface_name
        self.events = events
        self.clock = clock
        self.rng = rng or random.Random()

        self._last_heard: Optional[float] = None
        self._takes: list = []
        # re-drawn after every take: a fixed threshold sounds like a timer,
        # because it is one
        self._threshold = self._draw_threshold()

    # --- config -------------------------------------------------------------

    @property
    def _cfg(self) -> dict:
        return self.config.skills.get("discord", {}) or {}

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.get("fill_silences", True))

    @property
    def silence_after(self) -> float:
        return float(self._cfg.get("silence_seconds", 6.0))

    @property
    def jitter(self) -> float:
        return float(self._cfg.get("silence_jitter_seconds", 2.0))

    @property
    def min_gap(self) -> float:
        return float(self._cfg.get("silence_min_gap_seconds", 25.0))

    @property
    def max_takes(self) -> int:
        """Unprompted openings per minute. The number that sets her character."""
        return int(self._cfg.get("unprompted_per_minute", 1))

    # --- what it watches ----------------------------------------------------

    def heard(self, now: Optional[float] = None) -> None:
        """Somebody said something: the room is not silent any more."""
        self._last_heard = self.clock() if now is None else now

    def state(self) -> FloorState:
        now = self.clock()
        # before the first word of a call there is no silence to measure yet:
        # walking in and immediately talking into the void is not presence
        silence = 0.0 if self._last_heard is None else now - self._last_heard
        return FloorState(
            in_call=bool(self.channel.live),
            listeners=int(self.channel.listeners),
            she_is_speaking=bool(getattr(self.expression, "is_speaking", False)),
            silence_seconds=silence,
            seconds_since_she_took=(now - self._takes[-1]) if self._takes else None,
            takes_in_window=self._recent_takes(now),
        )

    def _recent_takes(self, now: float) -> int:
        self._takes = [t for t in self._takes if now - t < WINDOW_SECONDS]
        return len(self._takes)

    def _draw_threshold(self) -> float:
        spread = max(0.0, self.jitter)
        return max(1.0, self.silence_after + self.rng.uniform(-spread, spread))

    # --- the tick -----------------------------------------------------------

    def tick(self) -> FloorDecision:
        """One pass. Returns the decision so a test can read it without a bus."""
        if not self.enabled:
            return FloorDecision.HOLD

        state = self.state()
        decision = decide(state, silence_after=self._threshold,
                          min_gap=self.min_gap, max_takes=self.max_takes)
        if decision is FloorDecision.TAKE_SILENCE:
            self._take(state)
        return decision

    def _take(self, state: FloorState) -> None:
        now = self.clock()
        self._takes.append(now)
        self._last_heard = now
        self._threshold = self._draw_threshold()

        seconds = int(state.silence_seconds)
        self.bus.put(Perception(
            kind=PerceptionKind.VOICE,
            surface=self.surface_name,
            content=(f"(nobody has said anything in the call for {seconds} seconds — "
                     "you can break the silence, or let it be)"),
            salience=0.6,
            # the same door minecraft nudges come through: an explicit reason
            # she is being addressed, which is what gets past the cooldown
            meta={"addressed": "silence", "silence_seconds": seconds,
                  "listeners": state.listeners},
        ))
        logger.info(f"floor: taking the silence after {seconds}s")
        self._publish(state, seconds)

    def _publish(self, state: FloorState, seconds: int) -> None:
        if self.events is None:
            return
        try:
            self.events.publish(
                EventCategory.SYSTEM, "floor", f"silence of {seconds}s: opening the door",
                metadata={"decision": FloorDecision.TAKE_SILENCE.value,
                          "silence_seconds": seconds, "listeners": state.listeners,
                          "takes_in_window": len(self._takes)},
            )
        except Exception as e:  # a metric must never break the reflex
            logger.debug(f"could not publish the floor decision: {e}")
