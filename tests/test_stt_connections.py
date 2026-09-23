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
    real = groq_stt._KeptClient
    monkeypatch.setattr(groq_stt, "_KeptClient",
                        lambda **kwargs: asked.update(kwargs) or real(**kwargs))
    config = BrainConfig()
    config.groq_key = "gsk-test"
    groq_stt.GroqSTT(config)

    assert asked["limits"].keepalive_expiry == groq_stt.KEEPALIVE_SECONDS
    assert groq_stt.KEEPALIVE_SECONDS > 30, "a conversation pauses for longer than that"


def test_groq_closes_the_old_connections_when_the_key_changes(monkeypatch):
    import gc

    from src.modules.STT import groq_stt

    closed = []
    close = groq_stt._KeptClient.close

    def recording(self):
        closed.append(id(self))
        close(self)

    monkeypatch.setattr(groq_stt._KeptClient, "close", recording)
    config = BrainConfig()
    config.groq_key = "gsk-old"
    engine = groq_stt.GroqSTT(config)
    old = id(engine.client._client)

    config.groq_key = "gsk-new"
    engine.reload_config(config)
    assert engine.client.api_key == "gsk-new"
    gc.collect()
    assert old in closed, "the old key's connections were left open"
    assert id(engine.client._client) not in closed


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


def test_openrouter_does_not_knock_twice_on_a_host_that_refuses(monkeypatch, audio):
    from urllib3.exceptions import MaxRetryError, NewConnectionError

    refused = requests.ConnectionError(
        MaxRetryError(None, "/api/v1/audio/transcriptions",
                      NewConnectionError(None, "Connection refused")))
    engine, _, queue = openrouter(monkeypatch, refused, Reply())

    assert engine.transcribe(audio) == ""
    assert queue, "a host that refused was asked again"


def test_openrouter_retry_is_real_against_a_connection_the_server_dropped(audio):
    """The same, over a real socket: the server closes a kept connection without
    answering, and the one resend on a fresh connection is what gets through."""
    import http.server
    import socketserver
    import threading

    from src.modules.STT.openrouter_stt import OpenRouterSTT

    served = {"n": 0}

    class Flaky(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            served["n"] += 1
            if served["n"] == 2:
                # the kept connection, gone: no answer, just the socket closing
                self.close_connection = True
                self.connection.shutdown(2)
                return
            body = b'{"text": "ciao"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Flaky)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        config = BrainConfig()
        config.openrouter_key = "sk-or-test"
        config.language = "it"
        engine = OpenRouterSTT(config)
        engine_url = f"http://127.0.0.1:{server.server_address[1]}"
        post = engine._http.post
        engine._http.post = lambda url, **kw: post(engine_url + "/x", **kw)

        assert engine.transcribe(audio) == "ciao"
        assert engine.transcribe(audio) == "ciao"
        assert served["n"] == 3
    finally:
        server.shutdown()
        server.server_close()

