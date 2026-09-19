"""Every transcriber reads `config.language` the same way.

Only the local one ever normalized it. `jp` — which the dashboard's own picker
offers — went to Groq and OpenRouter verbatim, where it is not a language, and
an empty one was sent as an empty pin rather than as "detect it".
"""

import os

import pytest
from groq import omit

from src.core.config import BrainConfig
from src.modules.STT.faster_whisper_stt import normalize_language
from src.modules.STT.groq_stt import GroqSTT
from src.modules.STT.openrouter_stt import OpenRouterSTT


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "clip.wav"
    path.write_bytes(b"RIFF....WAVE")
    return str(path)


def _config(**overrides) -> BrainConfig:
    config = BrainConfig()
    config.groq_key = "gsk-test"
    config.openrouter_key = "sk-or-test"
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


# --- groq -------------------------------------------------------------------


@pytest.fixture
def groq_sent(monkeypatch):
    """Records the keyword arguments that reach the groq client."""
    sent = {}

    class FakeTranscriptions:
        def create(self, **kwargs):
            sent.update(kwargs)
            return type("R", (), {"text": "ok"})()

    class FakeClient:
        audio = type("A", (), {"transcriptions": FakeTranscriptions()})()

    monkeypatch.setattr("src.modules.STT.groq_stt.Groq", lambda api_key=None: FakeClient())
    return sent


def test_groq_is_given_the_resolved_code(groq_sent, audio):
    GroqSTT(_config(language="jp")).transcribe(audio)
    assert groq_sent["language"] == "ja"


def test_groq_is_given_the_language_behind_a_regional_tag(groq_sent, audio):
    GroqSTT(_config(language="it-IT")).transcribe(audio)
    assert groq_sent["language"] == "it"


def test_groq_is_told_to_detect_rather_than_sent_null(groq_sent, audio):
    """The sdk spells "no pin" as its own sentinel; null is not a value it takes."""
    GroqSTT(_config(language="auto")).transcribe(audio)
    assert groq_sent["language"] is omit


def test_groq_detects_rather_than_sending_a_language_nobody_has(groq_sent, audio):
    GroqSTT(_config(language="klingon")).transcribe(audio)
    assert groq_sent["language"] is omit


# --- openrouter -------------------------------------------------------------


@pytest.fixture
def openrouter_sent(monkeypatch):
    """Records the JSON body that reaches the openrouter endpoint."""
    sent = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"text": "ok"}

    def post(url, headers=None, json=None, timeout=None):
        sent.update(json or {})
        return FakeResponse()

    monkeypatch.setattr("src.modules.STT.openrouter_stt.requests.post", post)
    return sent


def test_openrouter_is_given_the_resolved_code(openrouter_sent, audio):
    OpenRouterSTT(_config(language="jp")).transcribe(audio)
    assert openrouter_sent["language"] == "ja"


def test_openrouter_is_not_sent_a_language_when_detecting(openrouter_sent, audio):
    OpenRouterSTT(_config(language="auto")).transcribe(audio)
    assert "language" not in openrouter_sent


# --- local ------------------------------------------------------------------


def test_local_whisper_resolves_the_same_spellings():
    assert normalize_language("jp") == "ja"
    assert normalize_language("it-IT") == "it"
    assert normalize_language("Italiano") == "it"


def test_local_whisper_detects_rather_than_raising_on_nonsense():
    assert normalize_language("klingon") is None
    assert normalize_language("auto") is None
    assert normalize_language("") is None


# --- the default ------------------------------------------------------------


def test_a_fresh_config_detects_rather_than_assuming_english():
    """Pinning `en` romanizes Japanese speech; detection transcribes it."""
    assert BrainConfig().language == "auto"
    assert normalize_language(BrainConfig().language) is None


def test_a_config_written_before_the_setting_existed_stops_pinning_english(
        tmp_path, monkeypatch):
    """`en` there is the default it used to have, not an answer anybody gave.

    This test used to assert the opposite, and the opposite is what every
    updated install shipped with: whisper does not fail on a wrong pin, it
    translates, so italian speech came back as fluent english and nothing said
    why. A file with no `config_version` predates the question being asked.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text('{"language": "en"}', encoding="utf-8")
    config = BrainConfig()
    config.load_from_file()
    assert config.language == "auto"
    assert os.path.exists("config.json"), "her config was rewritten underneath her"


def test_english_chosen_since_then_is_left_alone(tmp_path, monkeypatch):
    """Once the file says which shape it is, `en` is an answer and is kept."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(
        '{"config_version": 1, "language": "en"}', encoding="utf-8")
    config = BrainConfig()
    config.load_from_file()
    assert config.language == "en"


def test_any_other_language_is_never_touched(tmp_path, monkeypatch):
    """Only english was ever a default; everything else was chosen."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text('{"language": "it"}', encoding="utf-8")
    config = BrainConfig()
    config.load_from_file()
    assert config.language == "it"


def test_saving_writes_down_which_shape_the_file_is(tmp_path, monkeypatch):
    """So the migration above runs once rather than every time she starts."""
    import json

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text('{"language": "en"}', encoding="utf-8")
    config = BrainConfig()
    config.language = "en"
    config.save_to_file()

    assert json.loads((tmp_path / "config.json").read_text())["config_version"] == 1
    assert BrainConfig().language == "en", "the choice was migrated away again"
