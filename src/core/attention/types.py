"""What the attention gate decides. Pure data, no IO."""

from dataclasses import dataclass
from enum import Enum


class Reaction(str, Enum):
    """What to do with a perception."""

    REACT = "react"   # wake the mind now
    NOTE = "note"     # goes into the digest; zero llm calls
    DROP = "drop"     # noise, thrown away


@dataclass(frozen=True)
class Verdict:
    """The gate's decision on one perception."""

    reaction: Reaction
    score: float
    # readable so the thresholds can be tuned: "addressed:owner", "score:0.62", "cooldown"
    reason: str

    @property
    def reacts(self) -> bool:
        return self.reaction is Reaction.REACT
