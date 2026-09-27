"""OBS is talked to on a thread of its own, so a slow OBS never slows her down.

Two kinds of fake: a client object for the queue's own rules, and a real
obs-websocket v5 server on loopback for what the event loop actually feels
while the real client waits on a slow reply.
"""

import asyncio
import json
import socket
import threading
import time

import pytest

from src.modules.avatar.png import PngAvatar
from src.modules.caption.obs_text import ObsTextCaption
from src.modules.obs.obs_websocket import OBSController


def wait_until(predicate, seconds=3.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


class SlowClient:
    """Answers every request after `delay`, and remembers what it was asked."""

    def __init__(self, delay=0.0, **_):
        self.delay = delay
        self.calls = []
        self.fonts = 0
        self.gate = threading.Event()
        self.gate.set()

    def set_input_settings(self, name, settings, overlay):
        self.gate.wait()
        time.sleep(self.delay)
        self.calls.append((name, dict(settings)))

    def send(self, request, data=None, raw=False):
        self.fonts += 1
        return {"inputSettings": {"font": {"face": "Arial", "size": 75}}}


def controller(client, **kw):
    obs = OBSController("127.0.0.1", 4455, "", "avatar", client_factory=lambda **_: client, **kw)
    obs.connect()
    assert wait_until(lambda: obs.connected)
    return obs


def test_a_request_returns_before_obs_has_answered():
    client = SlowClient(delay=0.2)
    obs = controller(client)
    try:
        started = time.perf_counter()
        obs.set_image("happy.png")
        assert time.perf_counter() - started < 0.01
        assert wait_until(lambda: client.calls == [("avatar", {"file": "happy.png"})])
    finally:
        obs.disconnect()


def test_a_caption_typed_faster_than_obs_answers_only_sends_its_newest_text():
    client = SlowClient()
    client.gate.clear()
    obs = controller(client)
    try:
        obs.set_text("c", "caption")
        # the first one is in flight and held; these pile up behind it
        assert wait_until(lambda: client.fonts == 1)
        for text in ("ci", "cia", "ciao"):
            obs.set_text(text, "caption")
        client.gate.set()
        assert wait_until(lambda: len(client.calls) == 2)
        time.sleep(0.05)
        assert [c[1]["text"] for c in client.calls] == ["c", "ciao"]
    finally:
        obs.disconnect()


def test_two_sources_keep_the_order_they_were_asked_in():
    client = SlowClient()
    client.gate.clear()
    obs = controller(client)
    try:
        obs.set_image("first.png")
        time.sleep(0.05)
        obs.set_text("hello", "caption")
        obs.set_image("second.png")
        client.gate.set()
        assert wait_until(lambda: len(client.calls) == 3)
        assert [c[1].get("file") or c[1].get("text") for c in client.calls] == ["first.png", "hello", "second.png"]
    finally:
        obs.disconnect()


def test_the_text_font_is_read_once_per_source_on_the_worker():
    client = SlowClient()
    obs = controller(client)
    try:
        for text in ("a", "b", "c"):
            obs.set_text(text, "caption", font_size=60)
            assert wait_until(lambda t=text: client.calls and client.calls[-1][1]["text"] == t)
        assert client.fonts == 1
        assert client.calls[-1][1]["font"] == {"face": "Arial", "size": 60}
    finally:
        obs.disconnect()


def test_a_failed_request_drops_the_socket_and_the_next_one_reconnects():
    class Flaky(SlowClient):
        def set_input_settings(self, name, settings, overlay):
            raise TimeoutError("obs went quiet")

    opened = []

    def factory(**_):
        client = Flaky() if not opened else SlowClient()
        opened.append(client)
        return client

    import src.modules.obs.obs_websocket as module
    obs = OBSController("127.0.0.1", 4455, "", "avatar", client_factory=factory)
    previous, module.RETRY_SECONDS = module.RETRY_SECONDS, 0.01
    try:
        obs.connect()
        obs.set_image("lost.png")
        assert wait_until(lambda: len(opened) == 2 and obs.connected)
        obs.set_image("kept.png")
        assert wait_until(lambda: opened[1].calls == [("avatar", {"file": "kept.png"})])
    finally:
        module.RETRY_SECONDS = previous
        obs.disconnect()


def test_nothing_is_sent_after_a_disconnect():
    client = SlowClient()
    client.gate.clear()
    obs = controller(client)
    obs.set_image("in-flight.png")
    obs.set_image("queued.png")
    obs.disconnect()
    client.gate.set()
    time.sleep(0.1)
    assert ("avatar", {"file": "queued.png"}) not in client.calls


# --- the real client against a real slow server ---------------------------------


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def slow_obs():
    """An obs-websocket v5 server that takes `delay` seconds over every request."""
    import websockets.sync.server as wss

    state = {"delay": 0.2, "requests": 0}

    from websockets.exceptions import ConnectionClosed

    def handler(ws):
        try:
            serve(ws)
        except ConnectionClosed:
            # the client gave up on a reply, which is the point of some of these tests
            pass

    def serve(ws):
        ws.send(json.dumps({"op": 0, "d": {"obsWebSocketVersion": "5.0.0", "rpcVersion": 1}}))
        for raw in ws:
            message = json.loads(raw)
            if message["op"] == 1:
                ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
            elif message["op"] == 6:
                time.sleep(state["delay"])
                state["requests"] += 1
                d = message["d"]
                ws.send(json.dumps({"op": 7, "d": {
                    "requestType": d["requestType"], "requestId": d["requestId"],
                    "requestStatus": {"result": True, "code": 100}, "responseData": {}}}))

    port = free_port()
    server = wss.serve(handler, "127.0.0.1", port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield port, state
    finally:
        server.shutdown()


class Config:
    obs_source_type = "image"
    obs_text_source = "AIText"
    text_line_width = 30
    text_lines = 3
    text_font_size = 75
    text_min_font_size = 20
    text_font_step = 2
    typing_delay = 0.0
    text_min_duration = 0.0
    avatar_map = {"neutral": {"idle": "n/idle.png", "talking": "n/talk.png"}}


async def test_the_loop_keeps_turning_while_a_slow_obs_answers(slow_obs):
    """What `line_opened` does before her first sound: clear the caption, show her face."""
    port, state = slow_obs
    obs = OBSController("127.0.0.1", port, "", "avatar")
    obs.connect()
    try:
        assert await asyncio.to_thread(wait_until, lambda: obs.connected)
        avatar, caption = PngAvatar(Config(), obs), ObsTextCaption(Config(), obs)

        stalls = []

        async def ticker():
            while True:
                t = time.perf_counter()
                await asyncio.sleep(0.005)
                stalls.append(time.perf_counter() - t - 0.005)

        tick = asyncio.create_task(ticker())
        await asyncio.sleep(0.05)
        stalls.clear()

        started = time.perf_counter()
        caption.clear()
        avatar.show("neutral", "talking")
        both = time.perf_counter() - started
        await asyncio.sleep(0.5)
        tick.cancel()

        assert both < 0.005, f"the two calls took {both * 1000:.1f} ms on the loop"
        assert max(stalls) < 0.05, f"the loop stalled {max(stalls) * 1000:.1f} ms"
        assert state["requests"] >= 2, "and obs was still told"
    finally:
        obs.disconnect()


def test_an_obs_that_hangs_is_given_up_on_after_the_timeout(slow_obs, caplog):
    port, state = slow_obs
    state["delay"] = 1.0
    obs = OBSController("127.0.0.1", port, "", "avatar", timeout=0.2)
    obs.connect()
    try:
        assert wait_until(lambda: obs.connected)
        first = obs.client
        started = time.monotonic()
        obs.set_image("x.png")
        # a new socket, opened because the old one was given up on
        assert wait_until(lambda: obs.client is not None and obs.client is not first, seconds=1.0)
        assert time.monotonic() - started < 0.6, "the socket was waited on past its timeout"
        assert any("OBS request failed" in r.message for r in caplog.records)
    finally:
        obs.disconnect()


def test_the_dashboard_check_reports_a_closed_obs_without_raising():
    obs = OBSController("127.0.0.1", free_port(), "", "avatar", timeout=0.5)
    assert obs.check() is False
