"""The body's own sliding window.

She has one and it is carefully managed; the body used to have a list that
only grew. That was survivable while a goal was twenty-four steps and then
over, and it stops being survivable the moment the body never stops.

What it keeps is deliberately dumb: the rules, the goal, and the last few
rounds of what it tried. Everything older lives in the notebook, which is the
one thing the body rewrites on purpose and which no trim can take away.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# how many think->act->observe rounds stay in the window
KEEP_ROUNDS = 12


@dataclass
class _Round:
    """One assistant turn and the observations it earned.

    A round, not a message, because the two cannot be separated: a `tool`
    message whose `tool_calls` got trimmed away is a malformed conversation and
    most providers reject the whole request over it. Dropping whole rounds is
    what makes the trim safe.
    """

    assistant: Dict[str, Any]
    results: List[Dict[str, Any]] = field(default_factory=list)

    def messages(self) -> List[Dict[str, Any]]:
        return [self.assistant, *self.results]


@dataclass
class _Note:
    """Something the world said to the body, outside any round."""

    message: Dict[str, Any]
    tag: str = ""

    def messages(self) -> List[Dict[str, Any]]:
        return [self.message]


class BodyContext:
    """The rolling window the body reasons over."""

    def __init__(self, keep_rounds: int = KEEP_ROUNDS) -> None:
        self.keep_rounds = max(1, int(keep_rounds))
        self.mission: str = ""
        self._entries: List[Any] = []

    def start(self, mission: str) -> None:
        """A new goal: the window is about that goal and nothing before it."""
        self.mission = mission
        self._entries = []

    def add_round(self, assistant: Dict[str, Any],
                  results: Optional[List[Dict[str, Any]]] = None) -> None:
        self._entries.append(_Round(assistant, list(results or [])))
        self._trim()

    def observe(self, text: str, tag: str = "") -> None:
        """A user-role line into the window: fresh game state, an interruption.

        A tagged note replaces the last one that carried the same tag. The
        state from nine steps ago is not history, it is a wrong answer to
        "where am I", and leaving it there is how a body walks back into the
        lava it already climbed out of.
        """
        if tag:
            self._entries = [e for e in self._entries
                             if not (isinstance(e, _Note) and e.tag == tag)]
        self._entries.append(_Note({"role": "user", "content": text}, tag))
        self._trim()

    def messages(self, system: str) -> List[Dict[str, Any]]:
        """The full request: stable prefix first, so the cache can hold it."""
        out: List[Dict[str, Any]] = [{"role": "system", "content": system}]
        if self.mission:
            out.append({"role": "user", "content": self.mission})
        for entry in self._entries:
            out.extend(entry.messages())
        return out

    @property
    def rounds(self) -> int:
        return sum(1 for e in self._entries if isinstance(e, _Round))

    def _trim(self) -> None:
        indexes = [i for i, e in enumerate(self._entries) if isinstance(e, _Round)]
        if len(indexes) <= self.keep_rounds:
            return
        self._entries = self._entries[indexes[len(indexes) - self.keep_rounds]:]
