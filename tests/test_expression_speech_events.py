import asyncio
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from src.core.events import EventManager
from src.core.expression import Expression
from src.core.presence.events import (
    SPEECH_STARTED,
    SPEECH_FINISHED,
    SPEECH_INTERRUPTED,
)


class FakeTTS:
    def __init__(self, samples=1000, sample_rate=1000):
        self.samples = samples
        self.sample_rate = sample_rate

    async def generate_audio(self, message, prosody=None):
        return [0.0] * self.samples, self.sample_rate

    async def generate_stream(self, message, prosody=None):
        yield [0.0] * self.samples, self.sample_rate


class FakeAvatar:
    """Minimal avatar interface for testing."""
    def show(self, mood, state): pass
    def perform(self, clip): pass
    def mouth(self, envelope, fps): pass
    def set_mood(self, mood): pass
    def set_clip(self, clip): pass
    def set_text(self, text): pass
    def set_image(self, image): pass
    def set_media(self, media): pass
    async def type_text(self, **kwargs): return 16


class FakeCaption:
    """Minimal caption interface for testing."""
    def show(self, mood, state): pass
    def perform(self, clip): pass
    def mouth(self, envelope, fps): pass
    def set_mood(self, mood): pass
    def set_clip(self, clip): pass
    def set_text(self, text): pass
    def set_image(self, image): pass
    def set_media(self, media): pass
    def clear(self): pass
    async def type_text(self, **kwargs): return 16
    async def say(self, text): return 16


def make_config():
    return SimpleNamespace(
        text_font_size=16,
        audio_device_id=0,
        obs_text_source=None,
        obs_source_type="image",
        text_line_width=80,
        text_lines=4,
        text_min_font_size=10,
        text_font_step=1,
        typing_delay=0.0,
        text_min_duration=0.0,
    )


class FakeSoundDevice(types.ModuleType):
    def __init__(self):
        super().__init__("sounddevice")

    def query_devices(self, *args, **kwargs):
        return {"max_output_channels": 2}

    def play(self, *args, **kwargs):
        pass

    def stop(self):
        pass


class TestExpressionSpeechEvents(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = TemporaryDirectory()
        self.events = EventManager(
            journal_path=str(Path(self.tmp.name) / "events.jsonl")
        )
        self.old_sounddevice = sys.modules.get("sounddevice")
        sys.modules["sounddevice"] = FakeSoundDevice()

        self.expression = Expression(
            make_config(),
            FakeTTS(),
            FakeAvatar(),
            FakeCaption(),
            self.events,
        )

    async def asyncTearDown(self):
        if self.old_sounddevice is None:
            sys.modules.pop("sounddevice", None)
        else:
            sys.modules["sounddevice"] = self.old_sounddevice
        self.tmp.cleanup()

    async def test_local_speech_emits_started_and_finished(self):
        await self.expression.speak(
            "love",
            "hello",
            run_id="speech-001",
        )

        events = self.events.filter_events(subsystem="expression")

        self.assertEqual(
            [e["event_type"] for e in events],
            [SPEECH_STARTED, SPEECH_FINISHED],
        )
        self.assertEqual(events[0]["run_id"], "speech-001")
        self.assertEqual(events[1]["run_id"], "speech-001")
        self.assertEqual(events[0]["payload"]["mood"], "love")
        self.assertEqual(
            events[1]["parent_event_id"],
            events[0]["event_id"],
        )
        self.assertEqual(events[0]["source"], "expression.adapter")
        self.assertEqual(events[0]["subsystem"], "expression")

    async def test_interrupt_emits_interrupted_without_finished(self):
        self.expression.tts = FakeTTS(samples=1000, sample_rate=1000)

        task = asyncio.create_task(
            self.expression.speak(
                "normal",
                "long speech",
                run_id="speech-002",
            )
        )

        await asyncio.sleep(0.01)
        await self.expression.interrupt()
        await task

        events = self.events.filter_events(subsystem="expression")

        self.assertEqual(
            [e["event_type"] for e in events],
            [SPEECH_STARTED, SPEECH_INTERRUPTED],
        )
        self.assertEqual(events[0]["run_id"], "speech-002")
        self.assertEqual(events[1]["run_id"], "speech-002")
        self.assertEqual(
            events[1]["parent_event_id"],
            events[0]["event_id"],
        )
        self.assertGreaterEqual(
            events[1]["payload"]["resume_buffer_sec"],
            0.0,
        )

    async def test_remote_generation_does_not_claim_playback(self):
        async def fake_remote(mood, message):
            return b"fake-wav"

        self.expression._speak_remote = fake_remote

        result = await self.expression.speak(
            "normal",
            "remote speech",
            route="remote",
            run_id="speech-003",
        )

        events = self.events.filter_events(subsystem="expression")

        self.assertEqual(result, b"fake-wav")
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
