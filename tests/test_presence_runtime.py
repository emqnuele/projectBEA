import tempfile
import unittest

from src.core.events import EventCategory, EventManager
from src.core.presence import (
    PRESENCE_CONNECTED,
    PRESENCE_DISCONNECTED,
    PRESENCE_EMOTION_CHANGED,
    PRESENCE_MOTION_REQUESTED,
    PRESENCE_STATE_CHANGED,
    PresenceRuntime,
    PresenceState,
)


class TestPresenceRuntime(unittest.TestCase):
    def tearDown(self):
        self._tmp.cleanup()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.events = EventManager(
            journal_path=f"{self._tmp.name}/events.jsonl"
        )
        self.presence = PresenceRuntime(self.events)

    def test_connect_emits_connected_and_state_change(self):
        self.presence.connect()

        events = self.events.filter_events(subsystem="presence")

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event_type"], PRESENCE_CONNECTED)
        self.assertEqual(events[0]["category"], EventCategory.EMBODIMENT.value)
        self.assertEqual(events[0]["source"], "presence.runtime")

        self.assertEqual(events[1]["event_type"], PRESENCE_STATE_CHANGED)
        self.assertEqual(events[1]["payload"]["from"], "offline")
        self.assertEqual(events[1]["payload"]["to"], "idle")
        self.assertEqual(events[1]["parent_event_id"], events[0]["event_id"])

    def test_connect_is_idempotent(self):
        self.presence.connect()
        self.presence.connect()

        events = self.events.filter_events(subsystem="presence")
        self.assertEqual(len(events), 2)

    def test_state_transition_has_correlation(self):
        self.presence.connect()
        self.presence.set_state(
            PresenceState.THINKING,
            trigger="agent.turn.started",
            run_id="run-123",
        )

        events = self.events.filter_events(
            event_type=PRESENCE_STATE_CHANGED,
            run_id="run-123",
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["from"], "idle")
        self.assertEqual(events[0]["payload"]["to"], "thinking")
        self.assertEqual(
            events[0]["payload"]["trigger"],
            "agent.turn.started",
        )

    def test_emotion_contains_no_renderer_details(self):
        self.presence.connect()
        event = self.presence.set_emotion(
            "love",
            motion="soft_idle",
            run_id="speech-1",
        )

        self.assertEqual(event.event_type, PRESENCE_EMOTION_CHANGED)
        self.assertEqual(event.subsystem, "presence")
        self.assertEqual(event.payload["emotion"], "love")
        self.assertEqual(event.payload["motion"], "soft_idle")

        serialized = self.events.event_to_dict(event)
        forbidden = ("png", "obs", "live2d", "filename", "path")

        for key, value in serialized.items():
            blob = str(value).lower()
            for token in forbidden:
                self.assertNotIn(token, blob)

    def test_motion_request(self):
        self.presence.connect()
        event = self.presence.request_motion(
            "wave",
            duration=1.5,
            run_id="interaction-1",
        )

        self.assertEqual(event.event_type, PRESENCE_MOTION_REQUESTED)
        self.assertEqual(event.payload["motion"], "wave")
        self.assertEqual(event.payload["duration"], 1.5)

    def test_disconnect(self):
        self.presence.connect()
        self.presence.disconnect()

        events = self.events.filter_events(subsystem="presence")
        self.assertEqual(events[-2]["event_type"], PRESENCE_DISCONNECTED)
        self.assertEqual(events[-1]["event_type"], PRESENCE_STATE_CHANGED)
        self.assertEqual(events[-1]["payload"]["to"], "offline")

    def test_emotion_and_motion_are_semantic_only(self):
        self.presence.connect()

        emotion = self.presence.set_emotion(
            "shock",
            motion="recoil",
        )
        motion = self.presence.request_motion(
            "blink",
            duration=0.2,
        )

        for event in (emotion, motion):
            self.assertEqual(event.category, EventCategory.EMBODIMENT)
            self.assertEqual(event.subsystem, "presence")


if __name__ == "__main__":
    unittest.main()
