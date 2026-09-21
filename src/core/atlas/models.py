"""ATLAS domain models — durable project/work/decision representation.

ATLAS owns: project registry, work items, milestones, decisions, artifacts.
It emits atlas.* events through the existing EventManager.
It is NEVER imported by brain/consciousness/expression/dream/presence.

The EventManager continues to own event transport.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


# ------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class WorkItemStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    DECLINED = "declined"


class WorkItemPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkItemType(str, Enum):
    TASK = "task"
    BUG = "bug"
    FEATURE = "feature"
    DECISION = "decision"
    MILESTONE = "milestone"


class MilestoneStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DecisionStatus(str, Enum):
    PROPOSED = "proposed"
    RECORDED = "recorded"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


class ArtifactKind(str, Enum):
    FILE = "file"
    URL = "url"
    DOC = "doc"
    IMAGE = "image"
    AUDIO = "audio"
    CODE = "code"
    OTHER = "other"


# ------------------------------------------------------------------
# Timestamp helper
# ------------------------------------------------------------------

def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


# ------------------------------------------------------------------
# Project
# ------------------------------------------------------------------

@dataclass
class Project:
    """Top-level project container. Owns work items, milestones, decisions, artifacts."""

    project_id: str
    name: str
    description: str = ""
    status: str = ProjectStatus.ACTIVE.value
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.updated_at = _now()


@dataclass
class WorkItem:
    """A unit of work: task, bug, feature, or decision record.

    `depends_on` lists other work item IDs. Status transitions are
    explicit and emitted as events.
    """

    item_id: str
    project_id: str
    title: str
    description: str = ""
    status: str = WorkItemStatus.OPEN.value
    priority: str = WorkItemPriority.MEDIUM.value
    work_type: str = WorkItemType.TASK.value
    depends_on: List[str] = field(default_factory=list)
    assigned_to: str = ""
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    completed_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def transition(self, new_status: str, **kwargs) -> None:
        self.status = new_status
        if new_status == WorkItemStatus.COMPLETED.value:
            self.completed_at = _now()
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.updated_at = _now()


@dataclass
class Milestone:
    """A named phase boundary within a project."""

    milestone_id: str
    project_id: str
    name: str
    description: str = ""
    status: str = MilestoneStatus.PLANNED.value
    target_date: Optional[float] = None
    completed_at: Optional[float] = None
    order: int = 0
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    def update(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.updated_at = _now()


@dataclass
class Decision:
    """An architectural decision record (ADR-lite)."""

    decision_id: str
    project_id: str
    title: str
    context: str = ""
    decision: str = ""
    consequences: str = ""
    decided_at: float = field(default_factory=_now)
    decided_by: str = ""
    status: str = DecisionStatus.RECORDED.value
    supersedes: Optional[str] = None  # decision_id of replaced decision
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Artifact:
    """A reference to an external resource owned by a project."""

    artifact_id: str
    project_id: str
    name: str
    kind: str = ArtifactKind.FILE.value
    location: str = ""
    description: str = ""
    created_at: float = field(default_factory=_now)


# ------------------------------------------------------------------
# Snapshot — read-only projection of full ATLAS state
# ------------------------------------------------------------------

@dataclass
class AtlasSnapshot:
    """Read-only aggregate of all ATLAS domain objects.

    Built by AtlasService.snapshot() or AtlasProjection. Never mutated
    by consumers.
    """

    projects: List[Project] = field(default_factory=list)
    work_items: List[WorkItem] = field(default_factory=list)
    milestones: List[Milestone] = field(default_factory=list)
    decisions: List[Decision] = field(default_factory=list)
    artifacts: List[Artifact] = field(default_factory=list)
    active_project_id: Optional[str] = None
    projected_at: float = field(default_factory=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "projects": [p.__dict__ for p in self.projects],
            "work_items": [w.__dict__ for w in self.work_items],
            "milestones": [m.__dict__ for m in self.milestones],
            "decisions": [d.__dict__ for d in self.decisions],
            "artifacts": [a.__dict__ for a in self.artifacts],
            "active_project_id": self.active_project_id,
            "projected_at": self.projected_at,
        }


# ------------------------------------------------------------------
# Event type constants (emitted through EventManager)
# ------------------------------------------------------------------

class AtlasEventType:
    PROJECT_CREATED = "atlas.project.created"
    PROJECT_UPDATED = "atlas.project.updated"
    PROJECT_ACTIVE_CHANGED = "atlas.project.active_changed"
    PROJECT_DELETED = "atlas.project.deleted"

    WORK_ITEM_CREATED = "atlas.work_item.created"
    WORK_ITEM_UPDATED = "atlas.work_item.updated"
    WORK_ITEM_TRANSITIONED = "atlas.work_item.transitioned"
    WORK_ITEM_DELETED = "atlas.work_item.deleted"

    MILESTONE_CREATED = "atlas.milestone.created"
    MILESTONE_UPDATED = "atlas.milestone.updated"
    MILESTONE_COMPLETED = "atlas.milestone.completed"

    DECISION_RECORDED = "atlas.decision.recorded"
    DECISION_UPDATED = "atlas.decision.updated"

    ARTIFACT_ADDED = "atlas.artifact.added"
    ARTIFACT_REMOVED = "atlas.artifact.removed"

    SNAPSHOT_REQUESTED = "atlas.snapshot.requested"
