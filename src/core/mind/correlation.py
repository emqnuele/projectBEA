"""The bridge between an HTTP caller and Bea's next reply.

Some entrypoints are synchronous — the dashboard's chat box, a Discord voice
turn that needs the WAV bytes back. They deposit a perception and then wait for
whatever she says in response.

Kept apart from the mind because it is not part of thinking: it is a request
lifecycle, with one rule that matters more than the rest — **a waiting caller is
always freed**. Silence is an answer; a hang is a bug.
"""

import asyncio
import uuid
from typing import Any, Callable, Dict, List

from src.utils.logger import get_logger

logger = get_logger("bea.mind.correlation")


class CorrelationRegistry:
    """Tracks the callers waiting on a reply, and makes sure none is forgotten."""

    def __init__(self) -> None:
        self._waiting: Dict[str, Dict[str, Any]] = {}
        self._batch: List[str] = []

    def register(self, route: str = "local") -> "tuple[str, asyncio.Future]":
        cid = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._waiting[cid] = {"future": future, "route": route}
        return cid, future

    @property
    def routes(self) -> set:
        """Which routes the current batch is expecting an answer on."""
        return {self._waiting[c]["route"] for c in self._batch if c in self._waiting}

    def start_batch(self, perceptions) -> List[str]:
        """Picks up the callers waiting on this batch. Replaces the previous one."""
        self._batch = self._ids_in(perceptions)
        return self._batch

    def extend_batch(self, perceptions) -> None:
        """Folds in callers whose input arrived mid-turn (steering)."""
        self._batch += self._ids_in(perceptions)

    def _ids_in(self, perceptions) -> List[str]:
        return [p.meta["correlation_id"] for p in perceptions
                if p.meta.get("correlation_id") in self._waiting]

    def resolve(self, route_matches: Callable[[str], bool], payload: Any) -> None:
        """Answers the waiting callers whose route matches."""
        for cid in list(self._batch):
            entry = self._waiting.get(cid)
            if not entry or entry["future"].done():
                continue
            if route_matches(entry["route"]):
                entry["future"].set_result(payload)
                self._waiting.pop(cid, None)
                self._batch.remove(cid)

    def release(self) -> None:
        """Frees everyone still waiting: she said nothing, which is an answer.

        Without this, a perception the attention gate filtered out would leave
        its caller hanging until the timeout.
        """
        for cid in list(self._batch):
            entry = self._waiting.pop(cid, None)
            if not entry or entry["future"].done():
                continue
            if entry["route"] == "discord":
                entry["future"].set_result({"status": "ignored", "text": "", "audio": b""})
            else:
                entry["future"].set_result({"mood": "normal", "message": ""})
        self._batch = []
