"""What the attention gate decides, and why. Pure data — no IO, no imports."""

from dataclasses import dataclass
from enum import Enum


class Reaction(str, Enum):
    """What to do with a perception."""

    REACT = "react"   # wake the mind now
    NOTE = "note"     # goes into the digest; zero llm calls
    DROP = "drop"     # noise, thrown away


@dataclass(frozen=True)
class Verdict:
    """The gate's decision on one perception.

    `reason` is meant to be read by a human tuning the thresholds: without
    seeing *why* something was ignored, calibration is blind guessing.
    """

    reaction: Reaction
    score: float
    reason: str   # "addressed:mention" | "addressed:owner" | "score:0.62" | "cooldown"

    @property
    def reacts(self) -> bool:
        return self.reaction is Reaction.REACT
