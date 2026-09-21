"""Dream Engine domain boundary — minimal durable model for Phase 2.

This module defines the core Dream concepts without duplicating event
transport, persistence, or presentation logic.

The Dream subsystem owns:
  - DreamRun lifecycle
  - DreamSnapshot state observations
  - Dream event taxonomy helpers

The EventManager (src/core/events.py) continues to own:
  - event emission, filtering, correlation, replay, journal persistence
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import time
import uuid

# ------------------------------------------------------------------
# Lifecycle states (explicit, replayable)
# ------------------------------------------------------------------
class DreamState(str):
    CREATED = "created"
    STARTED = "started"
    SNAPSHOT_CREATED = "snapshot_created"
    RECONCILIATION_STARTED = "reconciliation_started"
    RECONCILIATION_COMPLETED = "reconciliation_completed"
    COMPLETED = "completed"
    FAILED = "failed"

# ------------------------------------------------------------------
# Dream event taxonomy constants (used with EventCategory / event_type)
# ------------------------------------------------------------------
EVENT_DREAM_STARTED = "dream.started"
EVENT_DREAM_SNAPSHOT_CREATED = "dream.snapshot_created"
EVENT_DREAM_RECONCILIATION_STARTED = "dream.reconciliation_started"
EVENT_DREAM_RECONCILIATION_COMPLETED = "dream.reconciliation_completed"
EVENT_DREAM_COMPLETED = "dream.completed"
EVENT_DREAM_FAILED = "dream.failed"

# ------------------------------------------------------------------
# DreamRun — minimal durable execution model
# ------------------------------------------------------------------
@dataclass
class DreamRun:
    """A single logical Dream execution.

    The run_id is stable and survives replay. The lifecycle is explicit
    and deterministic. No autonomous scheduling behavior is included.
    """

    run_id: str
    state: str = DreamState.CREATED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    parent_run_id: Optional[str] = None
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def transition_to(self, new_state: str, metadata_update: Optional[Dict[str, Any]] = None) -> None:
        self.state = new_state
        self.updated_at = time.time()
        if metadata_update:
            self.metadata.update(metadata_update)

# ------------------------------------------------------------------
# DreamSnapshot — durable state observation independent of UI
# ------------------------------------------------------------------
@dataclass
class DreamSnapshot:
    """A durable observation of Dream subsystem state at a point in time.

    Snapshots are associated with a DreamRun and remain independent of
    presentation concerns (no PNG/avatar/OBS references).
    """

    run_id: str
    snapshot_id: str
    created_at: float = field(default_factory=time.time)
    # Minimal state observations required by current architecture
    source_memory_ids: List[str] = field(default_factory=list)
    active_concepts: List[str] = field(default_factory=list)
    unresolved_threads: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    # Optional: derived metrics (empty by default for future consolidation)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at,
            "source_memory_ids": list(self.source_memory_ids),
            "active_concepts": list(self.active_concepts),
            "unresolved_threads": list(self.unresolved_threads),
            "contradictions": list(self.contradictions),
            "metrics": dict(self.metrics),
        }
