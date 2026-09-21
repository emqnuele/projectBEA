"""Dream event emission helpers — uses existing EventContract only.

No new persistence, no new event transport, no duplication of
Subscription/Replay/Journal logic.
"""

from typing import Optional, Dict, Any
import time

# Import the existing event contract (not a new event system)
from src.core.events import (
    EventCategory,
    EventSeverity,
    EventVisibility,
    EVENT_TYPE_INFO,
    EVENT_TYPE_STATE,
    EVENT_TYPE_LIFECYCLE,
    EVENT_TYPE_PROGRESS,
    EVENT_TYPE_ERROR,
)

# ------------------------------------------------------------------
# Dream event taxonomy (matches docs/EVENT_CONTRACT.md future target)
# ------------------------------------------------------------------
EVENT_DREAM_STARTED = "dream.started"
EVENT_DREAM_SNAPSHOT_CREATED = "dream.snapshot_created"
EVENT_DREAM_RECONCILIATION_STARTED = "dream.reconciliation_started"
EVENT_DREAM_RECONCILIATION_COMPLETED = "dream.reconciliation_completed"
EVENT_DREAM_COMPLETED = "dream.completed"
EVENT_DREAM_FAILED = "dream.failed"

# ------------------------------------------------------------------
# Memory consolidation event taxonomy (Phase 3)
# ------------------------------------------------------------------
EVENT_MEMORY_CONSOLIDATION_STARTED = "memory.consolidation_started"
EVENT_MEMORY_REHEARSAL_STARTED = "memory.rehearsal_started"
EVENT_MEMORY_REHEARSAL_COMPLETED = "memory.rehearsal_completed"
EVENT_MEMORY_VALIDATED = "memory.consolidation_validated"
EVENT_MEMORY_COMMITTED = "memory.consolidation_committed"
EVENT_MEMORY_REJECTED = "memory.consolidation_rejected"
EVENT_MEMORY_FAILED = "memory.consolidation_failed"

# ------------------------------------------------------------------
# Event emission helpers (minimal; requires an existing EventManager instance)
# ------------------------------------------------------------------

def emit_dream_started(
    event_manager,
    run_id: str,
    parent_event_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    """Emit dream.started lifecycle event."""
    return event_manager.publish(
        category=EventCategory.DREAM,
        source="dream_engine",
        message=f"Dream started: {run_id}",
        event_type=EVENT_TYPE_LIFECYCLE,
        subsystem="dream",
        run_id=run_id,
        parent_event_id=parent_event_id,
        severity=EventSeverity.INFO.value,
        visibility=EventVisibility.UI.value,
        payload=payload or {},
    )


def emit_dream_snapshot_created(
    event_manager,
    run_id: str,
    snapshot_id: str,
    parent_event_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    return event_manager.publish(
        category=EventCategory.DREAM,
        source="dream_engine",
        message=f"Dream snapshot created: {snapshot_id}",
        event_type=EVENT_DREAM_SNAPSHOT_CREATED,
        subsystem="dream",
        run_id=run_id,
        parent_event_id=parent_event_id,
        severity=EventSeverity.INFO.value,
        visibility=EventVisibility.UI.value,
        payload=payload or {},
    )


def emit_dream_reconciliation_started(
    event_manager,
    run_id: str,
    parent_event_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    return event_manager.publish(
        category=EventCategory.DREAM,
        source="dream_engine",
        message=f"Dream reconciliation started: {run_id}",
        event_type=EVENT_DREAM_RECONCILIATION_STARTED,
        subsystem="dream",
        run_id=run_id,
        parent_event_id=parent_event_id,
        severity=EventSeverity.INFO.value,
        visibility=EventVisibility.UI.value,
        payload=payload or {},
    )


def emit_dream_reconciliation_completed(
    event_manager,
    run_id: str,
    parent_event_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    return event_manager.publish(
        category=EventCategory.DREAM,
        source="dream_engine",
        message=f"Dream reconciliation completed: {run_id}",
        event_type=EVENT_DREAM_RECONCILIATION_COMPLETED,
        subsystem="dream",
        run_id=run_id,
        parent_event_id=parent_event_id,
        severity=EventSeverity.SUCCESS.value,
        visibility=EventVisibility.UI.value,
        payload=payload or {},
    )


def emit_dream_completed(
    event_manager,
    run_id: str,
    parent_event_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    return event_manager.publish(
        category=EventCategory.DREAM,
        source="dream_engine",
        message=f"Dream completed: {run_id}",
        event_type=EVENT_DREAM_COMPLETED,
        subsystem="dream",
        run_id=run_id,
        parent_event_id=parent_event_id,
        severity=EventSeverity.SUCCESS.value,
        visibility=EventVisibility.UI.value,
        payload=payload or {},
    )


def emit_dream_failed(
    event_manager,
    run_id: str,
    parent_event_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    return event_manager.publish(
        category=EventCategory.DREAM,
        source="dream_engine",
        message=f"Dream failed: {run_id}",
        event_type=EVENT_DREAM_FAILED,
        subsystem="dream",
        run_id=run_id,
        parent_event_id=parent_event_id,
        severity=EventSeverity.ERROR.value,
        visibility=EventVisibility.UI.value,
        payload=payload or {},
    )


# Memory consolidation event emission helpers (Phase 3)
# ------------------------------------------------------------------

def emit_memory_consolidation_started(
    event_manager,
    transaction_id: str,
    run_id: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    return event_manager.publish(
        category=EventCategory.MEMORY,
        source="memory_consolidation",
        message=f"Memory consolidation started: {transaction_id}",
        event_type="memory.consolidation_started",
        subsystem="memory",
        run_id=run_id,
        payload=payload or {},
    )


def emit_memory_rehearsal_started(
    event_manager,
    transaction_id: str,
    run_id: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    return event_manager.publish(
        category=EventCategory.MEMORY,
        source="memory_consolidation",
        message=f"Memory rehearsal started: {transaction_id}",
        event_type="memory.rehearsal_started",
        subsystem="memory",
        run_id=run_id,
        payload=payload or {},
    )


def emit_memory_rehearsal_completed(
    event_manager,
    transaction_id: str,
    run_id: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    return event_manager.publish(
        category=EventCategory.MEMORY,
        source="memory_consolidation",
        message=f"Memory rehearsal completed: {transaction_id}",
        event_type="memory.rehearsal_completed",
        subsystem="memory",
        run_id=run_id,
        payload=payload or {},
    )


def emit_memory_validated(
    event_manager,
    transaction_id: str,
    run_id: str,
    valid: bool = True,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    return event_manager.publish(
        category=EventCategory.MEMORY,
        source="memory_consolidation",
        message=f"Memory consolidation validated: {transaction_id} (valid={valid})",
        event_type="memory.consolidation_validated",
        subsystem="memory",
        run_id=run_id,
        severity=EventSeverity.SUCCESS.value if valid else EventSeverity.WARNING.value,
        visibility=EventVisibility.UI.value,
        payload=payload or {},
    )


def emit_memory_committed(
    event_manager,
    transaction_id: str,
    run_id: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    return event_manager.publish(
        category=EventCategory.MEMORY,
        source="memory_consolidation",
        message=f"Memory consolidation committed: {transaction_id}",
        event_type="memory.consolidation_committed",
        subsystem="memory",
        run_id=run_id,
        payload=payload or {},
    )


def emit_memory_rejected(
    event_manager,
    transaction_id: str,
    run_id: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    return event_manager.publish(
        category=EventCategory.MEMORY,
        source="memory_consolidation",
        message=f"Memory consolidation rejected: {transaction_id}",
        event_type="memory.consolidation_rejected",
        subsystem="memory",
        run_id=run_id,
        payload=payload or {},
    )


def emit_memory_failed(
    event_manager,
    transaction_id: str,
    run_id: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Any:
    return event_manager.publish(
        category=EventCategory.MEMORY,
        source="memory_consolidation",
        message=f"Memory consolidation failed: {transaction_id}",
        event_type="memory.consolidation_failed",
        subsystem="memory",
        run_id=run_id,
        payload=payload or {},
    )
