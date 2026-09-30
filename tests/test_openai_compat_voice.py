"""Voice in and out through any server speaking OpenAI's audio api.

Run against a real http server on localhost rather than a mocked session: the
things that break here are the wire format, the streamed wav header and the
kept connection, and a mock would agree with whatever the code assumed.
"""

import asyncio
import io
import json
import struct
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest

from src.core.config import BrainConfig
from src.core.expression.prosody import Prosody
from src.modules.STT.openai_compat_stt import OpenAICompatSTT
from src.modules.tts import providers
from src.modules.tts.openai_compat_tts import (
    OpenAICompatTTSWrapper,
    decode_samples,
    parse_wav_header,
)
from src.setup.config_plan import env_updates

RATE = 22050


def wav_bytes(samples: np.ndarray, rate: int = RATE, channels: int = 1,
              streamed: bool = False) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((samples * 32767).astype("<i2").tobytes())
    data = bytearray(buffer.getvalue())
    if streamed:
        # what a server writes before it knows how long the audio will be
        data[4:8] = struct.pack("<I", 0xFFFFFFFF)
        data[40:44] = struct.pack("<I", 0xFFFFFFFF)
    return bytes(data)


class Server:
    """A tiny openai-compatible audio server, recording what it was sent."""

    def __init__(self, tts_body: bytes = b"", refuse_verbose: bool = False):
        self.requests: list = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _reply(self, status: int, body: bytes, kind: str = "application/json"):
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_HEAD(self):
                outer.requests.append(("HEAD", self.path, dict(self.headers), b""))
                self.send_response(405)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                outer.requests.append(("POST", self.path, dict(self.headers), body))
                if self.path == "/v1/audio/speech":
                    # sent in small pieces, the way a streaming server does
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/wav")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    for i in range(0, len(outer.tts_body), 1000):
                        piece = outer.tts_body[i:i + 1000]
                        self.wfile.write(f"{len(piece):x}\r\n".encode() + piece + b"\r\n")
                    self.wfile.write(b"0\r\n\r\n")
                elif self.path == "/v1/audio/transcriptions":
                    if outer.refuse_verbose and b"verbose_json" in body:
                        self._reply(400, b'{"error": "unsupported response_format"}')
                    elif b"verbose_json" in body:
                        self._reply(200, json.dumps({"text": "ciao", "language": "italian"}).encode())
                    else:
                        self._reply(200, b'{"text": "ciao"}')
                else:
                    self._reply(404, b"{}")

        self.tts_body = tts_body
        self.refuse_verbose = refuse_verbose
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def tone():
    return (0.5 * np.sin(np.linspace(0, 400, RATE))).astype(np.float32)


# --- the wav header ----------------------------------------------------------


def test_a_header_is_not_answered_until_it_has_all_arrived(tone):
    data = wav_bytes(tone)
    assert parse_wav_header(data[:20]) is None
    assert parse_wav_header(data) == (1, 1, RATE, 16, 44)


def test_a_streamed_wav_with_no_length_is_still_read(tone):
    assert parse_wav_header(wav_bytes(tone, streamed=True)) == (1, 1, RATE, 16, 44)


def test_something_that_is_not_a_wav_is_refused():
    with pytest.raises(ValueError):
        parse_wav_header(b"ID3\x04" + b"\x00" * 40)


def test_stereo_is_folded_to_mono():
    frames = np.array([[0.5, -0.5], [0.25, 0.25]], dtype=np.float32)
    raw = (frames * 32768).astype("<i2").tobytes()
    assert np.allclose(decode_samples(raw, 1, 2, 16), [0.0, 0.25], atol=1e-4)


# --- speaking -----------------------------------------------------------------


def test_the_stream_is_the_whole_answer_in_order(tone):
    server = Server(tts_body=wav_bytes(tone, streamed=True))
    try:
        tts = OpenAICompatTTSWrapper(server.url, "", "tts-1", "alloy")

        async def gather():
            return [part async for part in tts.generate_stream("hello")]

        parts = asyncio.run(gather())
        assert len(parts) > 1, "a stream that arrives in one piece started no sooner"
        assert {rate for _, rate in parts} == {RATE}
        heard = np.concatenate([samples for samples, _ in parts])
        assert np.allclose(heard, tone, atol=1e-4)
    finally:
        server.close()


def test_the_whole_answer_decodes_the_same(tone):
    server = Server(tts_body=wav_bytes(tone))
    try:
        tts = OpenAICompatTTSWrapper(server.url, "", "tts-1", "alloy")
        samples, rate = asyncio.run(tts.generate_audio("hello"))
        assert rate == RATE
        assert np.allclose(samples, tone, atol=1e-4)
    finally:
        server.close()


def test_the_request_says_what_was_configured_and_the_mood_moves_the_speed(tone):
    server = Server(tts_body=wav_bytes(tone))
    try:
        tts = OpenAICompatTTSWrapper(server.url, "sk-test", "kokoro", "af_bella", speed=1.2)
        asyncio.run(tts.generate_audio("hello", Prosody(rate=1.1)))
        _, path, headers, body = server.requests[-1]
        sent = json.loads(body)
        assert path == "/v1/audio/speech"
        assert headers["Authorization"] == "Bearer sk-test"
        assert sent["model"] == "kokoro" and sent["voice"] == "af_bella"
        assert sent["response_format"] == "wav"
        assert sent["speed"] == pytest.approx(1.32)
    finally:
        server.close()


def test_a_neutral_voice_sends_no_speed_and_no_key(tone):
    server = Server(tts_body=wav_bytes(tone))
    try:
        tts = OpenAICompatTTSWrapper(server.url + "/", "", "tts-1", "alloy")
        asyncio.run(tts.generate_audio("hello"))
        _, path, headers, body = server.requests[-1]
        assert path == "/v1/audio/speech"
        assert "speed" not in json.loads(body)
        assert "Authorization" not in headers
    finally:
        server.close()


def test_the_mood_volume_is_applied_to_the_samples(tone):
    server = Server(tts_body=wav_bytes(tone))
    try:
        tts = OpenAICompatTTSWrapper(server.url, "", "tts-1", "alloy")
        samples, _ = asyncio.run(tts.generate_audio("hello", Prosody(volume=0.5)))
        assert np.allclose(samples, tone * 0.5, atol=1e-4)
    finally:
        server.close()


def test_warming_opens_the_connection_the_line_then_reuses(tone):
    server = Server(tts_body=wav_bytes(tone))
    try:
        tts = OpenAICompatTTSWrapper(server.url, "", "tts-1", "alloy")
        tts.warm()
        # a second turn a moment later finds the socket already open
        tts.warm()
        asyncio.run(tts.generate_audio("hello"))
        assert [r[0] for r in server.requests] == ["HEAD", "POST"]
        pool = next(iter(tts.client.adapters["http://"].poolmanager.pools._container.values()))
        assert pool.num_connections == 1
    finally:
        server.close()


def test_an_unreachable_server_is_silence_not_a_crash():
    tts = OpenAICompatTTSWrapper("http://127.0.0.1:9/v1", "", "tts-1", "alloy")
    samples, _ = asyncio.run(tts.generate_audio("hello"))
    assert len(samples) == 0


# --- hearing ------------------------------------------------------------------


def stt_config(url: str, **overrides) -> BrainConfig:
    settings = BrainConfig()
    settings.stt_provider = "openai_compat"
    settings.stt_compat_base_url = url
    settings.stt_compat_key = ""
    settings.stt_model = "whisper-1"
    settings.stt_language = "auto"
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def test_a_transcription_is_sent_as_multipart_and_read_back(tmp_path, tone):
    clip = tmp_path / "turn.wav"
    clip.write_bytes(wav_bytes(tone))
    server = Server()
    try:
        stt = OpenAICompatSTT(stt_config(server.url))
        assert stt.transcribe(str(clip)) == "ciao"
        _, path, headers, body = server.requests[-1]
        assert path == "/v1/audio/transcriptions"
        assert headers["Content-Type"].startswith("multipart/form-data")
        assert b"whisper-1" in body and b"verbose_json" in body
        assert "Authorization" not in headers
        assert stt.status()["degraded"] is False
    finally:
        server.close()


def test_a_server_without_verbose_json_is_asked_for_json_from_then_on(tmp_path, tone):
    clip = tmp_path / "turn.wav"
    clip.write_bytes(wav_bytes(tone))
    server = Server(refuse_verbose=True)
    try:
        stt = OpenAICompatSTT(stt_config(server.url))
        assert stt.transcribe(str(clip)) == "ciao"
        assert stt.transcribe(str(clip)) == "ciao"
        formats = [b"verbose_json" in r[3] for r in server.requests]
        assert formats == [True, False, False]
    finally:
        server.close()


def test_a_pinned_language_is_sent(tmp_path, tone):
    clip = tmp_path / "turn.wav"
    clip.write_bytes(wav_bytes(tone))
    server = Server()
    try:
        stt = OpenAICompatSTT(stt_config(server.url, stt_language="it"))
        stt.transcribe(str(clip))
        assert b'name="language"\r\n\r\nit' in server.requests[-1][3]
    finally:
        server.close()


def test_the_transcriber_warms_the_connection_its_turn_then_uses(tmp_path, tone):
    clip = tmp_path / "turn.wav"
    clip.write_bytes(wav_bytes(tone))
    server = Server()
    try:
        stt = OpenAICompatSTT(stt_config(server.url))
        stt.warm()
        stt.transcribe(str(clip))
        assert [r[0] for r in server.requests] == ["HEAD", "POST"]
        pool = next(iter(stt._http.adapters["http://"].poolmanager.pools._container.values()))
        assert pool.num_connections == 1
    finally:
        server.close()


def test_warming_an_unreachable_server_never_raises():
    OpenAICompatSTT(stt_config("http://127.0.0.1:9/v1")).warm()
    OpenAICompatTTSWrapper("http://127.0.0.1:9/v1", "", "tts-1", "alloy").warm()


def test_a_failure_is_reported_in_status(tmp_path, tone):
    clip = tmp_path / "turn.wav"
    clip.write_bytes(wav_bytes(tone))
    stt = OpenAICompatSTT(stt_config("http://127.0.0.1:9/v1"))
    assert stt.transcribe(str(clip)) == ""
    assert stt.status()["degraded"] is True


# --- the setup ----------------------------------------------------------------


def test_the_custom_voice_speaks_any_language_and_keeps_its_voice():
    settings = BrainConfig()
    settings.tts_provider = "openai_compat"
    settings.tts_compat_base_url = "http://localhost:8880/v1"
    settings.tts_compat_voice = "if_sara"
    settings.language = "ja"
    assert providers.speaks(providers.for_config(settings), "ja")
    assert providers.voice_for(settings).id == "if_sara"
    assert providers.plan_for_language(settings, "ja") == {}
    assert providers.warnings(settings) == ()


def test_the_custom_voice_without_a_url_is_warned_about():
    settings = BrainConfig()
    settings.tts_provider = "openai_compat"
    settings.tts_compat_base_url = ""
    assert any("tts_compat_base_url" in w for w in providers.warnings(settings))


def test_the_transcriber_key_never_lands_on_the_minds_custom_key():
    updates = env_updates({"llm_provider": "openrouter", "stt_provider": "openai_compat",
                           "stt_key": "sk-ears", "tts_compat_key": "sk-voice"})
    assert updates["STT_COMPAT_API_KEY"] == "sk-ears"
    assert updates["TTS_COMPAT_API_KEY"] == "sk-voice"
    assert "OPENAI_COMPAT_API_KEY" not in updates


def test_a_warm_socket_is_not_warmed_again_until_it_could_have_gone():
    from src.utils.warm import Warmer

    opened = []
    warm = Warmer(lambda: opened.append(1), every_s=60)
    warm()
    warm()
    assert opened == [1]
    Warmer(lambda: 1 / 0)()  # a failure is the request's to find, not the warmer's
