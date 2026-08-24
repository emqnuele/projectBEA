import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger("bea.events")

# how many events a single stalled subscriber may buffer before it is dropped
QUEUE_LIMIT = 500


class EventCategory(str, Enum):
    SYSTEM = "system"
    INPUT = "input"       # user input
    OUTPUT = "output"     # ai response
    THOUGHT = "thought"   # internal reasoning
    SKILL = "skill"       # skill triggers
    TOOL = "tool"         # tool usage
    ERROR = "error"


@dataclass
class BrainEvent:
    category: EventCategory
    source: str
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


def _render(event: BrainEvent) -> Dict[str, Any]:
    return {
        "id": event.id,
        "timestamp": event.timestamp,
        "category": event.category.value,
        "source": event.source,
        "message": event.message,
        "metadata": event.metadata,
    }


class EventManager:
    """The ring buffer the dashboard reads, plus live fan-out to subscribers."""

    def __init__(self, max_history: int = 200):
        self.events: List[BrainEvent] = []
        self.max_history = max_history
        # live subscribers (the dashboard's SSE stream). Bounded queues, because
        # a browser tab that stopped reading must not grow without limit.
        self._subscribers: List["asyncio.Queue[Dict[str, Any]]"] = []

    def publish(self, category: EventCategory, source: str, message: str,
                metadata: Optional[Dict[str, Any]] = None):
        event = BrainEvent(
            category=category,
            source=source,
            message=message,
            metadata=metadata or {},
        )

        self.events.append(event)

        # keep buffer size in check
        if len(self.events) > self.max_history:
            self.events.pop(0)

        self._fanout(_render(event))
        logger.debug(f"[{category.upper()}] [{source}] {message}")

    def get_events(self, limit: int = 50) -> List[Dict]:
        """Returns recent events."""
        return [_render(e) for e in self.events[-limit:]]

    # --- live subscription --------------------------------------------------

    def subscribe(self, backlog: int = 50) -> "asyncio.Queue[Dict[str, Any]]":
        """A queue of events, pre-filled with the recent ones.

        The backlog matters: a dashboard connecting mid-session should see what
        just happened rather than an empty screen until something else occurs.
        """
        queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=QUEUE_LIMIT)
        for event in self.events[-backlog:]:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(_render(event))
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
                # a subscriber that stopped reading is dropped rather than
                # allowed to slow down the brain that is trying to publish
                logger.debug("Dropping a stalled event subscriber.")
                self.unsubscribe(queue)
