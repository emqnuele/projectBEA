"""How she feels, as pure functions over two numbers and a timestamp.

It decays on read, not on a tick: the value carries when it was written, so a
restart comes back correctly aged and a test can stand at a fixed instant.
`render` describes a state and never prescribes behaviour — how she acts on it
is the soul's job, and the soul is a file the owner writes.
"""

import math
from dataclasses import dataclass
from typing import Tuple

# long enough to survive a few exchanges, short enough not to own the stream
HALF_LIFE_SECONDS = 25 * 60.0

# a rancour outlives a mood: days, not minutes
PERSON_HALF_LIFE_SECONDS = 60 * 3600.0

# one sharp line is a blip, two in a row are a mood
WEIGHT = 0.35

# under this, saying how she feels would be noise on every turn
FELT = 0.30

# where a mood stops being weather and starts being somebody's doing
STRONG_VALENCE = 0.60

WARMTH_SHOWN = 0.25


@dataclass(frozen=True)
class Affect:
    """Where she is on the two axes, and when that was last true."""

    valence: float = 0.0
    arousal: float = 0.0
    updated_at: float = 0.0

    @property
    def strength(self) -> float:
        return max(abs(self.valence), abs(self.arousal))

    @property
    def felt(self) -> bool:
        return self.strength >= FELT


def clamp(x: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, float(x)))


def faded(value: float, elapsed: float, half_life: float) -> float:
    """`value` after `elapsed` seconds. Toward zero, never past it."""
    if half_life <= 0 or elapsed <= 0 or value == 0.0:
        return value if elapsed <= 0 else 0.0
    return value * math.pow(0.5, elapsed / half_life)


def decay(affect: Affect, now: float, half_life: float = HALF_LIFE_SECONDS) -> Affect:
    """Her state as it stands `now`."""
    elapsed = now - affect.updated_at
    if elapsed <= 0:
        return affect
    return Affect(
        valence=faded(affect.valence, elapsed, half_life),
        arousal=faded(affect.arousal, elapsed, half_life),
        updated_at=now,
    )


def stir(affect: Affect, vector: Tuple[float, float], *, now: float,
         half_life: float = HALF_LIFE_SECONDS, weight: float = WEIGHT) -> Affect:
    """What she feels after expressing `vector`, on top of what she already felt.

    Additive rather than a slide toward the new mood: a neutral line has a zero
    vector, and under a slide every ordinary sentence would scrub the mood away.
    Time is what clears a mood, not talking.
    """
    base = decay(affect, now, half_life)
    return Affect(
        valence=clamp(base.valence + vector[0] * weight),
        arousal=clamp(base.arousal + vector[1] * weight),
        updated_at=now,
    )


def is_strong(vector: Tuple[float, float]) -> bool:
    """Did that land hard enough to be somebody's doing?

    Valence alone decides: a loud surprise has plenty of arousal without anyone
    having done anything to her.
    """
    return abs(vector[0]) >= STRONG_VALENCE


def render(affect: Affect) -> str:
    """`[HOW YOU FEEL]`, or nothing at all — which is most of the time.

    Every line is a state, never an instruction.
    """
    if not affect.felt:
        return ""

    valence, arousal = affect.valence, affect.arousal
    if valence <= -FELT:
        if arousal >= FELT:
            line = "Something got under your skin earlier and it hasn't worn off."
        elif arousal <= -FELT:
            line = "You feel flat. Nothing has gone your way for a while."
        else:
            line = "You're in a bad mood, and it has been going on a while."
    elif valence >= FELT:
        if arousal >= FELT:
            line = "You're still riding something that went well."
        else:
            line = "You're in a good mood, and have been for a while."
    elif arousal >= FELT:
        line = "You're wound up, without anything in particular behind it."
    else:
        line = "You're running out of steam."

    return f"[HOW YOU FEEL]\n{line}"


def warmth_phrase(warmth: float) -> str:
    """How she stands with one person, as words. A number would get recited."""
    if warmth >= 0.6:
        return "you're fond of them right now"
    if warmth >= WARMTH_SHOWN:
        return "they're in your good books lately"
    if warmth <= -0.6:
        return "you're still annoyed with them"
    if warmth <= -WARMTH_SHOWN:
        return "they've rubbed you the wrong way lately"
    return ""
