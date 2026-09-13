"""When her mouth opens. Never what comes out of it.

The floor is the right to speak: who has it, who is taking it, who is giving it
up. People negotiate it continuously and mostly without words, on a scale of
milliseconds — which is exactly why it cannot live in a prompt. A model cannot
honour a constraint measured in milliseconds, and every line of prompt spent
trying costs latency on every single turn.

So it lives here instead, as a pure function returning an enum. The rule that
keeps this from quietly becoming a second consciousness is the return type: if
anyone ever wants to add a `text` field to a decision, the design has slipped.
The mind is still the only thing in this codebase that can invent something to
say.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FloorDecision(str, Enum):
    HOLD = "hold"                 # say nothing; this is the answer most of the time
    TAKE_SILENCE = "take:silence"  # the room has gone quiet: open the door for her


@dataclass(frozen=True)
class FloorState:
    """Everything the decision is allowed to look at. No text, on purpose."""

    in_call: bool
    listeners: int
    she_is_speaking: bool
    silence_seconds: float
    seconds_since_she_took: Optional[float] = None
    takes_in_window: int = 0


def decide(state: FloorState, *, silence_after: float, min_gap: float,
           max_takes: int) -> FloorDecision:
    """Whether this is a moment to open her mouth in.

    Every gate here is a reason *not* to speak, and that ordering is deliberate:
    the failure people actually notice is the bot that talks too much, not the
    one that waits a beat too long.
    """
    if not state.in_call or state.listeners <= 0:
        return FloorDecision.HOLD
    # talking over her own voice is the one unambiguous mistake
    if state.she_is_speaking:
        return FloorDecision.HOLD
    if state.silence_seconds < silence_after:
        return FloorDecision.HOLD
    # she just filled a silence; filling the next one straight away is a tic
    if state.seconds_since_she_took is not None and state.seconds_since_she_took < min_gap:
        return FloorDecision.HOLD
    # the hard limit, and the reason she cannot become the one who never shuts up
    if max_takes > 0 and state.takes_in_window >= max_takes:
        return FloorDecision.HOLD
    return FloorDecision.TAKE_SILENCE
