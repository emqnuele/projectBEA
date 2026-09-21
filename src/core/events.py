import asyncio
import contextlib
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

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
    AGENT = "agent"       # autonomous agent actions
    DREAM = "dream"       # dream/consolidation events
    MEMORY = "memory"     # memory/recall events
    EMBODIMENT = "embodiment"  # avatar/presence events


class EventSeverity(str, Enum):
    """Severity level for events."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventVisibility(str, Enum):
    """Who can see an event."""
    SYSTEM = "system"      # internal only
    UI = "ui"              # visible in UI
    ALL = "all"            # everywhere


@dataclass
class BrainEvent:
    category: EventCategory
    source: str
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


def _render(event: BrainEvent) -> Dict[str, Any]:
    """Render an event as a flat dict, with metadata merged to top level."""
    result = {
        "id": event.id,
        "event_id": event.id,
        "timestamp": event.timestamp,
        "category": event.category.value,
        "source": event.source,
        "message": event.message,
    }
    # Merge metadata to top level so tests can access event_type, subsystem, payload directly
    result.update(event.metadata)
    return result


class EventManager:
    """The ring buffer the dashboard reads, plus live fan-out to subscribers."""

    def __init__(self, max_history: int = 200, journal_path: Optional[str] = None):
        self.events: List[BrainEvent] = []
        self.max_history = max_history
        self.journal_path = journal_path
        if journal_path:
            try:
                os.makedirs(os.path.dirname(journal_path), exist_ok=True)
            except Exception:
                pass
        # live subscribers (the dashboard's SSE stream). Bounded queues, because
        # a browser tab that stopped reading must not grow without limit.
        self._subscribers: List[Tuple[Any, Optional[str], Optional[str]]] = []

    def publish(self, category: EventCategory, source: str, message: str,
                metadata: Optional[Dict[str, Any]] = None,
                event_type=None, subsystem=None, severity=None,
                visibility=None, run_id=None, payload=None,
                parent_event_id=None):
        """Publish an event. Legacy kwargs (event_type, subsystem, etc.) are
        merged into metadata for backwards compatibility."""
        merged = dict(metadata or {})
        if event_type is not None:
            merged["event_type"] = event_type
        if subsystem is not None:
            merged["subsystem"] = subsystem
        if severity is not None:
            merged["severity"] = severity
        if visibility is not None:
            merged["visibility"] = visibility
        if run_id is not None:
            merged["run_id"] = run_id
        if payload is not None:
            merged["payload"] = payload
        if parent_event_id is not None:
            merged["parent_event_id"] = parent_event_id
        event = BrainEvent(
            category=category,
            source=source,
            message=message,
            metadata=merged,
        )

        self.events.append(event)

        # keep buffer size in check
        if len(self.events) > self.max_history:
            self.events.pop(0)

        self._fanout(_render(event))
        logger.debug(f"[{category.upper()}] {source}: {message}")
        return event

    def get_events(self, limit: int = 50) -> List[Dict]:
        """Returns recent events."""
        return [_render(e) for e in self.events[-limit:]]

    def filter_events(self, **kwargs) -> List[Dict]:
        """Returns events matching all kwargs as metadata fields."""
        results = []
        for event in self.events:
            match = True
            for key, value in kwargs.items():
                if key == "category":
                    if event.category != value:
                        match = False
                        break
                elif key == "source":
                    if event.source != value:
                        match = False
                        break
                else:
                    if event.metadata.get(key) != value:
                        match = False
                        break
            if match:
                results.append(_render(event))
        return results

    # --- live subscription --------------------------------------------------

    def subscribe(self, callback_or_backlog=None, event_type: Optional[str] = None, subsystem: Optional[str] = None):
        """Subscribe to events. Two call patterns:

        1. `subscribe(callback, event_type=, subsystem=)` - register a callback
           that is called only for matching events.
        2. `subscribe(backlog=50)` - return a queue of recent events, unfiltered.
        """
        # Pattern 1: first arg is a callback (callable but not a Queue, or is a function)
        if callback_or_backlog is not None and callable(callback_or_backlog):
            self._subscribers.append((callback_or_backlog, event_type, subsystem))
            return None
        
        # Pattern 2: return a queue
        backlog = callback_or_backlog if isinstance(callback_or_backlog, int) else 50
        queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=QUEUE_LIMIT)
        for event in self.events[-backlog:]:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(_render(event))
        self._subscribers.append((queue, event_type, subsystem))
        return queue

    def unsubscribe(self, queue) -> None:
        self._subscribers = [s for s in self._subscribers if s[0] is not queue]

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def _fanout(self, payload: Dict[str, Any]) -> None:
        for item in list(self._subscribers):
            subscriber, event_type, subsystem = item
            if event_type is not None and payload.get("event_type") != event_type:
                continue
            if subsystem is not None and payload.get("subsystem") != subsystem:
                continue
            if callable(subscriber):
                # Callback pattern
                try:
                    import inspect
                    sig = inspect.signature(subscriber)
                    if len(sig.parameters) >= 2:
                        subscriber(payload, payload)
                    else:
                        subscriber(payload)
                except Exception:
                    logger.debug("Event subscriber callback failed")
            elif subscriber is not None:
                # Queue pattern
                try:
                    subscriber.put_nowait(payload)
                except asyncio.QueueFull:
                    logger.debug("Dropping a stalled event subscriber.")
                    self.unsubscribe(subscriber)
