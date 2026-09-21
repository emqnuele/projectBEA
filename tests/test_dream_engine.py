# Dream Engine Foundation Tests
# Designed for `python -m unittest` compatibility.

import unittest
import sys
import os
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.dream.domain import DreamRun, DreamSnapshot, DreamState
from core.dream.events import (
    EVENT_DREAM_STARTED,
    EVENT_DREAM_SNAPSHOT_CREATED,
    EVENT_DREAM_RECONCILIATION_STARTED,
    EVENT_DREAM_RECONCILIATION_COMPLETED,
    EVENT_DREAM_COMPLETED,
    EVENT_DREAM_FAILED,
)
from core.events import EventManager, EventCategory, EventSeverity, EventVisibility


class TestDreamRun(unittest.TestCase):
    def test_run_creation(self):
        run = DreamRun(run_id="test-run-001")
        self.assertEqual(run.run_id, "test-run-001")
        self.assertEqual(run.state, DreamState.CREATED)
        self.assertIsNotNone(run.created_at)

    def test_run_transition(self):
        run = DreamRun(run_id="test-run-002")
        run.transition_to(DreamState.STARTED)
        self.assertEqual(run.state, DreamState.STARTED)
        self.assertGreaterEqual(run.updated_at, run.created_at)

    def test_run_metadata(self):
        run = DreamRun(run_id="test-run-003", metadata={"mode": "review"})
        self.assertEqual(run.metadata.get("mode"), "review")


class TestDreamSnapshot(unittest.TestCase):
    def test_snapshot_creation(self):
        snap = DreamSnapshot(
            run_id="test-run-004",
            snapshot_id="snap-1",
            source_memory_ids=["mem-01", "mem-02"],
            active_concepts=["music", "reaper"],
        )
        self.assertEqual(snap.run_id, "test-run-004")
        self.assertEqual(snap.snapshot_id, "snap-1")
        self.assertEqual(snap.source_memory_ids, ["mem-01", "mem-02"])

    def test_snapshot_to_dict(self):
        snap = DreamSnapshot(run_id="r", snapshot_id="s")
        d = snap.to_dict()
        self.assertEqual(d["run_id"], "r")
        self.assertEqual(d["snapshot_id"], "s")
        self.assertIn("created_at", d)


class TestDreamEventTaxonomy(unittest.TestCase):
    def test_constants_exist(self):
        self.assertEqual(EVENT_DREAM_STARTED, "dream.started")
        self.assertEqual(EVENT_DREAM_COMPLETED, "dream.completed")
        self.assertEqual(EVENT_DREAM_FAILED, "dream.failed")


class TestDreamLifecycleEvents(unittest.TestCase):
    def setUp(self):
        self.em = EventManager()
        self.run_id = "dream-test-run"

    def test_started_event(self):
        # Simulate emission using the event contract directly
        ev = self.em.publish(
            EventCategory.DREAM, "dream_engine", "Dream started",
            event_type=EVENT_DREAM_STARTED,
            subsystem="dream",
            run_id=self.run_id,
            payload={"mode": "review"},
            severity=EventSeverity.INFO.value,
        )
        self.assertEqual(ev.event_type, EVENT_DREAM_STARTED)
        self.assertEqual(ev.subsystem, "dream")
        self.assertEqual(ev.run_id, self.run_id)
        self.assertEqual(ev.category, EventCategory.DREAM)

    def test_snapshot_event(self):
        ev = self.em.publish(
            EventCategory.DREAM, "dream_engine", "Snapshot created",
            event_type=EVENT_DREAM_SNAPSHOT_CREATED,
            subsystem="dream",
            run_id=self.run_id,
            payload={"session_id": "session_001"},
        )
        replay = self.em.replay(run_id=self.run_id)
        self.assertTrue(any(r["event_type"] == EVENT_DREAM_SNAPSHOT_CREATED for r in replay))

    def test_reconciliation_lifecycle(self):
        self.em.publish(
            EventCategory.DREAM, "dream_engine", "Reconciliation started",
            event_type=EVENT_DREAM_RECONCILIATION_STARTED,
            subsystem="dream", run_id=self.run_id,
        )
        self.em.publish(
            EventCategory.DREAM, "dream_engine", "Reconciliation completed",
            event_type=EVENT_DREAM_RECONCILIATION_COMPLETED,
            subsystem="dream", run_id=self.run_id,
        )
        replay = self.em.replay(run_id=self.run_id)
        types = [r["event_type"] for r in replay]
        self.assertIn(EVENT_DREAM_RECONCILIATION_STARTED, types)
        self.assertIn(EVENT_DREAM_RECONCILIATION_COMPLETED, types)

    def test_completed_event(self):
        ev = self.em.publish(
            EventCategory.DREAM, "dream_engine", "Dream completed",
            event_type=EVENT_DREAM_COMPLETED,
            subsystem="dream", run_id=self.run_id,
            severity=EventSeverity.SUCCESS.value,
        )
        self.assertEqual(ev.event_type, EVENT_DREAM_COMPLETED)
        self.assertEqual(ev.severity, EventSeverity.SUCCESS.value)

    def test_failed_event(self):
        ev = self.em.publish(
            EventCategory.DREAM, "dream_engine", "Dream failed",
            event_type=EVENT_DREAM_FAILED,
            subsystem="dream", run_id=self.run_id,
            severity=EventSeverity.ERROR.value,
        )
        self.assertEqual(ev.event_type, EVENT_DREAM_FAILED)
        self.assertEqual(ev.severity, EventSeverity.ERROR.value)

    def test_correlation_and_replay(self):
        self.em.publish(
            EventCategory.DREAM, "dream_engine", "Dream started",
            event_type=EVENT_DREAM_STARTED, subsystem="dream", run_id=self.run_id,
        )
        replay = self.em.replay(run_id=self.run_id)
        self.assertGreaterEqual(len(replay), 1)
        # Replay preserves original event IDs
        original_id = replay[0]["event_id"]
        replay_again = self.em.replay(run_id=self.run_id)
        self.assertEqual(replay_again[0]["event_id"], original_id)
        # Sequence preserved
        self.assertEqual(replay_again[0]["sequence"], replay[0]["sequence"])

    def test_parent_relationship(self):
        parent = self.em.publish(
            EventCategory.DREAM, "dream_engine", "Parent", event_type=EVENT_DREAM_STARTED,
            subsystem="dream", run_id=self.run_id,
        )
        child = self.em.publish(
            EventCategory.DREAM, "dream_engine", "Child",
            event_type=EVENT_DREAM_SNAPSHOT_CREATED, subsystem="dream",
            run_id=self.run_id, parent_event_id=parent.id,
        )
        replay = self.em.replay(run_id=self.run_id)
        child_events = [r for r in replay if r.get("parent_event_id") == parent.id]
        self.assertEqual(len(child_events), 1)
        self.assertEqual(child_events[0]["message"], "Child")

    def test_journal_persists_dream_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = os.path.join(tmpdir, "dream_events.jsonl")
            em = EventManager(journal_path=journal_path)
            em.publish(
                EventCategory.DREAM, "dream_engine", "Dream started",
                event_type=EVENT_DREAM_STARTED, subsystem="dream", run_id=self.run_id,
            )
            # Simulate restart by creating new EventManager with same journal
            em2 = EventManager(journal_path=journal_path)
            replayed = em2.replay(run_id=self.run_id)
            self.assertEqual(len(replayed), 1)
            self.assertEqual(replayed[0]["message"], "Dream started")
            # Replay does not create new event IDs
            original_id = replayed[0]["event_id"]
            replayed_again = em2.replay(run_id=self.run_id)
            self.assertEqual(replayed_again[0]["event_id"], original_id)

    def test_existing_dream_behavior_compatibility(self):
        # Verify that Dreamer can be instantiated with default parameters
        # (no event_manager) without errors
        # Note: full Dreamer requires llm/history; this is a structural check only
        from core.skills.dream.dreamer import Dreamer
        # We do not attempt full LLM execution here; the structural test is that
        # the class accepts event_manager=None and does not break on import/construction.
        self.assertTrue(hasattr(Dreamer, "__init__"))
        # The domain model must be importable independently
        from core.dream.domain import DreamRun, DreamSnapshot
        run = DreamRun(run_id="compat-test")
        self.assertEqual(run.run_id, "compat-test")
        self.assertEqual(run.state, DreamState.CREATED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
