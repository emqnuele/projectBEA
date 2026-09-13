"""Where the milliseconds of a voice turn go.

One number decides whether any of the voice work was worth doing: how long
between someone stopping talking and Bea's first sound. Everything else — a
streaming TTS, a push channel, a reflex — is a bet on moving that number, and a
bet nobody can read is a bet nobody can settle.

So the turn carries a stopwatch from the moment audio lands to the moment the
first byte leaves for the call, and the breakdown says which stage to blame.
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from src.core.events import EventCategory
from src.utils.logger import get_logger

logger = get_logger("bea.skills.voice.latency")

# the stages of one turn, in the order they happen
STT = "stt"
MIND = "mind"
TTS = "tts"
TRANSPORT = "transport"
STAGES = (STT, MIND, TTS, TRANSPORT)


@dataclass
class VoiceTurn:
    """One turn's stopwatch. Pure bookkeeping: it publishes nothing itself."""

    speaker: str
    started: float
    stages: Dict[str, float] = field(default_factory=dict)
    order: List[str] = field(default_factory=list)
    _last: float = 0.0

    def __post_init__(self) -> None:
        self._last = self.started

    def mark(self, stage: str, now: float) -> None:
        """Closes `stage` at `now`. A stage marked twice accumulates.

        Accumulating matters for `tts`: a turn that says two sentences pays the
        synthesis twice, and hiding the second one would flatter the number.
        """
        elapsed = max(0.0, (now - self._last) * 1000.0)
        if stage not in self.stages:
            self.order.append(stage)
        self.stages[stage] = self.stages.get(stage, 0.0) + elapsed
        self._last = now

    @property
    def ttft_ms(self) -> float:
        """Audio in, first byte out. The whole point."""
        return sum(self.stages.values())

    def breakdown(self) -> Dict[str, int]:
        return {stage: round(self.stages[stage]) for stage in self.order}

    def render(self) -> str:
        parts = ", ".join(f"{s} {ms}" for s, ms in self.breakdown().items())
        return f"ttft {round(self.ttft_ms)}ms ({parts})"


class VoiceLatency:
    """The stopwatch of the voice turn currently in flight.

    A single slot, on purpose: the mind is serial, so there is never more than
    one voice turn being reasoned about. A turn nobody closed is simply replaced
    by the next one — the metric is a diagnostic, and a diagnostic that leaks
    memory or throws is worse than no diagnostic.
    """

    def __init__(self, events=None, clock: Callable[[], float] = time.monotonic):
        self.events = events
        self.clock = clock
        self.turn: Optional[VoiceTurn] = None

    def open(self, speaker: str) -> VoiceTurn:
        """Audio from the call just landed: start counting."""
        self.turn = VoiceTurn(speaker=speaker, started=self.clock())
        return self.turn

    def mark(self, stage: str) -> None:
        """Closes a stage of the open turn; a no-op when none is open."""
        if self.turn is None:
            return
        self.turn.mark(stage, self.clock())

    def close(self) -> Optional[VoiceTurn]:
        """First byte is on its way out: publish the breakdown and clear."""
        turn = self.turn
        self.turn = None
        if turn is None or not turn.stages:
            return None
        logger.info(f"voice {turn.render()}")
        self._publish(turn)
        return turn

    def abandon(self) -> None:
        """She said nothing. There is no time-to-first-sound to report."""
        self.turn = None

    def _publish(self, turn: VoiceTurn) -> None:
        if self.events is None:
            return
        try:
            self.events.publish(
                EventCategory.SYSTEM, "voice.latency", turn.render(),
                metadata={"ttft_ms": round(turn.ttft_ms), "speaker": turn.speaker,
                          **turn.breakdown()},
            )
        except Exception as e:  # a metric must never break a turn
            logger.debug(f"could not publish the voice latency: {e}")
