"""ATLAS domain and service tests.

Verifies:
  - Models are constructible with correct defaults
  - Enum values are stable
  - Service CRUD operations work
  - Event emission through EventManager
  - Snapshot is read-only and accurate
  - KeyError on unknown IDs
  - Cascade delete on project removal
  - No renderer details in payloads
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest

from core.atlas.models import (
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
    _now,
)
from core.atlas.service import AtlasService
from core.events import EventManager, EventCategory


class TestAtlasModels(unittest.TestCase):

    def test_project_defaults(self):
        p = Project(project_id="p1", name="Test Project")
        self.assertEqual(p.project_id, "p1")
        self.assertEqual(p.name, "Test Project")
        self.assertEqual(p.description, "")
        self.assertEqual(p.status, ProjectStatus.ACTIVE.value)
        self.assertIsInstance(p.created_at, float)
        self.assertIsInstance(p.updated_at, float)
        self.assertEqual(p.metadata, {})

    def test_project_update(self):
        p = Project(project_id="p1", name="Original")
        p.update(name="Updated", description="A description")
        self.assertEqual(p.name, "Updated")
        self.assertEqual(p.description, "A description")
        self.assertGreater(p.updated_at, p.created_at)

    def test_project_status_enum(self):
        self.assertEqual(ProjectStatus.ACTIVE.value, "active")
        self.assertEqual(ProjectStatus.PAUSED.value, "paused")
        self.assertEqual(ProjectStatus.COMPLETED.value, "completed")
        self.assertEqual(ProjectStatus.ARCHIVED.value, "archived")

    def test_work_item_defaults(self):
        wi = WorkItem(item_id="wi1", project_id="p1", title="Do something")
        self.assertEqual(wi.item_id, "wi1")
        self.assertEqual(wi.project_id, "p1")
        self.assertEqual(wi.title, "Do something")
        self.assertEqual(wi.description, "")
        self.assertEqual(wi.status, WorkItemStatus.OPEN.value)
        self.assertEqual(wi.priority, WorkItemPriority.MEDIUM.value)
        self.assertEqual(wi.work_type, WorkItemType.TASK.value)
        self.assertEqual(wi.depends_on, [])
        self.assertEqual(wi.assigned_to, "")
        self.assertIsNone(wi.completed_at)

    def test_work_item_transition_to_completed(self):
        wi = WorkItem(item_id="wi1", project_id="p1", title="Task")
        self.assertIsNone(wi.completed_at)
        wi.transition(WorkItemStatus.COMPLETED.value)
        self.assertEqual(wi.status, WorkItemStatus.COMPLETED.value)
        self.assertIsNotNone(wi.completed_at)
        self.assertGreater(wi.completed_at, 0)

    def test_work_item_priority_enum(self):
        self.assertEqual(WorkItemPriority.LOW.value, "low")
        self.assertEqual(WorkItemPriority.MEDIUM.value, "medium")
        self.assertEqual(WorkItemPriority.HIGH.value, "high")
        self.assertEqual(WorkItemPriority.CRITICAL.value, "critical")

    def test_work_item_type_enum(self):
        self.assertEqual(WorkItemType.TASK.value, "task")
        self.assertEqual(WorkItemType.BUG.value, "bug")
        self.assertEqual(WorkItemType.FEATURE.value, "feature")
        self.assertEqual(WorkItemType.DECISION.value, "decision")

    def test_milestone_defaults(self):
        ms = Milestone(milestone_id="m1", project_id="p1", name="Phase 1")
        self.assertEqual(ms.milestone_id, "m1")
        self.assertEqual(ms.name, "Phase 1")
        self.assertEqual(ms.status, MilestoneStatus.PLANNED.value)
        self.assertIsNone(ms.target_date)
        self.assertEqual(ms.order, 0)
        self.assertIsNone(ms.completed_at)

    def test_milestone_status_enum(self):
        self.assertEqual(MilestoneStatus.PLANNED.value, "planned")
        self.assertEqual(MilestoneStatus.IN_PROGRESS.value, "in_progress")
        self.assertEqual(MilestoneStatus.COMPLETED.value, "completed")
        self.assertEqual(MilestoneStatus.CANCELLED.value, "cancelled")

    def test_decision_defaults(self):
        d = Decision(
            decision_id="d1", project_id="p1", title="Use FastAPI",
            context="Web framework choice", decision="FastAPI",
            consequences="Lightweight, async", decided_by="viollett",
        )
        self.assertEqual(d.decision_id, "d1")
        self.assertEqual(d.title, "Use FastAPI")
        self.assertEqual(d.context, "Web framework choice")
        self.assertEqual(d.decision, "FastAPI")
        self.assertEqual(d.consequences, "Lightweight, async")
        self.assertEqual(d.decided_by, "viollett")
        self.assertEqual(d.status, DecisionStatus.RECORDED.value)
        self.assertIsNone(d.supersedes)

    def test_decision_status_enum(self):
        self.assertEqual(DecisionStatus.PROPOSED.value, "proposed")
        self.assertEqual(DecisionStatus.RECORDED.value, "recorded")
        self.assertEqual(DecisionStatus.DEPRECATED.value, "deprecated")
        self.assertEqual(DecisionStatus.SUPERSEDED.value, "superseded")

    def test_artifact_defaults(self):
        a = Artifact(
            artifact_id="a1", project_id="p1", name="design.md",
            kind=ArtifactKind.DOC.value, location="/docs/design.md",
            description="Architecture design",
        )
        self.assertEqual(a.artifact_id, "a1")
        self.assertEqual(a.name, "design.md")
        self.assertEqual(a.kind, ArtifactKind.DOC.value)
        self.assertEqual(a.location, "/docs/design.md")
        self.assertEqual(a.description, "Architecture design")

    def test_artifact_kind_enum(self):
        self.assertEqual(ArtifactKind.FILE.value, "file")
        self.assertEqual(ArtifactKind.URL.value, "url")
        self.assertEqual(ArtifactKind.DOC.value, "doc")
        self.assertEqual(ArtifactKind.IMAGE.value, "image")
        self.assertEqual(ArtifactKind.CODE.value, "code")

    def test_atlas_snapshot_empty(self):
        snap = AtlasSnapshot()
        self.assertEqual(snap.projects, [])
        self.assertEqual(snap.work_items, [])
        self.assertEqual(snap.milestones, [])
        self.assertEqual(snap.decisions, [])
        self.assertEqual(snap.artifacts, [])
        self.assertIsNone(snap.active_project_id)
        self.assertIsInstance(snap.projected_at, float)

    def test_atlas_snapshot_to_dict(self):
        snap = AtlasSnapshot(
            projects=[Project(project_id="p1", name="P1")],
            work_items=[WorkItem(item_id="wi1", project_id="p1", title="W1")],
            active_project_id="p1",
        )
        d = snap.to_dict()
        self.assertEqual(len(d["projects"]), 1)
        self.assertEqual(d["projects"][0]["name"], "P1")
        self.assertEqual(len(d["work_items"]), 1)
        self.assertEqual(d["active_project_id"], "p1")

    def test_event_type_constants(self):
        self.assertEqual(AtlasEventType.PROJECT_CREATED, "atlas.project.created")
        self.assertEqual(AtlasEventType.WORK_ITEM_CREATED, "atlas.work_item.created")
        self.assertEqual(AtlasEventType.MILESTONE_CREATED, "atlas.milestone.created")
        self.assertEqual(AtlasEventType.DECISION_RECORDED, "atlas.decision.recorded")
        self.assertEqual(AtlasEventType.ARTIFACT_ADDED, "atlas.artifact.added")
        self.assertTrue(AtlasEventType.PROJECT_CREATED.startswith("atlas."))


class TestAtlasService(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.events = EventManager(journal_path=f"{self._tmp.name}/events.jsonl")
        self.service = AtlasService(self.events)

    def tearDown(self):
        self._tmp.cleanup()

    def test_create_project_emits_event(self):
        p = self.service.create_project("My Project", "A test project")
        self.assertEqual(p.name, "My Project")
        self.assertEqual(p.status, "active")

        events = self.events.filter_events(event_type=AtlasEventType.PROJECT_CREATED)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["name"], "My Project")

    def test_create_and_list_projects(self):
        p1 = self.service.create_project("P1")
        p2 = self.service.create_project("P2")
        projects = self.service.list_projects()
        self.assertEqual(len(projects), 2)
        names = [p.name for p in projects]
        self.assertIn("P1", names)
        self.assertIn("P2", names)

    def test_active_project_auto_set_on_first_create(self):
        p = self.service.create_project("First")
        self.assertEqual(self.service._active_project_id, p.project_id)

    def test_set_active_project(self):
        p1 = self.service.create_project("P1")
        p2 = self.service.create_project("P2")
        self.service.set_active_project(p2.project_id)
        self.assertEqual(self.service._active_project_id, p2.project_id)
        # verify event
        events = self.events.filter_events(event_type=AtlasEventType.PROJECT_ACTIVE_CHANGED)
        found = [e for e in events if e["payload"]["project_id"] == p2.project_id]
        self.assertEqual(len(found), 1)

    def test_get_project(self):
        p = self.service.create_project("Test")
        retrieved = self.service.get_project(p.project_id)
        self.assertEqual(retrieved.name, "Test")

    def test_get_project_unknown_raises(self):
        with self.assertRaises(KeyError):
            self.service.get_project("nonexistent")

    def test_update_project(self):
        p = self.service.create_project("Original")
        updated = self.service.update_project(p.project_id, description="New desc")
        self.assertEqual(updated.description, "New desc")
        self.assertGreater(updated.updated_at, p.created_at)

    def test_create_work_item(self):
        p = self.service.create_project("P")
        wi = self.service.create_work_item(p.project_id, "Implement X")
        self.assertEqual(wi.title, "Implement X")
        self.assertEqual(wi.status, "open")
        self.assertEqual(wi.priority, "medium")
        self.assertEqual(wi.work_type, "task")

    def test_create_work_item_with_options(self):
        p = self.service.create_project("P")
        wi = self.service.create_work_item(
            p.project_id, "Bug fix", priority="high",
            work_type="bug", assigned_to="viollett",
        )
        self.assertEqual(wi.priority, "high")
        self.assertEqual(wi.work_type, "bug")
        self.assertEqual(wi.assigned_to, "viollett")

    def test_create_work_item_for_unknown_project_raises(self):
        with self.assertRaises(KeyError):
            self.service.create_work_item("no-such-project", "Task")

    def test_list_work_items_by_project(self):
        p = self.service.create_project("P")
        self.service.create_work_item(p.project_id, "W1")
        self.service.create_work_item(p.project_id, "W2")
        other = self.service.create_project("Other")
        self.service.create_work_item(other.project_id, "W3")
        items = self.service.list_work_items(project_id=p.project_id)
        self.assertEqual(len(items), 2)

    def test_list_work_items_by_status(self):
        p = self.service.create_project("P")
        wi = self.service.create_work_item(p.project_id, "W")
        self.service.transition_work_item(wi.item_id, "in_progress")
        open_items = self.service.list_work_items(status="open")
        in_progress_items = self.service.list_work_items(status="in_progress")
        self.assertEqual(len(open_items), 0)
        self.assertEqual(len(in_progress_items), 1)

    def test_complete_work_item(self):
        p = self.service.create_project("P")
        wi = self.service.create_work_item(p.project_id, "W")
        completed = self.service.complete_work_item(wi.item_id)
        self.assertEqual(completed.status, "completed")
        self.assertIsNotNone(completed.completed_at)
        # transition event
        events = self.events.filter_events(
            event_type=AtlasEventType.WORK_ITEM_TRANSITIONED,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["to"], "completed")

    def test_work_item_transition_event_payload(self):
        p = self.service.create_project("P")
        wi = self.service.create_work_item(p.project_id, "W")
        self.service.transition_work_item(wi.item_id, "blocked")
        events = self.events.filter_events(
            event_type=AtlasEventType.WORK_ITEM_TRANSITIONED,
        )
        self.assertEqual(events[0]["payload"]["from"], "open")
        self.assertEqual(events[0]["payload"]["to"], "blocked")
        self.assertEqual(events[0]["payload"]["item_id"], wi.item_id)
        self.assertEqual(events[0]["payload"]["project_id"], p.project_id)

    def test_delete_project_cascades(self):
        p = self.service.create_project("P")
        wi = self.service.create_work_item(p.project_id, "W")
        ms = self.service.create_milestone(p.project_id, "M")
        d = self.service.record_decision(p.project_id, "D")
        a = self.service.add_artifact(p.project_id, "file.txt")
        self.service.delete_project(p.project_id)
        self.assertNotIn(p.project_id, self.service._projects)
        self.assertNotIn(wi.item_id, self.service._work_items)
        self.assertNotIn(ms.milestone_id, self.service._milestones)
        self.assertNotIn(d.decision_id, self.service._decisions)
        self.assertNotIn(a.artifact_id, self.service._artifacts)
        self.assertIsNone(self.service._active_project_id)

    def test_snapshot(self):
        p = self.service.create_project("Snapshot Project")
        wi = self.service.create_work_item(p.project_id, "Task 1")
        ms = self.service.create_milestone(p.project_id, "M1")
        d = self.service.record_decision(p.project_id, "D1")
        a = self.service.add_artifact(p.project_id, "doc.md", kind="doc")

        snap = self.service.snapshot()
        self.assertEqual(len(snap.projects), 1)
        self.assertEqual(len(snap.work_items), 1)
        self.assertEqual(len(snap.milestones), 1)
        self.assertEqual(len(snap.decisions), 1)
        self.assertEqual(len(snap.artifacts), 1)
        self.assertEqual(snap.active_project_id, p.project_id)

    def test_snapshot_is_read_only(self):
        p = self.service.create_project("P")
        snap = self.service.snapshot()
        # Mutating the snapshot's internal lists must not affect service
        snap.projects.clear()
        self.assertEqual(len(self.service.list_projects()), 1)

    def test_create_milestone(self):
        p = self.service.create_project("P")
        ms = self.service.create_milestone(p.project_id, "Phase 1", order=1)
        self.assertEqual(ms.name, "Phase 1")
        self.assertEqual(ms.order, 1)
        self.assertEqual(ms.status, "planned")

    def test_list_milestones_sorted_by_order(self):
        p = self.service.create_project("P")
        self.service.create_milestone(p.project_id, "B", order=2)
        self.service.create_milestone(p.project_id, "A", order=1)
        milestones = self.service.list_milestones(p.project_id)
        self.assertEqual([m.name for m in milestones], ["A", "B"])

    def test_complete_milestone(self):
        p = self.service.create_project("P")
        ms = self.service.create_milestone(p.project_id, "M")
        completed = self.service.complete_milestone(ms.milestone_id)
        self.assertEqual(completed.status, "completed")
        self.assertIsNotNone(completed.completed_at)

    def test_record_decision(self):
        p = self.service.create_project("P")
        d = self.service.record_decision(
            p.project_id, "Use omniroute", context="LLM routing",
            decision="Use omniroute provider", decided_by="viollett",
        )
        self.assertEqual(d.title, "Use omniroute")
        self.assertEqual(d.decision, "Use omniroute provider")
        self.assertEqual(d.decided_by, "viollett")
        self.assertEqual(d.status, "recorded")

    def test_add_artifact(self):
        p = self.service.create_project("P")
        a = self.service.add_artifact(p.project_id, "spec.md", kind="doc",
                                        location="/docs/spec.md")
        self.assertEqual(a.name, "spec.md")
        self.assertEqual(a.kind, "doc")
        self.assertEqual(a.location, "/docs/spec.md")

    def test_remove_artifact(self):
        p = self.service.create_project("P")
        a = self.service.add_artifact(p.project_id, "file.txt")
        self.service.remove_artifact(a.artifact_id)
        with self.assertRaises(KeyError):
            self.service.get_artifact(a.artifact_id)

    def test_event_category_is_agent(self):
        self.assertEqual(AtlasService.CATEGORY, EventCategory.AGENT)

    def test_event_subsystem_is_atlas(self):
        p = self.service.create_project("P")
        events = self.events.filter_events(subsystem="atlas")
        self.assertGreater(len(events), 0)
        for e in events:
            self.assertEqual(e["subsystem"], "atlas")

    def test_no_renderer_details_in_payloads(self):
        p = self.service.create_project("P")
        wi = self.service.create_work_item(p.project_id, "W")
        self.service.complete_work_item(wi.item_id)
        events = self.events.filter_events(subsystem="atlas")
        for e in events:
            payload = e.get("payload", {})
            payload_str = str(payload)
            for forbidden in ["png", ".png", "obs", "live2d", "css", "widget"]:
                self.assertNotIn(
                    forbidden, payload_str.lower(),
                    f"Found renderer detail '{forbidden}' in event payload: {payload}",
                )


class TestAtlasEventTypeValues(unittest.TestCase):
    """Verify all AtlasEventType values follow the atlas.* naming convention."""

    def test_all_event_types_start_with_atlas(self):
        for attr in dir(AtlasEventType):
            if attr.startswith("_"):
                continue
            val = getattr(AtlasEventType, attr)
            self.assertTrue(
                val.startswith("atlas."),
                f"AtlasEventType.{attr} = {val!r} does not start with 'atlas.'",
            )

    def test_all_event_types_are_strings(self):
        for attr in dir(AtlasEventType):
            if attr.startswith("_"):
                continue
            val = getattr(AtlasEventType, attr)
            self.assertIsInstance(val, str)
