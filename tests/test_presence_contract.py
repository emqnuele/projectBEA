"""Presence/Event contract verification — projection + event lifecycle."""

import unittest
import sys
import tempfile
import os
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.events import EventManager, EventCategory, EventSeverity
from core.presence import (
    PRESENCE_CONNECTED,
    PRESENCE_DISCONNECTED,
    PRESENCE_STATE_CHANGED,
    PRESENCE_EMOTION_CHANGED,
    PRESENCE_MOTION_REQUESTED,
    SPEECH_STARTED,
    SPEECH_FINISHED,
    SPEECH_INTERRUPTED,
    AGENT_TURN_STARTED,
    AGENT_TURN_COMPLETED,
    AGENT_TURN_FAILED,
    TOOL_STARTED,
    TOOL_PROGRESS,
    TOOL_COMPLETED,
    TOOL_FAILED,
    INPUT_LISTENING_STARTED,
    INPUT_TRANSCRIPT_FINAL,
    INPUT_LISTENING_FINISHED,
    PresenceRuntime,
    PresenceState,
    PresenceProjection,
)


class TestPresenceProjectionStates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.events = EventManager(journal_path=f"{self.tmp.name}/events.jsonl")
        self.runtime = PresenceRuntime(self.events)
        self.projection = PresenceProjection(self.events, self.runtime)
        self.runtime.connect()

    def tearDown(self):
        self.tmp.cleanup()

    def test_projection_to_listening(self):
        self.events.publish(
            EventCategory.EMBODIMENT, "stt.adapter", "Listening",
            event_type=INPUT_LISTENING_STARTED,
            subsystem="stt",
        )
        self.assertEqual(self.runtime.state, PresenceState.LISTENING)

    def test_projection_to_thinking(self):
        self.events.publish(
            EventCategory.AGENT, "agent.core", "Turn started",
            event_type=AGENT_TURN_STARTED,
            subsystem="agent",
        )
        self.assertEqual(self.runtime.state, PresenceState.THINKING)

    def test_projection_to_speaking(self):
        self.events.publish(
            EventCategory.EMBODIMENT, "expression.adapter", "Speech started",
            event_type=SPEECH_STARTED,
            subsystem="expression",
        )
        self.assertEqual(self.runtime.state, PresenceState.SPEAKING)

    def test_projection_to_interrupted(self):
        self.events.publish(
            EventCategory.EMBODIMENT, "expression.adapter", "Speech started",
            event_type=SPEECH_STARTED,
            subsystem="expression",
        )
        self.events.publish(
            EventCategory.EMBODIMENT, "expression.adapter", "Speech interrupted",
            event_type=SPEECH_INTERRUPTED,
            subsystem="expression",
        )
        self.assertEqual(self.runtime.state, PresenceState.INTERRUPTED)

    def test_projection_to_idle_after_speech_finished(self):
        self.events.publish(
            EventCategory.EMBODIMENT, "expression.adapter", "Speech started",
            event_type=SPEECH_STARTED,
            subsystem="expression",
        )
        self.events.publish(
            EventCategory.EMBODIMENT, "expression.adapter", "Speech finished",
            event_type=SPEECH_FINISHED,
            subsystem="expression",
        )
        self.assertEqual(self.runtime.state, PresenceState.IDLE)

    def test_projection_to_idle_after_agent_completed(self):
        self.events.publish(
            EventCategory.AGENT, "agent.core", "Turn started",
            event_type=AGENT_TURN_STARTED,
            subsystem="agent",
        )
        self.events.publish(
            EventCategory.AGENT, "agent.core", "Turn completed",
            event_type=AGENT_TURN_COMPLETED,
            subsystem="agent",
        )
        self.assertEqual(self.runtime.state, PresenceState.IDLE)

    def test_projection_keeps_thinking_on_tool_progress(self):
        # Tool events should not oscillate presence out of THINKING
        self.events.publish(
            EventCategory.AGENT, "agent.core", "Turn started",
            event_type=AGENT_TURN_STARTED,
            subsystem="agent",
        )
        self.events.publish(
            EventCategory.TOOL, "agent.core", "Tool started",
            event_type=TOOL_STARTED,
            subsystem="agent",
        )
        self.events.publish(
            EventCategory.TOOL, "agent.core", "Tool completed",
            event_type=TOOL_COMPLETED,
            subsystem="agent",
        )
        self.assertEqual(self.runtime.state, PresenceState.THINKING)

    def test_projection_offline_on_disconnect(self):
        self.runtime.disconnect()
        self.assertEqual(self.runtime.state, PresenceState.OFFLINE)


class TestAgentTurnLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.events = EventManager(journal_path=f"{self.tmp.name}/events.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_agent_turn_start_completion(self):
        turn_id = "turn-1"
        started = self.events.publish(
            EventCategory.AGENT, "agent.core", "Turn started",
            event_type=AGENT_TURN_STARTED,
            subsystem="agent",
            run_id=turn_id,
        )
        completed = self.events.publish(
            EventCategory.AGENT, "agent.core", "Turn completed",
            event_type=AGENT_TURN_COMPLETED,
            subsystem="agent",
            run_id=turn_id,
            parent_event_id=started.id,
        )
        replayed = self.events.filter_events(run_id=turn_id, subsystem="agent")
        self.assertEqual(len(replayed), 2)
        self.assertEqual(replayed[0]["event_type"], AGENT_TURN_STARTED)
        self.assertEqual(replayed[1]["event_type"], AGENT_TURN_COMPLETED)
        self.assertEqual(replayed[1]["parent_event_id"], started.id)

    def test_agent_turn_failed(self):
        turn_id = "turn-fail"
        started = self.events.publish(
            EventCategory.AGENT, "agent.core", "Turn started",
            event_type=AGENT_TURN_STARTED,
            subsystem="agent",
            run_id=turn_id,
        )
        failed = self.events.publish(
            EventCategory.AGENT, "agent.core", "Turn failed",
            event_type=AGENT_TURN_FAILED,
            subsystem="agent",
            run_id=turn_id,
            parent_event_id=started.id,
            payload={"error": "something broke"},
        )
        replayed = self.events.filter_events(run_id=turn_id)
        self.assertEqual(len(replayed), 2)
        self.assertEqual(replayed[1]["event_type"], AGENT_TURN_FAILED)
        self.assertIn("something broke", replayed[1]["payload"]["error"])


class TestToolLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.events = EventManager(journal_path=f"{self.tmp.name}/events.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_tool_start_completion(self):
        tool_run_id = "tool-1"
        started = self.events.publish(
            EventCategory.TOOL, "agent.core", "Tool started: say_hello",
            event_type=TOOL_STARTED,
            subsystem="agent",
            run_id=tool_run_id,
            payload={"tool_name": "say_hello"},
        )
        completed = self.events.publish(
            EventCategory.TOOL, "agent.core", "Tool completed: say_hello",
            event_type=TOOL_COMPLETED,
            subsystem="agent",
            run_id=tool_run_id,
            parent_event_id=started.id,
            payload={"tool_name": "say_hello", "result": "hello"},
        )
        replayed = self.events.filter_events(run_id=tool_run_id)
        self.assertEqual(len(replayed), 2)
        self.assertEqual(replayed[0]["event_type"], TOOL_STARTED)
        self.assertEqual(replayed[1]["event_type"], TOOL_COMPLETED)

    def test_tool_failure(self):
        tool_run_id = "tool-fail"
        started = self.events.publish(
            EventCategory.TOOL, "agent.core", "Tool started: bad_tool",
            event_type=TOOL_STARTED,
            subsystem="agent",
            run_id=tool_run_id,
            payload={"tool_name": "bad_tool"},
        )
        failed = self.events.publish(
            EventCategory.TOOL, "agent.core", "Tool failed: bad_tool",
            event_type=TOOL_FAILED,
            subsystem="agent",
            run_id=tool_run_id,
            parent_event_id=started.id,
            payload={"tool_name": "bad_tool", "error": "ERROR: unknown"},
        )
        replayed = self.events.filter_events(run_id=tool_run_id)
        self.assertEqual(len(replayed), 2)
        self.assertEqual(replayed[1]["event_type"], TOOL_FAILED)

    def test_tool_progress_is_optional(self):
        # Zero or more progress events is allowed by contract.
        tool_run_id = "tool-progress"
        started = self.events.publish(
            EventCategory.TOOL, "agent.core", "Tool started",
            event_type=TOOL_STARTED,
            subsystem="agent",
            run_id=tool_run_id,
            payload={"tool_name": "slow"},
        )
        progress = self.events.publish(
            EventCategory.TOOL, "agent.core", "Tool progress",
            event_type=TOOL_PROGRESS,
            subsystem="agent",
            run_id=tool_run_id,
            parent_event_id=started.id,
            payload={"tool_name": "slow", "progress": 0.5},
        )
        completed = self.events.publish(
            EventCategory.TOOL, "agent.core", "Tool completed",
            event_type=TOOL_COMPLETED,
            subsystem="agent",
            run_id=tool_run_id,
            parent_event_id=started.id,
            payload={"tool_name": "slow", "result": "done"},
        )
        replayed = self.events.filter_events(run_id=tool_run_id)
        self.assertEqual(len(replayed), 3)
        self.assertEqual(replayed[1]["event_type"], TOOL_PROGRESS)


class TestSTTLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.events = EventManager(journal_path=f"{self.tmp.name}/events.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_stt_start_final_finish(self):
        run_id = "stt-1"
        started = self.events.publish(
            EventCategory.INPUT, "stt.adapter", "Listening started",
            event_type=INPUT_LISTENING_STARTED,
            subsystem="stt",
            run_id=run_id,
            payload={"audio_path_provided": True},
        )
        final_ev = self.events.publish(
            EventCategory.INPUT, "stt.adapter", "Transcript final",
            event_type=INPUT_TRANSCRIPT_FINAL,
            subsystem="stt",
            run_id=run_id,
            parent_event_id=started.id,
            payload={"text": "hello", "confidence": None},
        )
        finished = self.events.publish(
            EventCategory.INPUT, "stt.adapter", "Listening finished",
            event_type=INPUT_LISTENING_FINISHED,
            subsystem="stt",
            run_id=run_id,
            parent_event_id=started.id,
            payload={"status": "completed"},
        )
        replayed = self.events.filter_events(run_id=run_id)
        self.assertEqual(len(replayed), 3)
        self.assertEqual(replayed[0]["event_type"], INPUT_LISTENING_STARTED)
        self.assertEqual(replayed[1]["event_type"], INPUT_TRANSCRIPT_FINAL)
        self.assertEqual(replayed[2]["event_type"], INPUT_LISTENING_FINISHED)
        self.assertEqual(replayed[2]["parent_event_id"], started.id)


class TestPresenceEventSemantics(unittest.TestCase):
    def test_no_renderer_details_in_presence_events(self):
        # PresenceRuntime.set_emotion must not include PNG/OBS/live2d details.
        em = EventManager()
        presence = PresenceRuntime(em)
        presence.connect()
        event = presence.set_emotion("love", motion="soft_idle", run_id="emotion-1")
        serialized = em.event_to_dict(event)
        forbidden = ("png", "obs", "live2d", "filename", "path")
        for key, value in serialized.items():
            blob = str(value).lower()
            for token in forbidden:
                self.assertNotIn(
                    token, blob,
                    f"Forbidden token '{token}' found in presence event at key '{key}'",
                )

    def test_no_duplicate_events_for_idempotent_transitions(self):
        # Calling set_state with the same target should return None (idempotent).
        em = EventManager()
        presence = PresenceRuntime(em)
        presence.connect()
        result = presence.set_state(PresenceState.IDLE)
        self.assertIsNone(result)
        events_before = len(em.filter_events(subsystem="presence"))
        presence.set_state(PresenceState.IDLE)
        events_after = len(em.filter_events(subsystem="presence"))
        self.assertEqual(events_before, events_after)


class TestRunIdAndHierarchy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.events = EventManager(journal_path=f"{self.tmp.name}/events.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_id_preserved_across_replay(self):
        run_id = "run-preserve"
        ev = self.events.publish(
            EventCategory.AGENT, "agent.core", "Turn started",
            event_type=AGENT_TURN_STARTED,
            subsystem="agent",
            run_id=run_id,
        )
        replayed = self.events.replay(run_id=run_id)
        self.assertEqual(len(replayed), 1)
        self.assertEqual(replayed[0]["run_id"], run_id)
        self.assertEqual(replayed[0]["event_id"], ev.id)

    def test_parent_hierarchy_for_speech_lifecycle(self):
        started = self.events.publish(
            EventCategory.EMBODIMENT, "expression.adapter", "Speech started",
            event_type=SPEECH_STARTED,
            subsystem="expression",
            payload={"mood": "normal"},
        )
        finished = self.events.publish(
            EventCategory.EMBODIMENT, "expression.adapter", "Speech finished",
            event_type=SPEECH_FINISHED,
            subsystem="expression",
            parent_event_id=started.id,
        )
        children = self.events.filter_events(parent_event_id=started.id)
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]["event_type"], SPEECH_FINISHED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
