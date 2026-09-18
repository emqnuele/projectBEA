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


def test_an_existing_config_keeps_the_language_it_was_given(tmp_path, monkeypatch):
    """The new default must not rewrite a config.json that already says `en`."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text('{"language": "en"}', encoding="utf-8")
    config = BrainConfig()
    config.load_from_file()
    assert config.language == "en"
    assert os.path.exists("config.json")
