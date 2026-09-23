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
    await e.speak("neutral", "ok")
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


async def test_edge_decodes_in_memory_and_leaves_no_file_behind(monkeypatch, tmp_path):
    import io

    import numpy as np
    import soundfile as sf

    from src.modules.tts import edge_tts_wrapper

    clip = io.BytesIO()
    sf.write(clip, (np.sin(np.arange(24000) / 10) * 0.3).astype("float32"), 24000, format="MP3")
    mp3 = clip.getvalue()

    class Communicate:
        def __init__(self, text, voice, **kwargs):
            pass

        async def stream(self):
            yield {"type": "WordBoundary"}
            for at in range(0, len(mp3), 700):
                yield {"type": "audio", "data": mp3[at:at + 700]}

    monkeypatch.setattr(edge_tts_wrapper.edge_tts, "Communicate", Communicate)
    monkeypatch.chdir(tmp_path)

    audio, rate = await EdgeTTSWrapper(voice="v").generate_audio("ciao")

    expected, _ = sf.read(io.BytesIO(mp3), dtype="float32")
    assert rate == 24000
    assert np.array_equal(audio, expected)
    assert list(tmp_path.iterdir()) == [], "a temporary file was written"


async def test_edge_streams_the_very_same_samples_it_would_render_whole(monkeypatch):
    import io

    import numpy as np
    import soundfile as sf

    from src.modules.tts import edge_tts_wrapper

    clip = io.BytesIO()
    speech = (np.sin(np.arange(72000) / 7) * 0.3).astype("float32")
    sf.write(clip, speech, 24000, format="MP3")
    mp3 = clip.getvalue()

    class Communicate:
        def __init__(self, text, voice, **kwargs):
            pass

        async def stream(self):
            for at in range(0, len(mp3), 720):
                yield {"type": "audio", "data": mp3[at:at + 720]}

    monkeypatch.setattr(edge_tts_wrapper.edge_tts, "Communicate", Communicate)
    edge = EdgeTTSWrapper(voice="v")

    parts = [part async for part in edge.generate_stream("ciao")]
    whole, rate = await edge.generate_audio("ciao")

    assert len(parts) > 1, "nothing was handed over before the end"
    assert all(r == rate for _, r in parts)
    assert np.array_equal(np.concatenate([p for p, _ in parts]), whole)


async def test_edge_says_so_when_a_prefix_stops_being_a_prefix(monkeypatch, caplog):
    """The streaming rests on each longer stretch decoding to the start of the
    whole. A format change that broke that would have the room hear a repeat or
    a skip, and nothing downstream can see it, so the wrapper has to name it
    rather than hand over audio that only sounds right until it doesn't."""
    import numpy as np

    from src.modules.tts import edge_tts_wrapper

    class Communicate:
        def __init__(self, text, voice, **kwargs):
            pass

        async def stream(self):
            for _ in range(8):
                yield {"type": "audio", "data": b"\x00" * 900}

    def broken_decode(mp3):
        # every longer stretch opens somewhere else, instead of extending
        n = max(1, len(mp3))
        return np.full(n, float(n), dtype="float32"), 24000

    monkeypatch.setattr(edge_tts_wrapper.edge_tts, "Communicate", Communicate)
    monkeypatch.setattr(edge_tts_wrapper, "_decode", broken_decode)

    with caplog.at_level("ERROR", logger="bea.tts.edge"):
        parts = [part async for part in EdgeTTSWrapper(voice="v").generate_stream("ciao")]

    assert parts, "the broken stream stopped delivering audio entirely"
    assert "prefixes" in caplog.text, "the broken prefix invariant went unnamed"
