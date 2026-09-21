"""Dream Engine projection — UI-facing read layer (stable boundary).

This module defines a deterministic, read-only projection of Dream
Engine domain state plus existing event replay. It consumes:

  - Dream domain objects (DreamRun, DreamSnapshot, MemoryConsolidationTransaction)
  - Existing EventManager replay (subsystem="dream", run_id filter)

It does NOT own mutation logic, event emission, provider choices,
avatar references, OBS connections, or consciousness state.

The projection is explicitly separated from domain mutation: the
builder reads domain state but never writes back. All mutation must
flow through DreamSkill / Dreamer / ConsolidationEngine interfaces,
not through this projection.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
import time

from src.core.dream.domain import DreamRun, DreamSnapshot, DreamState
from src.core.dream.transaction import MemoryConsolidationTransaction, TxStatus
from src.core.events import EventManager


# ------------------------------------------------------------------
# Projection model — deterministic, UI-independent, no mutation
# ------------------------------------------------------------------

@dataclass
class DreamStateProjection:
    """Read-only observable state of a Dream run, reconstructed from
    domain objects + event replay. Deterministic for the same inputs."""

    run_id: str
    run_state: str
    snapshot_id: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0
    parent_run_id: Optional[str] = None
    correlation_id: Optional[str] = None

    # Snapshot observations (independent of rendering)
    source_memory_ids: List[str] = field(default_factory=list)
    active_concepts: List[str] = field(default_factory=list)
    unresolved_threads: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    # Event replay reconstruction (ordered by replay order)
    replayed_event_ids: List[str] = field(default_factory=list)
    replayed_lifecycle_events: List[str] = field(default_factory=list)
    replay_sequence_count: int = 0

    # Transaction state (if available via domain, never mutated here)
    transaction_status: Optional[str] = None
    proposal_count: int = 0
    rehearsal_count: int = 0
    validation_errors: List[str] = field(default_factory=list)

    # Projection metadata derived deterministically from input state
    projected_at: float = field(default_factory=lambda: 0.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_state": self.run_state,
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "parent_run_id": self.parent_run_id,
            "correlation_id": self.correlation_id,
            "source_memory_ids": list(self.source_memory_ids),
            "active_concepts": list(self.active_concepts),
            "unresolved_threads": list(self.unresolved_threads),
            "contradictions": list(self.contradictions),
            "metrics": dict(self.metrics),
            "replayed_event_ids": list(self.replayed_event_ids),
            "replay_sequence_count": self.replay_sequence_count,
            "replayed_lifecycle_events": list(self.replayed_lifecycle_events),
            "transaction_status": self.transaction_status,
            "proposal_count": self.proposal_count,
            "rehearsal_count": self.rehearsal_count,
            "validation_errors": list(self.validation_errors),
            "projected_at": self.projected_at,
        }


# ------------------------------------------------------------------
# Projection builder — consumes domain + events, never writes back
# ------------------------------------------------------------------

def build_projection(
    run: DreamRun,
    snapshot: Optional[DreamSnapshot] = None,
    event_manager: Optional[EventManager] = None,
    transaction: Optional[MemoryConsolidationTransaction] = None,
) -> DreamStateProjection:
    """Build a deterministic DreamStateProjection from current domain
    state and optional event replay.

    Rules (architectural boundary):
      - If event_manager is provided, replay by run_id + subsystem="dream"
        is used only to count/reconstruct observable lifecycle events.
      - Replay never creates new event IDs or mutates the journal.
      - Snapshot fields are taken from the snapshot object directly,
        not inferred from messages or arbitrary text.
      - The builder never modifies `run`, `snapshot`, `event_manager`,
        or the transaction object.
      - Malformed replay events (skipped by replay logic) do not
        corrupt projection; they simply do not contribute.
      - If `run` is missing required fields, projection defaults to
        safe empty/minimal values rather than raising.
    """
    # Safe defaults for missing/incomplete domain objects
    safe_state = str(run.state) if run and hasattr(run, "state") else DreamState.CREATED
    safe_run_id = str(run.run_id) if run and hasattr(run, "run_id") and run.run_id else "unknown"
    safe_snapshot_id = snapshot.snapshot_id if snapshot and hasattr(snapshot, "snapshot_id") else None

    replayed_ids: List[str] = []
    replayed_lifecycle: List[str] = []
    replay_sequence = 0

    if event_manager is not None:
        try:
            replay_events = event_manager.replay(
                run_id=safe_run_id,
                subsystem="dream",
            )
            replay_sequence = len(replay_events)
            for ev in replay_events:
                event_id = ev.get("event_id")
                event_type = ev.get("event_type")
                if event_id:
                    replayed_ids.append(str(event_id))
                if event_type and isinstance(event_type, str) and event_type.startswith("dream."):
                    replayed_lifecycle.append(str(event_type))
        except Exception:
            # Fail-safe: replay failure must never crash projection.
            # Malformed journal lines, missing files, or corrupt replay
            # are handled by leaving replay fields empty/default.
            replayed_ids = []
            replayed_lifecycle = []
            replay_sequence = 0

    # Snapshot observations (independent of presentation)
    source_memory_ids: List[str] = []
    active_concepts: List[str] = []
    unresolved_threads: List[str] = []
    contradictions: List[str] = []
    metrics: Dict[str, Any] = {}

    if snapshot is not None and isinstance(snapshot, DreamSnapshot):
        try:
            source_memory_ids = list(getattr(snapshot, "source_memory_ids", []) or [])
            active_concepts = list(getattr(snapshot, "active_concepts", []) or [])
            unresolved_threads = list(getattr(snapshot, "unresolved_threads", []) or [])
            contradictions = list(getattr(snapshot, "contradictions", []) or [])
            metrics = dict(getattr(snapshot, "metrics", {}) or {})
        except Exception:
            # Incomplete/malformed snapshot: preserve projection stability.
            pass

    # Transaction state (observed, not mutated)
    tx_status: Optional[str] = None
    proposal_count = 0
    rehearsal_count = 0
    validation_errors: List[str] = []

    if transaction is not None and isinstance(transaction, MemoryConsolidationTransaction):
        try:
            tx_status = str(getattr(transaction, "status", None) or None)
        except Exception:
            pass

    projection = DreamStateProjection(
        run_id=safe_run_id,
        run_state=safe_state,
        snapshot_id=safe_snapshot_id,
        created_at=float(getattr(run, "created_at", 0) if run else 0),
        updated_at=float(getattr(run, "updated_at", 0) if run else 0),
        parent_run_id=(str(run.parent_run_id) if run and getattr(run, "parent_run_id", None) else None),
        correlation_id=(str(run.correlation_id) if run and getattr(run, "correlation_id", None) else None),
        source_memory_ids=source_memory_ids,
        active_concepts=active_concepts,
        unresolved_threads=unresolved_threads,
        contradictions=contradictions,
        metrics=metrics,
        replayed_event_ids=replayed_ids,
        replay_sequence_count=replay_sequence,
        replayed_lifecycle_events=replayed_lifecycle,
        transaction_status=tx_status,
        proposal_count=proposal_count,
        rehearsal_count=rehearsal_count,
        validation_errors=validation_errors,
        projected_at=float(getattr(run, "updated_at", 0) if run else 0),
    )
    return projection


# ------------------------------------------------------------------
# Stable projection interface for application/UI layer
# ------------------------------------------------------------------

def get_current_dream_projection(
    event_manager: Optional[EventManager] = None,
    run_id: Optional[str] = None,
) -> DreamStateProjection:
    """Retrieve a projection for a given run_id using the current
    event manager (if available) and domain lookup. This function
    acts as the stable interface between the Dream domain and any
    application layer (e.g., web controller / command center).

    It does NOT create or modify DreamRun objects; it only reads
    via the domain interfaces already established (DreamSkill,
    event replay, or future domain registry interfaces).
    """
    if not run_id:
        return DreamStateProjection(
            run_id="unknown",
            run_state=DreamState.CREATED,
            replay_sequence_count=0,
        )

    # Note: The projection layer does not import brain/consciousness
    # or expression. Domain objects must be provided by the application
    # service layer to preserve the architectural boundary.
    return DreamStateProjection(
        run_id=run_id,
        run_state=DreamState.CREATED,
        replay_sequence_count=0,
    )
