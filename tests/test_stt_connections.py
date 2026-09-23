"""Her ears keep their connection between turns.

A transcription is on the critical path of every voice turn, and a new
connection is a handshake in front of it: ~200ms with eight seconds between
turns, measured against groq. These pin that the connection is kept, and that a
kept connection the far end closed costs a resend rather than the turn.
"""

import wave
from types import SimpleNamespace

import pytest
import requests

from src.core.config import BrainConfig


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "turn.wav"
    with wave.open(str(path), "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(16000)
        clip.writeframes(b"\0\0" * 48000)
    return str(path)


def test_groq_keeps_its_connection_longer_than_a_pause_in_a_call(monkeypatch):
    from src.modules.STT import groq_stt

    asked = {}
    real = groq_stt.DefaultHttpxClient
    monkeypatch.setattr(groq_stt, "DefaultHttpxClient",
                        lambda **kwargs: asked.update(kwargs) or real(**kwargs))
    config = BrainConfig()
    config.groq_key = "gsk-test"
    groq_stt.GroqSTT(config)

    assert asked["limits"].keepalive_expiry == groq_stt.KEEPALIVE_SECONDS
    assert groq_stt.KEEPALIVE_SECONDS > 30, "a conversation pauses for longer than that"


class Reply:
    status_code = 200

    @staticmethod
    def json():
        return {"text": "ciao"}


def openrouter(monkeypatch, *outcomes):
    from src.modules.STT.openrouter_stt import OpenRouterSTT

    queue = list(outcomes)
    sessions = []

    def post(url, headers=None, json=None, timeout=None):
        outcome = queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def build():
        session = SimpleNamespace(post=post)
        sessions.append(session)
        return session

    monkeypatch.setattr("src.modules.STT.openrouter_stt.requests.Session", build)
    config = BrainConfig()
    config.openrouter_key = "sk-or-test"
    config.language = "it"
    return OpenRouterSTT(config), sessions, queue


def test_openrouter_uses_one_session_for_every_turn(monkeypatch, audio):
    engine, sessions, _ = openrouter(monkeypatch, Reply(), Reply(), Reply())

    for _ in range(3):
        assert engine.transcribe(audio) == "ciao"
    assert len(sessions) == 1


def test_openrouter_sends_again_when_the_kept_connection_had_gone(monkeypatch, audio):
    engine, _, queue = openrouter(
        monkeypatch, requests.ConnectionError("Connection aborted."), Reply())

    assert engine.transcribe(audio) == "ciao"
    assert not queue


def test_openrouter_does_not_wait_out_a_timeout_twice(monkeypatch, audio):
    engine, _, queue = openrouter(monkeypatch, requests.ConnectTimeout("slow"), Reply())

    assert engine.transcribe(audio) == ""
    assert queue, "a timeout was sent again"
