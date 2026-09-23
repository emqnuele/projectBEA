"""Orpheus streams a sentence off an HTTP response on a worker thread.

What matters is what happens when nobody wants the rest: a barge-in cancels the
synthesis, and it used to wait for the whole response to download first — the
interruption itself stalled behind audio nobody was ever going to hear.
"""

import asyncio
import threading
import time

import numpy as np

from src.modules.tts.orpheus_tts_wrapper import OrpheusTTSWrapper

CHUNKS = 60
CHUNK_SECONDS = 0.02


class Response:
    """A streamed body that arrives a chunk at a time, like the real endpoint."""

    def __init__(self):
        self.read = 0
        self.closed = threading.Event()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.closed.set()

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=4096):
        for _ in range(CHUNKS):
            if self.closed.is_set():
                raise ConnectionError("the response was closed")
            time.sleep(CHUNK_SECONDS)
            self.read += 1
            yield b"\x00\x10" * 4000


class Session:
    def __init__(self):
        self.responses = []

    def post(self, *a, **k):
        self.responses.append(Response())
        return self.responses[-1]


def orpheus():
    tts = OrpheusTTSWrapper(api_key="k", endpoint_url="https://orpheus.invalid")
    tts.client = Session()
    return tts


def test_the_wait_before_a_response_is_bounded():
    """A barge-in cannot cancel a worker thread stuck inside `requests`, so the
    wait before the response headers have to end on their own. Without a
    timeout the thread and its socket outlive the sentence that was dropped."""
    from src.modules.tts import orpheus_tts_wrapper

    seen = {}

    class NeverAnswers:
        def post(self, *a, **k):
            seen.update(k)
            raise TimeoutError("no response")

    tts = OrpheusTTSWrapper(api_key="k", endpoint_url="https://orpheus.invalid")
    tts.client = NeverAnswers()

    blocks = [audio for audio, _ in _collect(tts)]

    assert blocks == []
    assert seen["timeout"] == (orpheus_tts_wrapper.CONNECT_TIMEOUT_S,
                               orpheus_tts_wrapper.READ_TIMEOUT_S)


def _collect(tts):
    """Blocks from a stream, synchronously, for the tests that need none."""
    import asyncio

    async def run():
        return [audio async for audio, _ in tts.generate_stream("ciao")]

    return asyncio.run(run())


async def test_the_whole_sentence_still_arrives_when_it_is_all_wanted():
    tts = orpheus()
    blocks = [audio async for audio, rate in tts.generate_stream("ciao")]
    total = sum(len(b) for b in blocks)
    assert total == CHUNKS * 4000
    assert all(isinstance(b, np.ndarray) for b in blocks)


async def test_walking_away_from_a_sentence_stops_downloading_it():
    tts = orpheus()
    stream = tts.generate_stream("ciao")
    await stream.__anext__()

    started = time.perf_counter()
    await stream.aclose()
    waited = time.perf_counter() - started

    response = tts.client.responses[0]
    assert waited < 0.2, f"closing waited {waited:.2f}s for the rest of the download"
    assert response.closed.wait(1), "the response was left open"
    time.sleep(3 * CHUNK_SECONDS)
    assert response.read < CHUNKS / 2, f"{response.read}/{CHUNKS} chunks read after it was dropped"


async def test_a_barge_in_does_not_wait_for_audio_nobody_will_hear():
    tts = orpheus()

    async def consume():
        async for _ in tts.generate_stream("ciao"):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(5 * CHUNK_SECONDS)
    started = time.perf_counter()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    waited = time.perf_counter() - started

    assert waited < 0.2, f"the cancel waited {waited:.2f}s for the rest of the download"
    assert tts.client.responses[0].closed.wait(1)


async def test_a_real_connection_is_hung_up_when_the_sentence_is_dropped():
    """The same, over a real socket through `requests`: the endpoint stops being
    read from, rather than streaming the rest of the sentence into nothing."""
    import http.server
    import socketserver

    served = {"chunks": 0, "hung_up": threading.Event()}

    class Slow(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            try:
                for _ in range(CHUNKS):
                    self.wfile.write(b"\x00\x10" * 4000)
                    self.wfile.flush()
                    served["chunks"] += 1
                    time.sleep(CHUNK_SECONDS)
            except OSError:
                served["hung_up"].set()

        def log_message(self, *a):
            pass

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Slow)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        tts = OrpheusTTSWrapper(api_key="k", endpoint_url=f"http://127.0.0.1:{port}/")
        stream = tts.generate_stream("ciao")
        await stream.__anext__()
        started = time.perf_counter()
        await stream.aclose()
        assert time.perf_counter() - started < 0.2

        assert served["hung_up"].wait(2), "the endpoint went on sending the whole sentence"
        assert served["chunks"] < CHUNKS
    finally:
        server.shutdown()
        server.server_close()
