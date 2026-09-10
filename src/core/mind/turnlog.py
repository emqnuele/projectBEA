"""One line per turn, on disk, for the questions you only think to ask later.

Something went wrong on stream twenty minutes ago and you have no idea what.
The dashboard shows the turn happening; it does not show the prompt that was in
force, what the retrieval put in front of her, which tools she reached for, or
what any of it cost. By the time you want that, the context has already rolled
over and the answer is gone.

So every turn writes itself down: what she was told, what she was shown, what
she did, and what it cost. Three things become possible that were not —
understanding a bad turn after it has happened, comparing two models on real
turns rather than on a benchmark, and having a dataset of how she actually
behaves without ever setting out to collect one.

One file a day, JSON Lines, appended and never rewritten. Nothing here may ever
cost a turn: a full disk, a read-only volume and an object that will not
serialise all end the same way — a line in the log about the log, and the turn
carries on.
"""

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger("bea.mind.turnlog")

# how much of any one string is worth keeping. The system prompt is thousands of
# characters and the whole point is to be able to read these back; a retrieval
# that ran long should not push the turn it belongs to off the screen.
MAX_FIELD_CHARS = 20000


class TurnLog:
    """Appends one JSON object per turn to today's file.

    `clock` is injected so a test can watch the day roll over without waiting
    for midnight, and `keep_days` is enforced on the first write of each new day
    rather than on a timer — a stream box that runs for a month should not be
    quietly filling its disk with January.
    """

    def __init__(self, directory: str = "data/turns", keep_days: int = 14, clock=None):
        self.directory = Path(directory)
        self.keep_days = max(0, int(keep_days))
        self._clock = clock or datetime.datetime.now
        self._day = ""
        self._broken = False

    @property
    def enabled(self) -> bool:
        return not self._broken

    def path_for(self, day: str) -> Path:
        return self.directory / f"{day}.jsonl"

    def write(self, record: Dict[str, Any]) -> None:
        """Take a turn down. Never raises."""
        if self._broken:
            return
        try:
            now = self._clock()
            day = now.strftime("%Y-%m-%d")
            if day != self._day:
                self.directory.mkdir(parents=True, exist_ok=True)
                self._sweep(now)
                self._day = day

            line = json.dumps({"at": now.isoformat(timespec="seconds"), **_trim(record)},
                              ensure_ascii=False, default=str)
            with self.path_for(day).open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception as e:
            # once, and then never again: a log that logs its own failure every
            # turn is worse than no log at all
            self._broken = True
            logger.warning(f"Turns are no longer being written down ({e}).")

    def _sweep(self, now: datetime.datetime) -> None:
        """Drops the days that have aged out. `keep_days` of 0 keeps everything."""
        if not self.keep_days:
            return
        cutoff = (now - datetime.timedelta(days=self.keep_days)).strftime("%Y-%m-%d")
        for path in self.directory.glob("*.jsonl"):
            if path.stem < cutoff:
                path.unlink(missing_ok=True)


def _trim(record: Dict[str, Any]) -> Dict[str, Any]:
    """Caps the long strings, so one runaway retrieval cannot bury a whole day."""
    out: Dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, str) and len(value) > MAX_FIELD_CHARS:
            out[key] = value[:MAX_FIELD_CHARS] + f"… (+{len(value) - MAX_FIELD_CHARS} chars)"
        else:
            out[key] = value
    return out


def turn_record(*, context: List[Dict[str, Any]], perceptions: List[str],
                calls: List[Dict[str, Any]], spoke: Optional[Dict[str, str]],
                usage, steps: int, ms: float, model: str = "") -> Dict[str, Any]:
    """One turn, as the object that gets written down.

    Kept apart from the writing so the shape can be tested without a disk, and
    so the loop hands over what it already has rather than reaching back into
    the context to reconstruct it.
    """
    system = [m.get("content", "") for m in context if m.get("role") == "system"]
    return {
        "model": model,
        "steps": steps,
        "ms": round(ms),
        # the two halves are kept apart the way the prompt keeps them: the first
        # is what a provider should be caching, the second is what changed
        "prompt": system[0] if system else "",
        "briefing": "\n\n".join(system[1:]),
        "perceptions": perceptions,
        "tools": calls,
        "spoke": spoke,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "cached_tokens": usage.cached_tokens,
    }
