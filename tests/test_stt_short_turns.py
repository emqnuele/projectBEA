"""What a transcriber does with a turn too short to judge the language of.

Whisper decides which language it is hearing from the audio alone, and on a
turn of half a second it decides wrong: real italian speech cut to length came
back as french at p=0.80, as spanish, and as "Thank you for watching." A call
is full of turns that short — "sì", "no", "aspetta" — so the answer cannot be
to ask better, only to stop asking and use what the last real sentence said.

All three transcribers, because the problem is in the audio: it is no easier
for a hosted whisper than for the one on this machine.
"""

from types import SimpleNamespace

import pytest

from src.core.config import BrainConfig
from src.modules.STT import faster_whisper_stt as local
from src.modules.STT.faster_whisper_stt import FasterWhisperSTT

RATE = local.SAMPLE_RATE


class FakeModel:
    """Records what it was asked, and answers with whatever it was told to."""

    def __init__(self, detects="en", probability=0.99):
        self.detects = detects
        self.probability = probability
        self.calls = []

    def transcribe(self, audio, language=None, **kwargs):
        self.calls.append({"language": language, **kwargs})
        language_used = language or self.detects
        info = type("Info", (), {"language": language_used,
                                 "language_probability": self.probability})()
        return [type("S", (), {"text": "ok"})()], info


@pytest.fixture
def stt(monkeypatch):
    """A transcriber with the model swapped out and the weights never touched."""
    monkeypatch.setattr(FasterWhisperSTT, "_load", lambda self: None)
    monkeypatch.setattr(FasterWhisperSTT, "_probe", lambda self: None)

    config = BrainConfig()
    config.stt_language = "auto"
    engine = FasterWhisperSTT(config)
    engine.model = FakeModel()
    return engine


def _heard(engine, seconds, monkeypatch, path="clip.wav"):
    import numpy as np

    monkeypatch.setattr(local, "decode_audio",
                        lambda *a, **k: np.zeros(int(seconds * RATE), dtype="float32"),
                        raising=False)
    monkeypatch.setattr("faster_whisper.audio.decode_audio",
                        lambda *a, **k: np.zeros(int(seconds * RATE), dtype="float32"))
    return engine._transcribe_file(path, engine.config.stt_language)


# --- the degenerate decode ---------------------------------------------------


def test_whisper_is_left_somewhere_to_fall_back_to(stt, monkeypatch):
    """A single temperature is what returned a repetition it had itself flagged."""
    _heard(stt, 3.0, monkeypatch)
    assert stt.model.calls[0]["temperature"] == local.TEMPERATURES
    assert len(local.TEMPERATURES) > 1


# --- borrowing the language --------------------------------------------------


def test_a_turn_long_enough_is_asked_what_language_it_is(stt, monkeypatch):
    _heard(stt, 3.0, monkeypatch)
    assert stt.model.calls[-1]["language"] is None, "it was pinned instead of detected"


def test_a_short_turn_borrows_the_language_of_the_last_real_sentence(stt, monkeypatch):
    stt.model.detects = "it"
    _heard(stt, 3.0, monkeypatch)

    _heard(stt, 0.4, monkeypatch)
    assert stt.model.calls[-1]["language"] == "it", \
        "half a second of audio was asked which language it was"


def test_a_short_turn_with_nothing_to_borrow_is_still_transcribed(stt, monkeypatch):
    """The first thing said in a call can be short, and dropping it is worse."""
    assert _heard(stt, 0.4, monkeypatch) == "ok"
    assert stt.model.calls[-1]["language"] is None


def test_a_language_heard_unsurely_is_not_remembered(stt, monkeypatch):
    stt.model.detects, stt.model.probability = "fr", 0.6
    _heard(stt, 3.0, monkeypatch)

    _heard(stt, 0.4, monkeypatch)
    assert stt.model.calls[-1]["language"] is None, \
        "a guess it was not sure of was pinned onto the rest of the call"


def test_what_was_heard_goes_stale(stt, monkeypatch):
    from src.modules.STT.heard import HEARD_FOR_SECONDS, HeardLanguage

    clock = {"at": 1000.0}
    stt.heard = HeardLanguage(clock=lambda: clock["at"])
    stt.model.detects = "it"
    _heard(stt, 3.0, monkeypatch)

    clock["at"] += HEARD_FOR_SECONDS + 1
    _heard(stt, 0.4, monkeypatch)
    assert stt.model.calls[-1]["language"] is None, "an old call still decided this one"


def test_a_configured_language_is_still_the_pin_whatever_the_length(stt, monkeypatch):
    stt.config.stt_language = "ja"
    _heard(stt, 0.4, monkeypatch)
    assert stt.model.calls[-1]["language"] == "ja"


# --- and the same for the transcribers that send the audio somewhere ---------


@pytest.fixture
def clip(tmp_path):
    """A real wav, since the hosted engines read the length off its header."""
    import wave

    def write(seconds: float) -> str:
        path = tmp_path / f"clip_{seconds}.wav"
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(b"\x00\x00" * int(seconds * RATE))
        return str(path)

    return write


def test_the_length_of_a_turn_is_read_off_the_header(clip):
    from src.modules.STT.heard import clip_seconds

    assert abs(clip_seconds(clip(2.5)) - 2.5) < 0.01
    assert clip_seconds("not-a-file.wav") == 0.0, "an unreadable clip must not read as short"


def test_groq_borrows_the_language_of_the_last_real_sentence(monkeypatch, clip):
    from src.modules.STT.groq_stt import GroqSTT

    sent = []

    class FakeTranscriptions:
        def create(self, **kwargs):
            sent.append(kwargs)
            return type("R", (), {"text": "ok", "language": "italian"})()

    class FakeClient:
        audio = type("A", (), {"transcriptions": FakeTranscriptions()})()

    monkeypatch.setattr("src.modules.STT.groq_stt.Groq", lambda api_key=None, **_: FakeClient())

    config = BrainConfig()
    config.stt_language = "auto"
    config.groq_key = "gsk-test"
    engine = GroqSTT(config)

    from groq import omit

    engine.transcribe(clip(3.0))
    assert sent[-1]["language"] is omit, "a long turn should be asked, not told"

    engine.transcribe(clip(0.4))
    assert sent[-1]["language"] == "it", \
        "half a second went to the api with no language and came back as anything"


def test_openrouter_borrows_it_too(monkeypatch, clip):
    from src.modules.STT.openrouter_stt import OpenRouterSTT

    sent = []

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"text": "ok", "language": "it"}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent.append(json)
        return FakeResponse()

    monkeypatch.setattr("src.modules.STT.openrouter_stt.requests.Session",
                        lambda: SimpleNamespace(post=fake_post))

    config = BrainConfig()
    config.stt_language = "auto"
    config.openrouter_key = "sk-or-test"
    engine = OpenRouterSTT(config)

    engine.transcribe(clip(3.0))
    assert "language" not in sent[-1], "a long turn should be asked, not told"

    engine.transcribe(clip(0.4))
    assert sent[-1]["language"] == "it"


def test_a_hosted_engine_that_never_says_what_it_heard_still_works(monkeypatch, clip):
    from src.modules.STT.openrouter_stt import OpenRouterSTT

    sent = []

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"text": "ok"}

    monkeypatch.setattr("src.modules.STT.openrouter_stt.requests.Session",
                        lambda: SimpleNamespace(post=lambda url, headers=None, json=None, timeout=None:
                                                (sent.append(json), FakeResponse())[1]))

    config = BrainConfig()
    config.stt_language = "auto"
    config.openrouter_key = "sk-or-test"
    engine = OpenRouterSTT(config)

    engine.transcribe(clip(3.0))
    assert engine.transcribe(clip(0.4)) == "ok"
    assert "language" not in sent[-1], "a language was invented for it"


# --- saying which language it is listening in --------------------------------


def test_the_log_says_which_language_her_ears_are_pinned_to(caplog):
    """The one setting that decides whether she hears anything usable, and the
    only one nothing else would ever mention."""
    from src.modules.STT.factory import build_stt

    config = BrainConfig()
    config.stt_provider = "groq"
    config.groq_key = "gsk-test"

    config.stt_language = "it"
    with caplog.at_level("INFO"):
        build_stt(config)
    assert "Italian" in caplog.text

    caplog.clear()
    config.stt_language = "auto"
    with caplog.at_level("INFO"):
        build_stt(config)
    assert "whatever language" in caplog.text
