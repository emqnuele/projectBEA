"""What her body is trying to do, as a thing with a life rather than a string.

The mind used to hand the body a sentence and get one back when it was over.
Nothing in between had a name: no way to ask what it was on, whether it had
stalled, or how long it had been at it — and an interruption threw the sentence
away, because there was nothing left holding it.
"""

import time
from dataclasses import dataclass, field
from typing import Dict

# a goal the body is working on right now
RUNNING = "running"
# put down mid-way so the mind could use the body for something else
SUSPENDED = "suspended"
# the body said it was finished
DONE = "done"
# out of steps, or failing the same way over and over
STUCK = "stuck"
# replaced by a newer goal, or called off
ABANDONED = "abandoned"

# statuses after which the body stops working on it
CLOSED = frozenset({DONE, STUCK, ABANDONED})


@dataclass
class Goal:
    """One intention of hers, and how far the body has got with it."""

    text: str
    status: str = RUNNING
    set_at: float = field(default_factory=time.time)
    steps: int = 0
    # how many observations in a row came back bad; a body failing the same way
    # forever is stuck long before it runs out of steps
    failures: int = 0
    # the one line the body closes with, which is what actually reaches her
    outcome: str = ""
    # what the world has to agree about before this may close as done. Empty
    # means the body's word is all there is, which is how it always was
    requires: Dict[str, int] = field(default_factory=dict)

    @property
    def open(self) -> bool:
        return self.status not in CLOSED

    @property
    def elapsed(self) -> float:
        return time.time() - self.set_at

    def describe(self, budget: int = 0) -> str:
        """One line for her context: what it is on, and how it is going."""
        spent = f"{self.steps}/{budget}" if budget else str(self.steps)
        line = f"{self.text} ({int(self.elapsed)}s, step {spent})"
        if self.status == SUSPENDED:
            return f"paused: {line}"
        if self.status == STUCK:
            return f"stuck on: {line}"
        return f"working on: {line}"


def unmet(requires: Dict[str, int], have: Dict[str, int]) -> str:
    """What is still missing, named with the numbers, or "" when nothing is.

    A request matches an item by its exact name or by its kind, so `log` is
    satisfied by oak_log and birch_log together. It matches on the whole last
    word only: `stone` must not be answered by a stone_pickaxe.
    """
    short = []
    for item, needed in (requires or {}).items():
        got = sum(count for name, count in (have or {}).items() if _is(name, item))
        if got < int(needed):
            short.append(f"{item} {got}/{int(needed)}")
    return ", ".join(short)


def _is(name: str, wanted: str) -> bool:
    return name == wanted or name.endswith("_" + wanted)
