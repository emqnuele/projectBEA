"""ATLAS service — in-memory domain service with event emission and persistence.

Owns the project/work/decision/artifact registries.
Emits atlas.* events through the provided EventManager.
Persists domain state to disk via AtlasRepository.

This service is the application-service layer for ATLAS. It is consumed
by the web layer and FORGE projection. It does NOT import brain,
consciousness, expression, or any renderer.

Persistence:
  - AtlasRepository writes the full domain snapshot to a JSON file.
  - The event journal (EventManager) is the separate audit trail.
  - On load, the repository restores the domain snapshot; events are
    replayed separately if needed for audit/debug.
  - No renderer details anywhere in persisted data.
"""

import uuid
from typing import Any, Dict, List, Optional

from src.core.events import EventCategory, EventManager, EventSeverity, EventVisibility
from src.utils.logger import get_logger

from .models import (
    AtlasEventType,
    Project,
    ProjectStatus,
    WorkItem,
    WorkItemStatus,
    Milestone,
    MilestoneStatus,
    Decision,
    DecisionStatus,
    Artifact,
    ArtifactKind,
    AtlasSnapshot,
    _now,
)
from .repository import AtlasRepository, AtlasData

logger = get_logger("atlas.service")

# String constants for default parameter values.
_DEFAULT_PRIORITY = "medium"
_DEFAULT_WORK_TYPE = "task"
_DEFAULT_ARTIFACT_KIND = "file"


class AtlasService:
    """In-memory ATLAS domain service with optional persistence.

    Thread-safety is NOT guaranteed; callers should serialize access
    from the running event loop. This is consistent with the rest of
    the ProjectSHURA runtime which runs in a single async context.

    Args:
        event_manager: The shared EventManager for event emission.
        repository: Optional AtlasRepository for persistence. If None,
            a default repository is created (data/atlas/state.json).
            Pass None explicitly in tests to run without persistence.
    """

    SUBSYSTEM = "atlas"
    SOURCE = "atlas.service"
    CATEGORY = EventCategory.AGENT  # ATLAS is orchestration layer

    def __init__(
        self,
        event_manager: EventManager,
        repository: Optional[AtlasRepository] = None,
        storage_path: Optional[str] = None,
    ):
        self.events = event_manager
        if repository is not None:
            self._repository = repository
            self._persistent = True
        elif storage_path is not None:
            self._repository = AtlasRepository(storage_path)
            self._persistent = True
        else:
            self._repository = None
            self._persistent = False
        self._projects: Dict[str, Project] = {}
        self._work_items: Dict[str, WorkItem] = {}
        self._milestones: Dict[str, Milestone] = {}
        self._decisions: Dict[str, Decision] = {}
        self._artifacts: Dict[str, Artifact] = {}
        self._active_project_id: Optional[str] = None
        self._load_from_disk()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_from_disk(self) -> None:
        """Restore domain state from the persistence file, if available."""
        if not self._persistent:
            return
        try:
            data = self._repository.load()
            for p in data.projects:
                proj = Project(**p)
                self._projects[proj.project_id] = proj
            for wi in data.work_items:
                item = WorkItem(**wi)
                self._work_items[item.item_id] = item
            for ms in data.milestones:
                milestone = Milestone(**ms)
                self._milestones[milestone.milestone_id] = milestone
            for d in data.decisions:
                decision = Decision(**d)
                self._decisions[decision.decision_id] = decision
            for a in data.artifacts:
                artifact = Artifact(**a)
                self._artifacts[artifact.artifact_id] = artifact
            self._active_project_id = data.active_project_id
        except Exception as e:
            logger.warning(f"ATLAS load from disk failed, starting fresh: {e}")

    def _persist(self) -> None:
        """Write current domain state to the persistence file."""
        if not self._persistent:
            return
        try:
            data = AtlasData(
                active_project_id=self._active_project_id,
                projects=[p.__dict__ for p in self._projects.values()],
                work_items=[w.__dict__ for w in self._work_items.values()],
                milestones=[m.__dict__ for m in self._milestones.values()],
                decisions=[d.__dict__ for d in self._decisions.values()],
                artifacts=[a.__dict__ for a in self._artifacts.values()],
            )
            self._repository.save(data)
        except Exception as e:
            logger.warning(f"ATLAS persist failed: {e}")

    def reset_persistence(self) -> None:
        """Clear the persisted state file. For testing and reset scenarios."""
        if self._persistent:
            self._repository.clear()

    # ------------------------------------------------------------------
    # Project operations
    # ------------------------------------------------------------------

    def create_project(self, name: str, description: str = "") -> Project:
        pid = str(uuid.uuid4())
        project = Project(project_id=pid, name=name, description=description)
        self._projects[pid] = project
        self._emit(AtlasEventType.PROJECT_CREATED, payload={
            "project_id": pid, "name": name, "description": description,
        })
        if self._active_project_id is None:
            self._active_project_id = pid
        self._persist()
        return project

    def update_project(self, project_id: str, **kwargs) -> Project:
        proj = self._require_project(project_id)
        proj.update(**kwargs)
        self._emit(AtlasEventType.PROJECT_UPDATED, payload={
            "project_id": project_id, "updates": list(kwargs.keys()),
        })
        self._persist()
        return proj

    def set_active_project(self, project_id: str) -> Project:
        if project_id not in self._projects:
            raise KeyError(f"Unknown project: {project_id}")
        previous = self._active_project_id
        self._active_project_id = project_id
        self._emit(AtlasEventType.PROJECT_ACTIVE_CHANGED, payload={
            "project_id": project_id, "previous": previous,
        })
        self._persist()
        return self._projects[project_id]

    def get_project(self, project_id: str) -> Project:
        return self._require_project(project_id)

    def list_projects(self) -> List[Project]:
        return list(self._projects.values())

    def delete_project(self, project_id: str) -> None:
        if project_id not in self._projects:
            raise KeyError(f"Unknown project: {project_id}")
        del self._projects[project_id]
        # cascade delete dependents
        for wi in list(self._work_items.values()):
            if wi.project_id == project_id:
                del self._work_items[wi.item_id]
        for ms in list(self._milestones.values()):
            if ms.project_id == project_id:
                del self._milestones[ms.milestone_id]
        for d in list(self._decisions.values()):
            if d.project_id == project_id:
                del self._decisions[d.decision_id]
        for a in list(self._artifacts.values()):
            if a.project_id == project_id:
                del self._artifacts[a.artifact_id]
        if self._active_project_id == project_id:
            self._active_project_id = None
        self._emit(AtlasEventType.PROJECT_DELETED, payload={"project_id": project_id})
        self._persist()

    # ------------------------------------------------------------------
    # Work item operations
    # ------------------------------------------------------------------

    def create_work_item(
        self,
        project_id: str,
        title: str,
        description: str = "",
        priority: str = _DEFAULT_PRIORITY,
        work_type: str = _DEFAULT_WORK_TYPE,
        depends_on: Optional[List[str]] = None,
        assigned_to: str = "",
    ) -> WorkItem:
        self._require_project(project_id)
        item_id = str(uuid.uuid4())
        item = WorkItem(
            item_id=item_id,
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
            work_type=work_type,
            depends_on=list(depends_on or []),
            assigned_to=assigned_to,
        )
        self._work_items[item_id] = item
        self._emit(AtlasEventType.WORK_ITEM_CREATED, payload={
            "item_id": item_id, "project_id": project_id, "title": title,
            "priority": priority, "work_type": work_type,
        })
        self._persist()
        return item

    def update_work_item(self, item_id: str, **kwargs) -> WorkItem:
        item = self._require_work_item(item_id)
        item.update(**kwargs)
        self._emit(AtlasEventType.WORK_ITEM_UPDATED, payload={
            "item_id": item_id, "updates": list(kwargs.keys()),
        })
        self._persist()
        return item

    def transition_work_item(self, item_id: str, new_status: str) -> WorkItem:
        item = self._require_work_item(item_id)
        previous = item.status
        item.transition(new_status)
        self._emit(AtlasEventType.WORK_ITEM_TRANSITIONED, payload={
            "item_id": item_id, "project_id": item.project_id,
            "from": previous, "to": new_status,
        })
        self._persist()
        return item

    def complete_work_item(self, item_id: str) -> WorkItem:
        return self.transition_work_item(item_id, WorkItemStatus.COMPLETED.value)

    def get_work_item(self, item_id: str) -> WorkItem:
        return self._require_work_item(item_id)

    def list_work_items(
        self, project_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[WorkItem]:
        items = list(self._work_items.values())
        if project_id is not None:
            items = [i for i in items if i.project_id == project_id]
        if status is not None:
            items = [i for i in items if i.status == status]
        return items

    def delete_work_item(self, item_id: str) -> None:
        if item_id not in self._work_items:
            raise KeyError(f"Unknown work item: {item_id}")
        del self._work_items[item_id]
        self._emit(AtlasEventType.WORK_ITEM_DELETED, payload={"item_id": item_id})
        self._persist()

    # ------------------------------------------------------------------
    # Milestone operations
    # ------------------------------------------------------------------

    def create_milestone(
        self,
        project_id: str,
        name: str,
        description: str = "",
        order: int = 0,
        target_date: Optional[float] = None,
    ) -> Milestone:
        self._require_project(project_id)
        mid = str(uuid.uuid4())
        ms = Milestone(
            milestone_id=mid,
            project_id=project_id,
            name=name,
            description=description,
            order=order,
            target_date=target_date,
        )
        self._milestones[mid] = ms
        self._emit(AtlasEventType.MILESTONE_CREATED, payload={
            "milestone_id": mid, "project_id": project_id, "name": name,
        })
        self._persist()
        return ms

    def update_milestone(self, milestone_id: str, **kwargs) -> Milestone:
        ms = self._require_milestone(milestone_id)
        ms.update(**kwargs)
        self._emit(AtlasEventType.MILESTONE_UPDATED, payload={
            "milestone_id": milestone_id, "updates": list(kwargs.keys()),
        })
        self._persist()
        return ms

    def complete_milestone(self, milestone_id: str) -> Milestone:
        ms = self._require_milestone(milestone_id)
        ms.status = MilestoneStatus.COMPLETED.value
        ms.completed_at = _now()
        ms.updated_at = _now()
        self._emit(AtlasEventType.MILESTONE_COMPLETED, payload={
            "milestone_id": milestone_id, "project_id": ms.project_id,
        })
        self._persist()
        return ms

    def get_milestone(self, milestone_id: str) -> Milestone:
        return self._require_milestone(milestone_id)

    def list_milestones(self, project_id: Optional[str] = None) -> List[Milestone]:
        items = list(self._milestones.values())
        if project_id is not None:
            items = [m for m in items if m.project_id == project_id]
        return sorted(items, key=lambda m: m.order)

    # ------------------------------------------------------------------
    # Decision operations
    # ------------------------------------------------------------------

    def record_decision(
        self,
        project_id: str,
        title: str,
        context: str = "",
        decision: str = "",
        consequences: str = "",
        decided_by: str = "",
    ) -> Decision:
        self._require_project(project_id)
        did = str(uuid.uuid4())
        d = Decision(
            decision_id=did,
            project_id=project_id,
            title=title,
            context=context,
            decision=decision,
            consequences=consequences,
            decided_by=decided_by,
        )
        self._decisions[did] = d
        self._emit(AtlasEventType.DECISION_RECORDED, payload={
            "decision_id": did, "project_id": project_id, "title": title,
        })
        self._persist()
        return d

    def get_decision(self, decision_id: str) -> Decision:
        return self._require_decision(decision_id)

    def list_decisions(self, project_id: Optional[str] = None) -> List[Decision]:
        items = list(self._decisions.values())
        if project_id is not None:
            items = [d for d in items if d.project_id == project_id]
        return items

    # ------------------------------------------------------------------
    # Artifact operations
    # ------------------------------------------------------------------

    def add_artifact(
        self,
        project_id: str,
        name: str,
        kind: str = _DEFAULT_ARTIFACT_KIND,
        location: str = "",
        description: str = "",
    ) -> Artifact:
        self._require_project(project_id)
        aid = str(uuid.uuid4())
        a = Artifact(
            artifact_id=aid,
            project_id=project_id,
            name=name,
            kind=kind,
            location=location,
            description=description,
        )
        self._artifacts[aid] = a
        self._emit(AtlasEventType.ARTIFACT_ADDED, payload={
            "artifact_id": aid, "project_id": project_id,
            "name": name, "kind": kind, "location": location,
        })
        self._persist()
        return a

    def get_artifact(self, artifact_id: str) -> Artifact:
        return self._require_artifact(artifact_id)

    def list_artifacts(self, project_id: Optional[str] = None) -> List[Artifact]:
        items = list(self._artifacts.values())
        if project_id is not None:
            items = [a for a in items if a.project_id == project_id]
        return items

    def remove_artifact(self, artifact_id: str) -> None:
        if artifact_id not in self._artifacts:
            raise KeyError(f"Unknown artifact: {artifact_id}")
        del self._artifacts[artifact_id]
        self._emit(AtlasEventType.ARTIFACT_REMOVED, payload={"artifact_id": artifact_id})
        self._persist()

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> AtlasSnapshot:
        """Build a read-only AtlasSnapshot of current state."""
        return AtlasSnapshot(
            projects=list(self._projects.values()),
            work_items=list(self._work_items.values()),
            milestones=list(self._milestones.values()),
            decisions=list(self._decisions.values()),
            artifacts=list(self._artifacts.values()),
            active_project_id=self._active_project_id,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_project(self, project_id: str) -> Project:
        if project_id not in self._projects:
            raise KeyError(f"Unknown project: {project_id}")
        return self._projects[project_id]

    def _require_work_item(self, item_id: str) -> WorkItem:
        if item_id not in self._work_items:
            raise KeyError(f"Unknown work item: {item_id}")
        return self._work_items[item_id]

    def _require_milestone(self, milestone_id: str) -> Milestone:
        if milestone_id not in self._milestones:
            raise KeyError(f"Unknown milestone: {milestone_id}")
        return self._milestones[milestone_id]

    def _require_decision(self, decision_id: str) -> Decision:
        if decision_id not in self._decisions:
            raise KeyError(f"Unknown decision: {decision_id}")
        return self._decisions[decision_id]

    def _require_artifact(self, artifact_id: str) -> Artifact:
        if artifact_id not in self._artifacts:
            raise KeyError(f"Unknown artifact: {artifact_id}")
        return self._artifacts[artifact_id]

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emit an ATLAS event through the EventManager. Non-fatal on failure."""
        try:
            self.events.publish(
                category=self.CATEGORY,
                source=self.SOURCE,
                message=f"ATLAS: {event_type}",
                metadata={
                    "event_type": event_type,
                    "subsystem": self.SUBSYSTEM,
                    "severity": EventSeverity.INFO.value,
                    "visibility": EventVisibility.UI.value,
                    "payload": payload,
                },
            )
        except Exception as e:
            logger.warning(f"ATLAS event emission failed: {e}")
