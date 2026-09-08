"""How a line is said, as opposed to what it says.

She already picks a mood for every line and until now it only reached a PNG.
Engines spell the same intent differently and most can only do part of it, so
the intent is written once here and each wrapper translates what it can — the
same shape as `llm/reasoning.py`. `Prosody()` is neutral and must stay
byte-identical to no prosody at all.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from src.core.affect.rules import Affect, clamp
from src.core.mind.moods import vector_for

# small on purpose: a line that sounds annoyed, not a cartoon
RATE_PER_AROUSAL = 0.15
PITCH_HZ_PER_AROUSAL = 12.0
PITCH_HZ_PER_VALENCE = 8.0
VOLUME_PER_AROUSAL = 0.10

# a standing mood makes a matching line land harder and a contradicting one softer
AGREEMENT_GAIN = 0.40

# something ordinary said while furious still comes out clipped
NEUTRAL_LEAK = 0.50

RATE_LIMITS = (0.80, 1.25)
PITCH_LIMITS = (-25.0, 25.0)
VOLUME_LIMITS = (0.85, 1.15)


@dataclass(frozen=True)
class Prosody:
    """A deviation from however the voice is configured, never an absolute.

    Multipliers for rate and volume, an offset in Hz for pitch: mixed units,
    because that is what the engines that can do anything actually accept.
    """

    rate: float = 1.0
    pitch_hz: float = 0.0
    volume: float = 1.0

    @property
    def neutral(self) -> bool:
        return self.rate == 1.0 and self.pitch_hz == 0.0 and self.volume == 1.0


NEUTRAL = Prosody()


def for_mood(mood: str, affect: Optional[Affect] = None) -> Prosody:
    """How this line should sound: its own mood, coloured by the standing one.

    The mood decides the direction — a single furious line must not come out
    flat while the slow state catches up. The state decides how far it goes.
    """
    valence, arousal = _coloured(vector_for(mood), affect)
    return Prosody(
        rate=clamp(1.0 + arousal * RATE_PER_AROUSAL, *RATE_LIMITS),
        pitch_hz=clamp(
            arousal * PITCH_HZ_PER_AROUSAL + valence * PITCH_HZ_PER_VALENCE, *PITCH_LIMITS
        ),
        volume=clamp(1.0 + arousal * VOLUME_PER_AROUSAL, *VOLUME_LIMITS),
    )


def _coloured(vector: Tuple[float, float], affect: Optional[Affect]) -> Tuple[float, float]:
    if affect is None or not affect.felt:
        return vector
    if vector == (0.0, 0.0):
        return affect.valence * NEUTRAL_LEAK, affect.arousal * NEUTRAL_LEAK
    gain = 1.0 + AGREEMENT_GAIN * clamp(
        vector[0] * affect.valence + vector[1] * affect.arousal
    )
    return clamp(vector[0] * gain), clamp(vector[1] * gain)


# --- translation for the SSML-shaped engines --------------------------------


def as_percent(multiplier: float) -> str:
    return f"{round((multiplier - 1.0) * 100):+d}%"


def as_hz(offset: float) -> str:
    return f"{round(offset):+d}Hz"


def combine_percent(base: str, multiplier: float) -> str:
    """The configured voice and the mood compose; neither replaces the other."""
    return as_percent((1.0 + _number(base, "%") / 100.0) * multiplier)


def combine_hz(base: str, offset: float) -> str:
    return as_hz(_number(base, "Hz") + offset)


def _number(raw: str, suffix: str) -> float:
    """The number out of `+10%`. A malformed value is simply no change."""
    text = str(raw or "").strip()
    if text.lower().endswith(suffix.lower()):
        text = text[: -len(suffix)]
    try:
        return float(text)
    except ValueError:
        return 0.0
