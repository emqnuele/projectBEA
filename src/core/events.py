from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional
import time
import uuid
from src.utils.logger import get_logger

logger = get_logger("bea.events")

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

class EventManager:
    def __init__(self, max_history: int = 200):
        self.events: List[BrainEvent] = []
        self.max_history = max_history

    def publish(self, category: EventCategory, source: str, message: str, metadata: Dict[str, Any] = None):
        if metadata is None:
            metadata = {}
            
        event = BrainEvent(
            category=category,
            source=source,
            message=message,
            metadata=metadata
        )
        
        self.events.append(event)
        
        # keep buffer size in check
        if len(self.events) > self.max_history:
            self.events.pop(0)
            
        logger.debug(f"[{category.upper()}] [{source}] {message}")

    def get_events(self, limit: int = 50) -> List[Dict]:
        """Returns recent events."""
        return [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "category": e.category.value,
                "source": e.source,
                "message": e.message,
                "metadata": e.metadata
            }
            for e in self.events[-limit:]
        ]
