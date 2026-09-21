"""ATLAS — durable project/work/decision/artifact domain for ProjectSHURA.

ATLAS is the operational/orchestration layer. It owns project registries,
work items, milestones, decisions, and artifacts. It emits atlas.* events
through the existing EventManager and is consumed by the web layer and
FORGE projection.

ATLAS does NOT import brain, consciousness, expression, dream, or any
renderer. The dependency direction is:

    identity → brain/consciousness → events → presence → dream
                                          ↑
                            ATLAS consumes events; provides snapshot
                                          ↑
                            FORGE consumes presence + ATLAS + dream

No renderer details (PNG paths, OBS scene names, Live2D indices, UI
coordinates, CSS state) appear anywhere in ATLAS.
"""

from .models import (
    Project,
    ProjectStatus,
    WorkItem,
    WorkItemStatus,
    WorkItemPriority,
    WorkItemType,
    Milestone,
    MilestoneStatus,
    Decision,
    DecisionStatus,
    Artifact,
    ArtifactKind,
    AtlasSnapshot,
    AtlasEventType,
)
from .service import AtlasService
from .repository import AtlasRepository, AtlasData

__all__ = [
    "Project",
    "ProjectStatus",
    "WorkItem",
    "WorkItemStatus",
    "WorkItemPriority",
    "WorkItemType",
    "Milestone",
    "MilestoneStatus",
    "Decision",
    "DecisionStatus",
    "Artifact",
    "ArtifactKind",
    "AtlasSnapshot",
    "AtlasEventType",
    "AtlasService",
    "AtlasRepository",
    "AtlasData",
]
