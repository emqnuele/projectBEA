"""The endpoints the Discord bot posts into.

These carry audio and text from a call into the mind. What they must not do is
answer a failure by handing the caller the engine's internals: the bot writes
whatever it gets back into its own log, and a stack of absolute paths and
driver internals is neither useful there nor something to hand out.
"""

import io
from types import SimpleNamespace

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from src.core import config as config_module
    from src.core.config import BrainConfig
    from src.web import deps
    from src.web.app import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", "config.json")

    class BrainStub:
        def __init__(self):
            self.config = BrainConfig()
            self.stt = None
            self.surface_registry = None
            self.perceived = []

        async def process_discord_interaction(self, path, username, **kw):
            raise RuntimeError(f"/Users/someone/secret/path/{username}.wav is unreadable")

        def perceive_discord_text(self, message, username, channel_id, **kw):
            self.perceived.append((username, message))

    stub = BrainStub()
    previous = deps.brain_instance
    deps.brain_instance = stub
    try:
        yield TestClient(app, raise_server_exceptions=False), stub
    finally:
        deps.brain_instance = previous


def upload():
    return {"file": ("clip.wav", io.BytesIO(b"RIFF....WAVE"), "audio/wav")}


# --- what comes back when transcription fails -------------------------------


def test_a_failed_transcription_is_a_500(client):
    api, _ = client

    answer = api.post("/discord/audio", files=upload(), data={"username": "ema"})

    assert answer.status_code == 500


def test_a_failed_transcription_does_not_hand_back_the_internals(client):
    api, _ = client

    answer = api.post("/discord/audio", files=upload(), data={"username": "ema"})

    detail = answer.json()["detail"]
    assert "/Users/someone/secret/path" not in detail
    assert "RuntimeError" not in detail
    assert "Check the engine log" in detail


def test_the_temp_file_is_cleaned_up_even_when_it_fails(client, tmp_path):
    api, _ = client

    api.post("/discord/audio", files=upload(), data={"username": "ema"})

    leftovers = list((tmp_path / "temp_discord").glob("*.wav"))
    assert leftovers == []


# --- the text side still works ----------------------------------------------


def test_a_chat_message_becomes_a_perception(client):
    api, stub = client

    answer = api.post("/discord/chat", json={"username": "ema", "message": "ciao"})

    assert answer.status_code == 200
    assert answer.json() == {"status": "perceived"}
    assert stub.perceived == [("ema", "ciao")]


def test_an_empty_message_is_refused_before_it_reaches_her(client):
    api, stub = client

    answer = api.post("/discord/chat", json={"username": "ema", "message": "   "})

    assert answer.status_code == 422
    assert stub.perceived == []


# --- overheard speech reports its own failure rather than raising ------------


def test_an_overheard_clip_with_no_stt_is_not_an_error(client):
    # the engine may be running without speech-to-text at all; the bot keeps
    # sending, and a 500 per clip would fill its log with nothing
    api, _ = client

    answer = api.post("/voice/transcript", files=upload(), data={"username": "ema"})

    assert answer.status_code == 200
    assert answer.json() == {"status": "perceived", "transcript": ""}


def test_a_transcription_that_throws_is_reported_not_raised(client):
    api, stub = client
    stub.stt = SimpleNamespace(transcribe=lambda path: (_ for _ in ()).throw(OSError("boom")))

    answer = api.post("/voice/transcript", files=upload(), data={"username": "ema"})

    assert answer.status_code == 200
    assert answer.json()["status"] == "error"
