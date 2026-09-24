"""What she hears is its own setting, and every transcriber reads it.

`language` used to answer two questions at once: what she speaks when nobody
has written to her, and what the transcriber is pinned to. The dashboard only
showed it under "Mind", so someone whose call in italian was transcribed as
japanese, korean and hindi went looking under Hearing and found nothing.
"""

import json
from types import SimpleNamespace

import pytest
from groq import omit

from src.core.config import BrainConfig
from src.modules.STT.groq_stt import GroqSTT
from src.modules.STT.openrouter_stt import OpenRouterSTT
from src.setup.config_plan import apply_answers


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "clip.wav"
    path.write_bytes(b"RIFF....WAVE")
    return str(path)


def _loaded(tmp_path, monkeypatch, data: dict) -> BrainConfig:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    return BrainConfig()


# --- the setting ------------------------------------------------------------


def test_a_fresh_install_detects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert BrainConfig().stt_language == "auto"


def test_a_pin_from_before_the_split_keeps_her_hearing_in_it(tmp_path, monkeypatch):
    """The fix someone applied by hand in config.json must survive the update."""
    config = _loaded(tmp_path, monkeypatch, {"config_version": 1, "language": "it"})
    assert config.stt_language == "it"
    assert config.language == "it"


def test_the_copy_is_resolved_rather_than_verbatim(tmp_path, monkeypatch):
    config = _loaded(tmp_path, monkeypatch, {"config_version": 1, "language": "jp"})
    assert config.stt_language == "ja"


def test_detection_before_the_split_stays_detection(tmp_path, monkeypatch):
    config = _loaded(tmp_path, monkeypatch, {"config_version": 1, "language": "auto"})
    assert config.stt_language == "auto"


def test_the_old_english_default_is_not_copied_as_a_pin(tmp_path, monkeypatch):
    """An unversioned `en` was never chosen, so there is nothing to keep."""
    config = _loaded(tmp_path, monkeypatch, {"language": "en"})
    assert config.stt_language == "auto"


def test_a_hearing_language_already_chosen_is_left_alone(tmp_path, monkeypatch):
    config = _loaded(tmp_path, monkeypatch,
                     {"config_version": 1, "language": "it", "stt_language": "auto"})
    assert config.stt_language == "auto"


def test_the_choice_is_written_down(tmp_path, monkeypatch):
    config = _loaded(tmp_path, monkeypatch, {"config_version": 1, "language": "auto"})
    config.stt_language = "it"
    config.save_to_file()
    assert json.loads((tmp_path / "config.json").read_text())["stt_language"] == "it"
    assert BrainConfig().stt_language == "it"


def test_the_wizard_answer_pins_hearing_too():
    """It pinned the transcriber before the split; a fresh setup must not lose that."""
    answers = {"llm_provider": "openrouter", "llm_model": "x", "llm_key": "k",
               "tts_provider": "edge", "skills": {}, "language": "it"}
    config = apply_answers(BrainConfig(), answers)
    assert config.stt_language == "it"


# --- every transcriber reads it, and only it ---------------------------------


def _config(**overrides) -> BrainConfig:
    config = BrainConfig()
    config.groq_key = "gsk-test"
    config.openrouter_key = "sk-or-test"
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


@pytest.fixture
def groq_sent(monkeypatch):
    sent = {}

    class FakeTranscriptions:
        def create(self, **kwargs):
            sent.update(kwargs)
            return type("R", (), {"text": "ok"})()

    class FakeClient:
        audio = type("A", (), {"transcriptions": FakeTranscriptions()})()

    monkeypatch.setattr("src.modules.STT.groq_stt.Groq", lambda api_key=None, **_: FakeClient())
    return sent


@pytest.fixture
def openrouter_sent(monkeypatch):
    sent = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"text": "ok"}

    def post(url, headers=None, json=None, timeout=None):
        sent.clear()
        sent.update(json or {})
        return FakeResponse()

    monkeypatch.setattr("src.modules.STT.openrouter_stt.requests.Session",
                        lambda: SimpleNamespace(post=post))
    return sent


def test_groq_hears_in_the_hearing_language(groq_sent, audio):
    GroqSTT(_config(language="auto", stt_language="it")).transcribe(audio)
    assert groq_sent["language"] == "it"


def test_groq_ignores_the_language_she_speaks(groq_sent, audio):
    GroqSTT(_config(language="ja", stt_language="auto")).transcribe(audio)
    assert groq_sent["language"] is omit


def test_openrouter_hears_in_the_hearing_language(openrouter_sent, audio):
    OpenRouterSTT(_config(language="auto", stt_language="it")).transcribe(audio)
    assert openrouter_sent["language"] == "it"


def test_openrouter_ignores_the_language_she_speaks(openrouter_sent, audio):
    OpenRouterSTT(_config(language="ja", stt_language="auto")).transcribe(audio)
    assert "language" not in openrouter_sent


def test_a_change_from_the_dashboard_reaches_the_next_turn(openrouter_sent, audio):
    """Saving mutates the live config in place; nothing has to be rebuilt."""
    config = _config(stt_language="auto")
    stt = OpenRouterSTT(config)
    stt.transcribe(audio)
    assert "language" not in openrouter_sent
    config.stt_language = "it"
    stt.transcribe(audio)
    assert openrouter_sent["language"] == "it"


def test_local_whisper_hears_in_the_hearing_language(tmp_path, monkeypatch):
    import wave

    from src.modules.STT.faster_whisper_stt import FasterWhisperSTT

    calls = []

    class FakeModel:
        def transcribe(self, audio, language=None, **kwargs):
            calls.append(language)
            info = SimpleNamespace(language=language or "en", language_probability=0.99)
            return [SimpleNamespace(text="ciao")], info

    monkeypatch.setattr(FasterWhisperSTT, "_load", lambda self: None)
    monkeypatch.setattr(FasterWhisperSTT, "_probe", lambda self: None)
    stt = FasterWhisperSTT(_config(language="ja", stt_language="it"))
    stt.model = FakeModel()

    path = tmp_path / "turn.wav"
    with wave.open(str(path), "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(16000)
        clip.writeframes(b"\x00\x00" * 32000)

    assert stt.transcribe(str(path)) == "ciao"
    assert calls == ["it"]


# --- the doctor --------------------------------------------------------------


def test_the_ears_check_hears_its_own_line_when_hearing_is_pinned_elsewhere():
    """An english line under an italian pin fails a transcriber that works."""
    from src.setup.doctor import _heard_as

    assert _heard_as(_config(language="auto", stt_language="it")) == "en"
    assert _heard_as(_config(language="ja", stt_language="it")) == "ja"


def test_the_ears_check_leaves_a_matching_or_absent_pin_alone():
    from src.setup.doctor import _heard_as

    assert _heard_as(_config(language="it", stt_language="it")) is None
    assert _heard_as(_config(language="it", stt_language="auto")) is None
