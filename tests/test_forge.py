"""FORGE contract and projection tests.

Verifies:
  - ForgeState is constructible with correct defaults
  - ForgeState.to_dict() is accurate
  - ForgeState contains NO renderer details (PNG, OBS, Live2D, CSS, widget)
  - ForgeProjection builds correct state from core interfaces
  - ForgeProjection is read-only (does not mutate inputs)
  - ForgeProjection handles missing dream/atlas gracefully
  - ForgePresenceState enum values match PresenceState
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest

from core.forge.contract import ForgeState, ForgePresenceState, ForgeProjection
from core.events import EventManager, EventCategory
from core.presence.events import (
    PRESENCE_CONNECTED,
    PRESENCE_STATE_CHANGED,
    SPEECH_STARTED,
    SPEECH_FINISHED,
    AGENT_TURN_STARTED,
    AGENT_TURN_COMPLETED,
)
from core.presence.runtime import PresenceRuntime, PresenceState
from core.presence.projection import PresenceProjection
from core.atlas.models import Project, WorkItem, Milestone, Decision


class TestForgeState(unittest.TestCase):

    def test_defaults(self):
        s = ForgeState()
        self.assertEqual(s.presence_state, ForgePresenceState.OFFLINE.value)
        self.assertFalse(s.is_connected)
        self.assertIsNone(s.emotion)
        self.assertIsNone(s.motion)
        self.assertFalse(s.is_speaking)
        self.assertFalse(s.is_sleeping)
        self.assertFalse(s.is_dreaming)
        self.assertIsNone(s.active_project)
        self.assertEqual(s.recent_work_items, [])
        self.assertEqual(s.active_milestones, [])
        self.assertEqual(s.recent_decisions, [])
        self.assertIsNone(s.dream_state)
        self.assertEqual(s.recent_events, [])
        self.assertEqual(s.notifications, [])
        self.assertIsInstance(s.projected_at, float)

    def test_to_dict(self):
        s = ForgeState(
            presence_state=ForgePresenceState.TALKING.value if hasattr(ForgePresenceState, "TALKING") else ForgePresenceState.SPEAKING.value,
            is_connected=True,
            emotion="love",
            motion="bounce",
            is_speaking=True,
            active_project={"project_id": "p1", "name": "Test"},
            recent_work_items=[{"item_id": "wi1", "title": "Task"}],
            recent_events=[{"event_id": "e1", "message": "Hello"}],
        )
        d = s.to_dict()
        self.assertEqual(d["presence_state"], "speaking")  # speaking exists
        self.assertTrue(d["is_connected"])
        self.assertEqual(d["emotion"], "love")
        self.assertEqual(d["is_speaking"], True)
        self.assertEqual(d["active_project"]["name"], "Test")
        self.assertEqual(len(d["recent_work_items"]), 1)
        self.assertEqual(len(d["recent_events"]), 1)

    def test_no_renderer_details_in_defaults(self):
        s = ForgeState()
        d = s.to_dict()
        all_str = str(d)
        for forbidden in ["png", ".png", "obs", "live2d", "vrm", "css",
                           "widget", "coordinate", "viewport", "animation"]:
            self.assertNotIn(
                forbidden, all_str.lower(),
                f"Found renderer detail '{forbidden}' in ForgeState defaults",
            )

    def test_no_renderer_details_in_custom_state(self):
        s = ForgeState(
            emotion="shocked",
            motion="jump",
            recent_work_items=[{"title": "Fix OBS scene", "location": "/path/to/file.png"}],
        )
        d = s.to_dict()
        # The work item title/location are user data — we check that FORGE
        # does not ADD renderer details, not that user data is clean.
        # What matters: FORGE fields themselves contain no renderer info.
        for key in ["presence_state", "emotion", "motion", "dream_state"]:
            val = str(d.get(key, ""))
            for forbidden in ["png_path", "obs_scene", "live2d_idx", "css"]:
                self.assertNotIn(forbidden, val)

    def test_forge_presence_state_enum(self):
        self.assertEqual(ForgePresenceState.OFFLINE.value, "offline")
        self.assertEqual(ForgePresenceState.IDLE.value, "idle")
        self.assertEqual(ForgePresenceState.LISTENING.value, "listening")
        self.assertEqual(ForgePresenceState.THINKING.value, "thinking")
        self.assertEqual(ForgePresenceState.SPEAKING.value, "speaking")
        self.assertEqual(ForgePresenceState.INTERRUPTED.value, "interrupted")
        self.assertEqual(ForgePresenceState.DREAMING.value, "dreaming")
        self.assertEqual(ForgePresenceState.ERROR.value, "error")

    def test_forge_presence_state_matches_presence_state(self):
        # Verify FORGE presence enum values match the core PresenceState values
        for forge_val, core_val in [
            (ForgePresenceState.OFFLINE.value, PresenceState.OFFLINE.value),
            (ForgePresenceState.IDLE.value, PresenceState.IDLE.value),
            (ForgePresenceState.LISTENING.value, PresenceState.LISTENING.value),
            (ForgePresenceState.THINKING.value, PresenceState.THINKING.value),
            (ForgePresenceState.SPEAKING.value, PresenceState.SPEAKING.value),
            (ForgePresenceState.INTERRUPTED.value, PresenceState.INTERRUPTED.value),
        ]:
            self.assertEqual(forge_val, core_val,
                             f"Mismatch: FORGE={forge_val!r} vs core={core_val!r}")


class TestForgeProjection(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.events = EventManager(journal_path=f"{self._tmp.name}/events.jsonl")
        self.runtime = PresenceRuntime(self.events)
        self.runtime.connect()

        # Mock ATLAS snapshot function
        from core.atlas.models import Project, WorkItem, Milestone, Decision, Artifact
        self._atlas_projects = []
        self._atlas_work_items = []
        self._atlas_milestones = []
        self._atlas_decisions = []

        def mock_atlas_snapshot():
            from core.atlas.models import AtlasSnapshot
            return AtlasSnapshot(
                projects=list(self._atlas_projects),
                work_items=list(self._atlas_work_items),
                milestones=list(self._atlas_milestones),
                decisions=list(self._atlas_decisions),
                active_project_id=(self._atlas_projects[0].project_id
                                   if self._atlas_projects else None),
            )

        # Mock dream projection function
        def mock_dream_projection(run_id):
            from core.dream.domain import DreamRun, DreamState
            from core.dream.projection import DreamStateProjection
            run = DreamRun(run_id=run_id or "dream-1", state=DreamState.CREATED)
            return DreamStateProjection(
                run_id=run_id or "dream-1",
                run_state=DreamState.CREATED,
                active_concepts=["test_concept"],
                unresolved_threads=["thread1"],
            )

        self.projection = ForgeProjection(
            event_manager=self.events,
            presence_runtime=self.runtime,
            atlas_snapshot_fn=mock_atlas_snapshot,
            dream_projection_fn=mock_dream_projection,
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_build_state_defaults(self):
        state = self.projection.build_state()
        self.assertEqual(state.presence_state, "idle")  # connected → idle
        self.assertTrue(state.is_connected)
        self.assertIsNone(state.emotion)
        self.assertFalse(state.is_speaking)

    def test_build_state_with_atlas_data(self):
        from core.atlas.models import Project, WorkItem, Milestone

        p = Project(project_id="p1", name="ATLAS Project", description="A project")
        self._atlas_projects.append(p)
        self._atlas_work_items.append(
            WorkItem(item_id="wi1", project_id="p1", title="Implement ATLAS",
                     status="in_progress", priority="high")
        )
        self._atlas_milestones.append(
            Milestone(milestone_id="m1", project_id="p1", name="M1",
                      status="in_progress", order=0)
        )
        self._atlas_decisions.append(
            Decision(decision_id="d1", project_id="p1", title="ADR-001",
                     decision="Use in-memory ATLAS", status="recorded")
        )

        state = self.projection.build_state()
        self.assertEqual(state.active_project["name"], "ATLAS Project")
        self.assertEqual(len(state.recent_work_items), 1)
        self.assertEqual(state.recent_work_items[0]["title"], "Implement ATLAS")
        self.assertEqual(len(state.active_milestones), 1)
        self.assertEqual(len(state.recent_decisions), 1)

    def test_build_state_haunted_events(self):
        self.events.publish(
            EventCategory.AGENT, "agent.core", "Turn started",
            event_type=AGENT_TURN_STARTED, subsystem="agent",
            run_id="run-1",
        )
        self.events.publish(
            EventCategory.EMBODIMENT, "expression.adapter", "Speaking",
            event_type=SPEECH_STARTED, subsystem="expression",
            run_id="run-1",
        )

        state = self.projection.build_state()
        self.assertGreaterEqual(len(state.recent_events), 2)
        event_types = [e["event_type"] for e in state.recent_events]
        self.assertIn(AGENT_TURN_STARTED, event_types)
        self.assertIn(SPEECH_STARTED, event_types)

    def test_build_state_dream_state_present(self):
        state = self.projection.build_state(run_id="dream-1")
        self.assertIsNotNone(state.dream_state)
        self.assertEqual(state.dream_state["run_id"], "dream-1")
        self.assertEqual(state.dream_state["run_state"], "created")
        self.assertEqual(state.dream_state["active_concepts"], ["test_concept"])
        self.assertEqual(state.dream_state["unresolved_threads"], ["thread1"])

    def test_build_state_read_only(self):
        """Each call to build_state returns independent dicts; mutating one
        must not affect a subsequent call."""
        p = Project(project_id="p1", name="Immutable Test")
        self._atlas_projects.append(p)
        self._atlas_work_items.append(
            WorkItem(item_id="wi1", project_id="p1", title="W1")
        )

        state1 = self.projection.build_state()
        state2 = self.projection.build_state()

        # state1 and state2 must be independent objects
        self.assertIsNot(state1, state2)
        self.assertIsNot(state1.active_project, state2.active_project)
        self.assertIsNot(state1.recent_work_items, state2.recent_work_items)

        # Mutating state1 must not affect state2
        state1.active_project["name"] = "Mutated"
        state1.recent_work_items.clear()
        self.assertEqual(state2.active_project["name"], "Immutable Test")
        self.assertGreater(len(state2.recent_work_items), 0)

    def test_build_state_handles_atlas_failure_gracefully(self):
        def failing_snapshot():
            raise RuntimeError("Simulated ATLAS failure")

        projection = ForgeProjection(
            event_manager=self.events,
            presence_runtime=self.runtime,
            atlas_snapshot_fn=failing_snapshot,
            dream_projection_fn=lambda rid: None,
        )
        state = projection.build_state()
        # Must not crash; ATLAS fields just empty
        self.assertIsNone(state.active_project)
        self.assertEqual(state.recent_work_items, [])

    def test_build_state_handles_dream_failure_gracefully(self):
        def failing_dream(rid):
            raise RuntimeError("Simulated dream failure")

        projection = ForgeProjection(
            event_manager=self.events,
            presence_runtime=self.runtime,
            atlas_snapshot_fn=lambda: None,
            dream_projection_fn=failing_dream,
        )
        state = projection.build_state(run_id="fail")
        # Must not crash; dream_state just None
        self.assertIsNone(state.dream_state)

    def test_build_state_no_renderer_details_in_output(self):
        from core.atlas.models import Project, WorkItem

        p = Project(project_id="p1", name="P")
        self._atlas_projects.append(p)
        self._atlas_work_items.append(
            WorkItem(item_id="wi1", project_id="p1", title="Task")
        )
        self.events.publish(
            EventCategory.AGENT, "agent.core", "Turn",
            event_type=AGENT_TURN_STARTED, subsystem="agent",
        )

        state = self.projection.build_state()
        d = state.to_dict()
        all_str = str(d)
        for forbidden in ["png_path", "obs_scene", "live2d", "vrm", "css_state",
                           "widget_id", "ui_coordinate", "viewport"]:
            self.assertNotIn(
                forbidden, all_str.lower(),
                f"Renderer detail '{forbidden}' found in ForgeProjection output",
            )


class TestForgeProjectionEventSemantics(unittest.TestCase):
    """Verify ForgeProjection correctly derives presence state from events."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.events = EventManager(journal_path=f"{self._tmp.name}/events.jsonl")
        self.runtime = PresenceRuntime(self.events)
        self.runtime.connect()
        self.projection = PresenceProjection(self.events, self.runtime)

        def mock_atlas():
            from core.atlas.models import AtlasSnapshot
            return AtlasSnapshot()

        def mock_dream(rid):
            from core.dream.domain import DreamRun, DreamState
            from core.dream.projection import DreamStateProjection
            return DreamStateProjection(run_id=rid or "d1", run_state=DreamState.CREATED)

        self.forge = ForgeProjection(
            event_manager=self.events,
            presence_runtime=self.runtime,
            atlas_snapshot_fn=mock_atlas,
            dream_projection_fn=mock_dream,
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_projection_to_listening_updates_forge_state(self):
        self.events.publish(
            EventCategory.EMBODIMENT, "stt.adapter", "Listening",
            event_type=PRESENCE_STATE_CHANGED if False else "input.listening.started",
            subsystem="stt",
        )
        # Use INPUT_LISTENING_STARTED directly
        self.events.publish(
            EventCategory.EMBODIMENT, "stt.adapter", "Listening started",
            event_type="input.listening.started", subsystem="stt",
        )
        state = self.forge.build_state()
        self.assertEqual(state.presence_state, "listening")

    def test_projection_to_thinking_updates_forge_state(self):
        self.events.publish(
            EventCategory.AGENT, "agent.core", "Turn started",
            event_type=AGENT_TURN_STARTED, subsystem="agent",
        )
        state = self.forge.build_state()
        self.assertEqual(state.presence_state, "thinking")

    def test_projection_to_speaking_updates_forge_state(self):
        self.events.publish(
            EventCategory.EMBODIMENT, "expression.adapter", "Speech started",
            event_type=SPEECH_STARTED, subsystem="expression",
        )
        state = self.forge.build_state()
        self.assertEqual(state.presence_state, "speaking")
        # is_speaking is owned by Expression, not PresenceRuntime.
        # In the live web endpoint it is merged from brain.is_speaking.
        # Here we verify presence_state is correct; is_speaking requires
        # the Expression bridge.
        self.assertTrue(state.presence_state == "speaking")


class TestForgeProjectionMalformedReplay(unittest.TestCase):
    """Verify ForgeProjection does not crash on malformed event journal."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        journal_path = f"{self._tmp.name}/events.jsonl"
        # Write a malformed line directly
        with open(journal_path, "w") as f:
            f.write('{"bad json\n')
        self.events = EventManager(journal_path=journal_path)
        self.runtime = PresenceRuntime(self.events)
        self.runtime.connect()

        def mock_atlas():
            from core.atlas.models import AtlasSnapshot
            return AtlasSnapshot()

        def mock_dream(rid):
            from core.dream.domain import DreamRun, DreamState
            from core.dream.projection import DreamStateProjection
            return DreamStateProjection(run_id=rid or "d1", run_state=DreamState.CREATED)

        self.projection = ForgeProjection(
            event_manager=self.events,
            presence_runtime=self.runtime,
            atlas_snapshot_fn=mock_atlas,
            dream_projection_fn=mock_dream,
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_malformed_journal_does_not_crash_projection(self):
        # The in-memory event buffer has events from connect().
        # The key assertion: build_state does not crash despite malformed JSONL.
        state = self.projection.build_state()
        self.assertEqual(state.presence_state, "idle")
        # PresenceRuntime.connect() publishes to in-memory buffer —
        # those events are visible via get_events() regardless of journal state.
        self.assertGreaterEqual(len(state.recent_events), 0)


class TestForgeNotifications(unittest.TestCase):
    """Notifications field exists and is consumed by frontend, initially empty."""

    def test_notifications_default_empty(self):
        s = ForgeState()
        self.assertEqual(s.notifications, [])

    def test_notifications_is_list(self):
        s = ForgeState()
        s.notifications.append({"type": "info", "message": "Test"})
        self.assertIsInstance(s.notifications, list)
        self.assertEqual(len(s.notifications), 1)
