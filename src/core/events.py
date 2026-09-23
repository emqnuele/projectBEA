import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.core.fanout import Fanout, offer
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
        self.events: "deque[BrainEvent]" = deque(maxlen=max_history)
        self.max_history = max_history
        # bounded per subscriber: a browser tab that stopped reading must not grow without limit
        self._fanout = Fanout(QUEUE_LIMIT, "event")

    def publish(self, category: EventCategory, source: str, message: str,
                metadata: Optional[Dict[str, Any]] = None):
        event = BrainEvent(
            category=category,
            source=source,
            message=message,
            metadata=metadata or {},
        )
        self.events.append(event)
        self._fanout.publish(_render(event))
        logger.debug(f"[{category.upper()}] [{source}] {message}")

    def get_events(self, limit: int = 50) -> List[Dict]:
        """Returns recent events."""
        return [_render(e) for e in self._recent(limit)]

    def _recent(self, limit: int) -> List[BrainEvent]:
        return list(self.events)[-limit:] if limit > 0 else []

    # --- live subscription --------------------------------------------------

    def subscribe(self, backlog: int = 50) -> "asyncio.Queue[Dict[str, Any]]":
        """A queue of events, pre-filled with the recent ones.

        The backlog matters: a dashboard connecting mid-session should see what
        just happened rather than an empty screen until something else occurs.
        """
        return self._fanout.subscribe([_render(e) for e in self._recent(backlog)])

    def unsubscribe(self, queue) -> None:
        self._fanout.unsubscribe(queue)

    def close(self) -> None:
        """Ends every live stream: subscribers get one shutdown event, then nothing.

        Force-closing the connections from the server side used to cancel the
        streaming responses mid-sentence, which surfaced as a CancelledError
        traceback on every shutdown. A stream that returns on its own closes
        its connection cleanly instead.
        """
        for queue in self._fanout.queues():
            offer(queue, {"shutdown": True})
            self._fanout.unsubscribe(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._fanout)
