"""Does the mood actually reach the engine, and does off really mean off?

The maths is tested in `test_prosody.py`. What is worth pinning here is the
wiring: a mood that never leaves `Expression` is a feature nobody can hear.
"""

import numpy as np
import pytest

from src.core.affect.rules import Affect
from src.core.expression.prosody import Prosody, for_mood
from src.core.expression.voice import Expression
from src.interfaces.base_interfaces import TTSInterface
from src.modules.tts.edge_tts_wrapper import EdgeTTSWrapper
from tests.fakes import FakeAvatar, FakeCaption

T0 = 1_000_000.0


class RecordingTTS(TTSInterface):
    """Keeps every (text, prosody) it was handed."""

    def __init__(self):
        self.calls = []

    async def generate_audio(self, text, prosody=None):
        self.calls.append((text, prosody))
        # nothing to play: these tests are about what the engine was told, and
        # the runner that decides it has no sound card
        return np.zeros(0, dtype=np.float32), 24000

    async def speak(self, text, output_device_id):
        pass

    def reload_config(self, config):
        pass

    @property
    def moods(self):
        return [p for _, p in self.calls]


class Affects:
    """The shape `Expression` reads a standing mood through."""

    def __init__(self, current=Affect(), enabled=True):
        self.current = current
        self.enabled = enabled


class Events:
    def publish(self, *a, **k):
        pass


class Config:
    text_font_size = 40
    text_line_width = 30
    text_lines = 3
    text_min_font_size = 20
    text_font_step = 2
    typing_delay = 0.0
    text_min_duration = 0.0
    obs_text_source = ""
    obs_source_type = "image"
    audio_device_id = None


def expression(tts) -> Expression:
    e = Expression(Config(), tts, FakeAvatar(), FakeCaption(), Events())
    return e


# --- the wiring -------------------------------------------------------------


@pytest.mark.asyncio
async def test_without_an_affect_the_engine_is_told_nothing():
    tts = RecordingTTS()
    await expression(tts).speak("angry", "ma dai")
    assert tts.moods == [None]


@pytest.mark.asyncio
async def test_switching_it_off_is_the_same_as_not_having_it():
    tts = RecordingTTS()
    e = expression(tts)
    e.set_affect(Affects(Affect(-0.9, 0.9, T0), enabled=False))
    await e.speak("angry", "ma dai")
    assert tts.moods == [None]


@pytest.mark.asyncio
async def test_an_angry_line_reaches_the_engine_as_an_angry_voice():
    tts = RecordingTTS()
    e = expression(tts)
    e.set_affect(Affects())
    await e.speak("angry", "ma dai")

    spoken = tts.moods[0]
    assert spoken is not None and not spoken.neutral
    assert spoken.rate > 1.0 and spoken.pitch_hz > 0.0


@pytest.mark.asyncio
async def test_a_neutral_line_from_a_calm_mind_leaves_the_voice_alone():
    tts = RecordingTTS()
    e = expression(tts)
    e.set_affect(Affects())
    await e.speak("normal", "ok")
    assert tts.moods[0].neutral is True


@pytest.mark.asyncio
async def test_the_standing_mood_colours_the_same_words():
    calm, furious = RecordingTTS(), RecordingTTS()

    e = expression(calm)
    e.set_affect(Affects())
    await e.speak("angry", "ma dai")

    e = expression(furious)
    e.set_affect(Affects(Affect(-0.9, 0.9, T0)))
    await e.speak("angry", "ma dai")

    assert furious.moods[0].pitch_hz > calm.moods[0].pitch_hz


@pytest.mark.asyncio
async def test_the_mind_can_say_how_she_felt_when_she_decided():
    """Local speech is rendered in a task started after the turn moved on."""
    tts = RecordingTTS()
    e = expression(tts)
    e.set_affect(Affects(Affect(-0.9, 0.9, T0)))
    await e.speak("angry", "ma dai", feeling=Affect())

    assert tts.moods[0] == for_mood("angry")


# --- the engine translation --------------------------------------------------


def test_edge_leaves_the_configured_voice_untouched_when_nothing_is_felt():
    edge = EdgeTTSWrapper(voice="v", pitch="+5Hz", rate="+10%", volume="+33%")
    assert edge._voice_for(None) == ("+5Hz", "+10%", "+33%")
    assert edge._voice_for(Prosody()) == ("+5Hz", "+10%", "+33%")


def test_edge_moves_the_configured_voice_rather_than_replacing_it():
    edge = EdgeTTSWrapper(voice="v", pitch="+5Hz", rate="+10%", volume="+33%")
    pitch, rate, volume = edge._voice_for(Prosody(rate=1.12, pitch_hz=9.6, volume=1.08))
    assert (pitch, rate) == ("+15Hz", "+23%")
    assert volume == "+44%"
