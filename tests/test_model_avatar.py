"""The 3D body, and the mouth that moves with it.

Everything here runs without a browser: the backend publishes what she is, and
the page is the only thing that knows what three.js is.
"""

import json
import time

import numpy as np
import pytest

from src.core.config import BrainConfig
from src.core.expression import Expression
from src.core.expression.pcm import (
    BRIGHTEST_HZ,
    DARKEST_HZ,
    NEUTRAL_SHAPE,
    envelope,
)
from src.core.stage import StageChannel
from src.modules.avatar.factory import build_avatar
from src.modules.avatar.model3d import Model3DAvatar
from src.modules.avatar.png import PngAvatar
from tests.fakes import FakeCaption


class Obs:
    def set_image(self, *a, **k):
        pass

    def set_media(self, *a, **k):
        pass


class SilentTTS:
    def __init__(self, samples=24000):
        self.samples = samples

    async def generate_audio(self, text, prosody=None):
        rng = np.random.default_rng(0)
        return rng.normal(0, 0.2, self.samples).astype(np.float32), 24000

    async def speak(self, text, output_device_id):
        pass

    def reload_config(self, config):
        pass


class Events:
    def publish(self, *a, **k):
        pass


def config(**stage) -> BrainConfig:
    cfg = BrainConfig()
    cfg.stage = {**cfg.stage, "avatar_backend": "model", "model_path": "data/models/x.vrm", **stage}
    cfg.obs_text_source = ""
    return cfg


# --- the lip sync ------------------------------------------------------------


def opens(frames) -> list:
    return [how_open for how_open, _shape in frames]


def shapes(frames) -> list:
    return [shape for _open, shape in frames]


def tone(hz: float, rate: int = 24000, seconds: float = 1.0, level: float = 0.3):
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False, dtype=np.float32)
    return (level * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def test_the_envelope_is_cheap_enough_to_compute_before_she_speaks():
    """It runs on the turn's critical path, between synthesis and playback."""
    rate, seconds = 24000, 6.0
    t = np.linspace(0, seconds, int(rate * seconds), dtype=np.float32)
    speech = (np.sin(2 * np.pi * 180 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * t)) ** 2)

    started = time.perf_counter()
    frames = envelope(speech.astype(np.float32), rate, 30)
    elapsed = (time.perf_counter() - started) * 1000

    assert len(frames) == int(seconds * 30)
    assert max(opens(frames)) == 1.0 and min(opens(frames)) >= 0.0
    assert elapsed < 25.0, f"{elapsed:.1f} ms is too long to sit in front of playback"


def test_the_envelope_is_small_enough_to_send_whole():
    rate = 24000
    frames = envelope(np.random.default_rng(0).normal(0, 0.2, rate * 6).astype(np.float32), rate, 30)
    payload = len(json.dumps(frames))
    assert payload < 8000, f"{payload} bytes for six seconds is too much for one message"


def test_silence_closes_her_mouth():
    """Or she talks through her own pauses."""
    rate = 24000
    loud = np.random.default_rng(0).normal(0, 0.3, rate).astype(np.float32)
    quiet = np.zeros(rate // 2, dtype=np.float32)
    frames = opens(envelope(np.concatenate([loud, quiet, loud]), rate, 30))

    assert np.mean(frames[:30]) > 0.5
    assert max(frames[30:45]) < 0.01
    assert np.mean(frames[45:]) > 0.5


@pytest.mark.parametrize("audio", [None, np.zeros(0, dtype=np.float32)])
def test_nothing_to_say_moves_no_mouth(audio):
    assert envelope(audio, 24000) == []


def test_a_whisper_is_not_drawn_like_a_shout():
    """Normalising every line against its own peak flattened them all to one."""
    rate = 24000
    rng = np.random.default_rng(0)
    loud = opens(envelope(rng.normal(0, 0.3, rate).astype(np.float32), rate, 30))
    whisper = opens(envelope(rng.normal(0, 0.005, rate).astype(np.float32), rate, 30))

    assert max(loud) == 1.0
    assert max(whisper) < 0.2, "her mouth opened as wide for a whisper as for a shout"
    assert max(whisper) > 0.0, "and it must still move"


def test_a_silent_buffer_does_not_divide_by_its_own_peak():
    frames = envelope(np.zeros(24000, dtype=np.float32), 24000, 30)
    assert frames and set(opens(frames)) == {0.0}


# --- and what shape it is in --------------------------------------------------
#
# One number per frame, dark to bright. It is not a phoneme model and does not
# pretend to be: what it has to get right is that two different vowels do not
# draw the same mouth.


def test_a_dark_sound_and_a_bright_one_are_not_the_same_mouth():
    dark = shapes(envelope(tone(DARKEST_HZ), 24000, 30))
    bright = shapes(envelope(tone(BRIGHTEST_HZ), 24000, 30))

    assert np.mean(dark) < 0.2
    assert np.mean(bright) > 0.8


def test_the_axis_is_ordered_the_way_a_spectrum_is():
    rising = [np.mean(shapes(envelope(tone(hz), 24000, 30)))
              for hz in (400, 700, 1200, 2000)]
    assert rising == sorted(rising)


def test_a_rumble_below_speech_is_still_the_darkest_a_mouth_goes():
    assert np.mean(shapes(envelope(tone(80), 24000, 30))) < 0.05


def test_a_hiss_above_speech_is_still_the_brightest():
    assert np.mean(shapes(envelope(tone(9000), 24000, 30))) > 0.95


def test_silence_has_no_vowel_to_measure_and_does_not_invent_one():
    """A closed mouth reading the noise floor's colour is a mouth twitching."""
    frames = envelope(np.zeros(24000, dtype=np.float32), 24000, 30)
    assert set(shapes(frames)) == {NEUTRAL_SHAPE}


# --- what the backend publishes ---------------------------------------------


def test_the_backend_publishes_weights_not_a_mood_name():
    """The vocabulary of moods stays in Python, where it is tested."""
    channel = StageChannel()
    Model3DAvatar(config(), channel).show("angry", "talking")

    snapshot = channel.snapshot()
    assert snapshot["expressions"]["angry"] == 1.0
    assert snapshot["expressions"]["happy"] == 0.0
    assert snapshot["state"] == "talking"


def test_a_behaviour_plays_when_she_starts_talking_and_not_while_idle():
    channel = StageChannel()
    avatar = Model3DAvatar(config(mood_clips={"angry": "lean_in"}), channel)

    queue = channel.subscribe()
    avatar.show("angry", "idle")
    avatar.show("angry", "talking")

    patches = [queue.get_nowait() for _ in range(queue.qsize())]
    assert "perform" not in patches[0]
    assert patches[1]["perform"] == "lean_in"


def test_a_mood_with_no_behaviour_just_changes_face():
    channel = StageChannel()
    queue = channel.subscribe()
    Model3DAvatar(config(mood_clips={}), channel).show("happy", "talking")

    assert "perform" not in queue.get_nowait()


def test_an_empty_mouth_is_not_published():
    channel = StageChannel()
    queue = channel.subscribe()
    Model3DAvatar(config(), channel).mouth([], 30)

    assert queue.empty()


def test_a_missing_model_is_a_warning_not_a_crash(caplog):
    channel = StageChannel()
    with caplog.at_level("WARNING"):
        avatar = Model3DAvatar(config(model_path=""), channel)
    avatar.show("neutral", "idle")

    assert any("model_path" in r.message for r in caplog.records)


def test_the_backend_needs_a_channel_and_says_so_rather_than_going_quiet(caplog):
    with caplog.at_level("WARNING"):
        avatar = build_avatar(config(), Obs(), publisher=None)
    assert isinstance(avatar, PngAvatar)


# --- end to end through Expression ------------------------------------------


async def test_speaking_hands_the_body_a_face_and_a_mouth():
    channel = StageChannel()
    avatar = Model3DAvatar(config(), channel)
    expression = Expression(config(), SilentTTS(), avatar, FakeCaption(), Events())
    queue = channel.subscribe()

    await expression.speak("sad", "non ce la faccio piu")

    patches = [queue.get_nowait() for _ in range(queue.qsize())]
    faces = [p for p in patches if "expressions" in p]
    mouths = [p for p in patches if "envelope" in p]

    assert faces[0]["expressions"]["sad"] == 1.0
    assert mouths and len(mouths[0]["envelope"]) == 30, "one second of audio at 30 fps"
    assert mouths[0]["envelope_fps"] == 30


async def test_the_mouth_is_told_between_the_talking_face_and_the_idle_one():
    """The page runs the envelope off its own clock; late is out of sync.

    The order on the wire is the contract: she starts talking, the mouth gets
    the shape of the line, and only then does she settle back to idle.
    """
    channel = StageChannel()
    queue = channel.subscribe()
    expression = Expression(config(), SilentTTS(), Model3DAvatar(config(), channel),
                            FakeCaption(), Events())

    await expression.speak("neutral", "ciao")

    patches = [queue.get_nowait() for _ in range(queue.qsize())]
    talking = next(i for i, p in enumerate(patches) if p.get("state") == "talking")
    mouth = next(i for i, p in enumerate(patches) if "envelope" in p)
    idle = next(i for i, p in enumerate(patches) if p.get("state") == "idle")

    assert talking < mouth < idle


async def test_a_lip_sync_failure_never_stops_her_from_speaking(caplog):
    class BrokenMouth(Model3DAvatar):
        def mouth(self, envelope, fps=30):
            raise RuntimeError("the renderer went away")

    channel = StageChannel()
    expression = Expression(config(), SilentTTS(), BrokenMouth(config(), channel),
                            FakeCaption(), Events())

    with caplog.at_level("ERROR"):
        await expression.speak("neutral", "vado avanti comunque")

    assert any("Lip sync failed" in r.message for r in caplog.records)
    assert channel.snapshot()["state"] == "idle", "she finished the line anyway"


def test_the_lip_sync_rate_is_configurable():
    channel = StageChannel()
    queue = channel.subscribe()
    expression = Expression(config(lipsync_fps=60), SilentTTS(),
                            Model3DAvatar(config(), channel), FakeCaption(), Events())

    expression._move_mouth(np.random.default_rng(0).normal(0, 0.2, 24000).astype(np.float32), 24000)

    patch = queue.get_nowait()
    assert patch["envelope_fps"] == 60
    assert len(patch["envelope"]) == 60
