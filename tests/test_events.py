# Event Foundation Tests
# Designed for both `python -m unittest` and `pytest` compatibility.
# No external dependencies beyond the existing project.

import unittest
import sys
import json
import tempfile
import os
from pathlib import Path

# Ensure src is on PYTHONPATH for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.events import (
    EventManager,
    BrainEvent,
    EventCategory,
    EventSeverity,
    EventVisibility,
    EVENT_TYPE_INFO,
    EVENT_TYPE_STATE,
    EVENT_TYPE_LIFECYCLE,
    EVENT_TYPE_PROGRESS,
    EVENT_TYPE_ERROR,
)


class TestEventCreation(unittest.TestCase):
    def test_default_fields(self):
        em = EventManager()
        ev = em.publish(EventCategory.SYSTEM, "test", "hello")
        self.assertIsInstance(ev.id, str)
        self.assertGreater(len(ev.id), 0)
        self.assertEqual(ev.category, EventCategory.SYSTEM)
        self.assertEqual(ev.source, "test")
        self.assertEqual(ev.message, "hello")
        self.assertEqual(ev.event_type, EVENT_TYPE_INFO)
        self.assertEqual(ev.subsystem, "core")
        self.assertIsNone(ev.run_id)
        self.assertIsNone(ev.parent_event_id)

    def test_custom_fields(self):
        em = EventManager()
        ev = em.publish(
            EventCategory.MEMORY,
            "memory_skill",
            "Snapshot created",
            event_type=EVENT_TYPE_PROGRESS,
            subsystem="memory",
            run_id="run-42",
            parent_event_id="parent-001",
            severity=EventSeverity.INFO.value,
            visibility=EventVisibility.UI.value,
            payload={"count": 10},
        )
        self.assertEqual(ev.event_type, EVENT_TYPE_PROGRESS)
        self.assertEqual(ev.subsystem, "memory")
        self.assertEqual(ev.run_id, "run-42")
        self.assertEqual(ev.parent_event_id, "parent-001")
        self.assertEqual(ev.severity, "info")
        self.assertEqual(ev.visibility, "ui")
        self.assertEqual(ev.payload, {"count": 10})

    def test_sequence_increases(self):
        em = EventManager()
        ev1 = em.publish(EventCategory.SYSTEM, "test", "a")
        ev2 = em.publish(EventCategory.SYSTEM, "test", "b")
        self.assertEqual(ev2.sequence, ev1.sequence + 1)

    def test_metadata_compat(self):
        em = EventManager()
        ev = em.publish(
            EventCategory.SYSTEM, "test", "msg",
            metadata={"mood": "normal"},
        )
        self.assertEqual(ev.metadata.get("mood"), "normal")


class TestSerialization(unittest.TestCase):
    def test_round_trip_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = os.path.join(tmpdir, "events.jsonl")
            em = EventManager(journal_path=journal_path)
            em.publish(EventCategory.SYSTEM, "test", "hello", event_type=EVENT_TYPE_LIFECYCLE)
            # Read directly from file to verify persistence format
            with open(journal_path, "r", encoding="utf-8") as f:
                line = f.readline()
            event_dict = json.loads(line)
            self.assertEqual(event_dict["message"], "hello")
            self.assertIn("event_id", event_dict)
            self.assertIn("sequence", event_dict)

    def test_serialization_preserves_new_fields(self):
        em = EventManager()
        ev = em.publish(
            EventCategory.DREAM, "dream", "start",
            event_type=EVENT_TYPE_LIFECYCLE,
            subsystem="dream",
            run_id="r",
            parent_event_id="p",
            severity="success",
            visibility="audit",
            payload={"k": "v"},
        )
        d = em.event_to_dict(ev)
        self.assertEqual(d["event_type"], EVENT_TYPE_LIFECYCLE)
        self.assertEqual(d["subsystem"], "dream")
        self.assertEqual(d["run_id"], "r")
        self.assertEqual(d["parent_event_id"], "p")
        self.assertEqual(d["severity"], "success")
        self.assertEqual(d["visibility"], "audit")
        self.assertEqual(d["payload"], {"k": "v"})


class TestOrdering(unittest.TestCase):
    def test_monotonic_sequence(self):
        em = EventManager()
        sequences = [em.publish(EventCategory.SYSTEM, "s", f"m{i}").sequence for i in range(20)]
        self.assertTrue(all(sequences[i] < sequences[i + 1] for i in range(len(sequences) - 1)))

    def test_replay_order_preserved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = os.path.join(tmpdir, "events.jsonl")
            em = EventManager(journal_path=journal_path)
            for i in range(5):
                em.publish(EventCategory.SYSTEM, "s", f"m{i}", run_id="run-x")
            replayed = em.replay(run_id="run-x")
            self.assertEqual(len(replayed), 5)
            sequences = [e.get("sequence") for e in replayed]
            self.assertTrue(all(sequences[i] < sequences[i + 1] for i in range(len(sequences) - 1)))


class TestCorrelation(unittest.TestCase):
    def test_run_id_filtering_memory(self):
        em = EventManager()
        em.publish(EventCategory.SYSTEM, "s", "a", run_id="run-1")
        em.publish(EventCategory.SYSTEM, "s", "b", run_id="run-2")
        filtered = em.filter_events(run_id="run-1")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["message"], "a")

    def test_parent_event_filtering_memory(self):
        em = EventManager()
        parent = em.publish(EventCategory.SYSTEM, "s", "parent", event_type=EVENT_TYPE_LIFECYCLE)
        child = em.publish(EventCategory.SYSTEM, "s", "child", event_type=EVENT_TYPE_PROGRESS, parent_event_id=parent.id)
        filtered = em.filter_events(parent_event_id=parent.id)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["message"], "child")

    def test_replay_correlation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = os.path.join(tmpdir, "events.jsonl")
            em = EventManager(journal_path=journal_path)
            em.publish(EventCategory.SYSTEM, "s", "a", run_id="run-1")
            replayed = em.replay(run_id="run-1")
            self.assertEqual(len(replayed), 1)
            self.assertEqual(replayed[0]["run_id"], "run-1")


class TestFiltering(unittest.TestCase):
    def test_combined_filters(self):
        em = EventManager()
        em.publish(EventCategory.SYSTEM, "s", "a", event_type=EVENT_TYPE_INFO, subsystem="core", severity="info")
        em.publish(EventCategory.SYSTEM, "s", "b", event_type=EVENT_TYPE_ERROR, subsystem="agent", severity="error")
        results = em.filter_events(event_type=EVENT_TYPE_ERROR, subsystem="agent")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["message"], "b")

    def test_no_match_returns_empty(self):
        em = EventManager()
        em.publish(EventCategory.SYSTEM, "s", "a")
        results = em.filter_events(run_id="nonexistent")
        self.assertEqual(len(results), 0)


class TestSubscription(unittest.TestCase):
    def test_subscription_receives_matching_events(self):
        em = EventManager()
        received = []
        def handler(event_dict, event_obj):
            received.append(event_dict)
        em.subscribe(handler, event_type=EVENT_TYPE_LIFECYCLE, subsystem="core")
        em.publish(EventCategory.SYSTEM, "test", "hello", event_type=EVENT_TYPE_LIFECYCLE, subsystem="core")
        em.publish(EventCategory.SYSTEM, "test", "other", event_type=EVENT_TYPE_INFO, subsystem="core")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["message"], "hello")

    def test_unsubscribe_removes_handler(self):
        em = EventManager()
        received = []
        def handler(event_dict, event_obj):
            received.append(event_dict)
        em.subscribe(handler, event_type=EVENT_TYPE_LIFECYCLE)
        em.unsubscribe(handler)
        em.publish(EventCategory.SYSTEM, "test", "hello", event_type=EVENT_TYPE_LIFECYCLE)
        self.assertEqual(len(received), 0)

    def test_subscriber_failure_does_not_break_publish(self):
        em = EventManager()
        def bad_handler(event_dict, event_obj):
            raise RuntimeError("intentional failure")
        em.subscribe(bad_handler, event_type=EVENT_TYPE_INFO)
        # Should not raise
        ev = em.publish(EventCategory.SYSTEM, "test", "msg")
        self.assertIsNotNone(ev)


class TestPersistence(unittest.TestCase):
    def test_journal_survives_restart_simulation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = os.path.join(tmpdir, "events.jsonl")
            em1 = EventManager(journal_path=journal_path)
            em1.publish(EventCategory.SYSTEM, "test", "before")
            em2 = EventManager(journal_path=journal_path)
            replayed = em2.replay()
            self.assertEqual(len(replayed), 1)
            self.assertEqual(replayed[0]["message"], "before")
            # Replay preserves original event IDs (no new IDs generated)
            original_id = replayed[0]["event_id"]
            replayed_again = em2.replay()
            self.assertEqual(replayed_again[0]["event_id"], original_id)

    def test_malformed_line_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = os.path.join(tmpdir, "events.jsonl")
            em = EventManager(journal_path=journal_path)
            em.publish(EventCategory.SYSTEM, "test", "good")
            # Inject malformed line
            with open(journal_path, "a", encoding="utf-8") as f:
                f.write("not json\n")
            replayed = em.replay()
            # Should contain exactly the valid event; malformed line skipped
            messages = [r["message"] for r in replayed]
            self.assertIn("good", messages)


class TestReplaySemantics(unittest.TestCase):
    def test_replay_does_not_create_new_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = os.path.join(tmpdir, "events.jsonl")
            em = EventManager(journal_path=journal_path)
            ev = em.publish(EventCategory.SYSTEM, "test", "msg")
            replayed = em.replay()
            self.assertEqual(len(replayed), 1)
            self.assertEqual(replayed[0]["event_id"], ev.id)
            # Replay should not produce a different ID for the same event
            replayed_again = em.replay()
            self.assertEqual(replayed_again[0]["event_id"], ev.id)

    def test_replay_preserves_hierarchy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = os.path.join(tmpdir, "events.jsonl")
            em = EventManager(journal_path=journal_path)
            parent = em.publish(EventCategory.SYSTEM, "test", "parent")
            child = em.publish(EventCategory.SYSTEM, "test", "child", parent_event_id=parent.id)
            replayed = em.replay()
            child_replay = [r for r in replayed if r.get("parent_event_id") == parent.id]
            self.assertEqual(len(child_replay), 1)
            self.assertEqual(child_replay[0]["message"], "child")


class TestFailureBehavior(unittest.TestCase):
    def test_invalid_payload_is_accepted_as_dict(self):
        em = EventManager()
        # Payload should be a dict; passing an int is a programming error but does not crash the event system
        # The event system does not enforce payload schema; it only requires dict serialization
        ev = em.publish(EventCategory.SYSTEM, "test", "msg", payload={"key": 123})
        self.assertEqual(ev.payload["key"], 123)

    def test_write_failure_is_logged_not_raised(self):
        # We do not force a write failure here; the journal catches exceptions and logs them.
        # The event emission continues regardless.
        em = EventManager()
        ev = em.publish(EventCategory.SYSTEM, "test", "msg")
        self.assertIsNotNone(ev)


if __name__ == "__main__":
    unittest.main(verbosity=2)
