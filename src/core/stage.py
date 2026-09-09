"""What the browser source is told, and the last thing it was told.

Deliberately not `EventManager`. That one replays a backlog to every new
subscriber, which is right for a dashboard reading a log and wrong for a stage:
OBS reloads a browser source whenever you toggle it, and replaying fifty events
would make her act out the last minute of the stream again. Here a fresh
connection gets one snapshot of how she looks *now*, and patches after that.
"""

import asyncio
import contextlib
from typing import Any, Dict, List

from src.utils.logger import get_logger

logger = get_logger("bea.stage")

# how many patches a stalled page may buffer before it is dropped
QUEUE_LIMIT = 200

# things that describe a moment rather than a state. Storing the envelope would
# make a page that reconnects mouth a sentence nobody is saying any more.
TRANSIENT = frozenset({"envelope", "perform"})


class StageChannel:
    """One-way fan-out from the engine to however many browser sources exist."""

    def __init__(self) -> None:
        self._subscribers: List["asyncio.Queue[Dict[str, Any]]"] = []
        self._state: Dict[str, Any] = {"mood": "normal", "state": "idle", "caption": ""}

    # --- writing ------------------------------------------------------------

    def publish(self, patch: Dict[str, Any]) -> None:
        """Merges the durable keys into the state and fans the patch out."""
        for key, value in patch.items():
            if key not in TRANSIENT:
                self._state[key] = value
        self._fanout(patch)

    def snapshot(self) -> Dict[str, Any]:
        """Everything a page needs to draw her correctly the instant it loads."""
        return dict(self._state)

    # --- reading ------------------------------------------------------------

    def subscribe(self) -> "asyncio.Queue[Dict[str, Any]]":
        queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def _fanout(self, payload: Dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # a page that stopped reading must not slow down the engine
                logger.debug("Dropping a stalled stage subscriber.")
                self.unsubscribe(queue)

    def close(self) -> None:
        for queue in list(self._subscribers):
            self.unsubscribe(queue)
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait({"closed": True})
