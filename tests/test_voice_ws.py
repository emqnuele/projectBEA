"""The seam between the two processes: the socket her voice goes down.

Everything else about the push channel is unit-tested against a fake socket.
This is the one test that runs the real endpoint, because the failures that
matter here are wiring failures — a token nobody checks, or a disconnect that
leaves the brain believing it can still be heard.
"""

import json
import time
from functools import partial

import pytest
from starlette.websockets import WebSocketDisconnect

from src.core.skills.voice.channel import VoiceChannel, unframe

TOKEN = "test-token-not-a-real-one"


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from src.web import app as web
    from src.web import deps

    class Transport:
        api_token = TOKEN

    class Surface:
        def __init__(self):
            self.channel = VoiceChannel()
            self.transport = Transport()

    class Registry:
        def __init__(self, surface):
            self._surface = surface

        def get(self, name):
            return self._surface if name == "voice:discord" else None

    surface = Surface()

    class BrainStub:
        surface_registry = Registry(surface)

    previous = deps.brain_instance
    deps.brain_instance = BrainStub()
    try:
        # as a context manager the client owns a portal, which is how a test
        # thread reaches into the app's event loop to make her speak
        with TestClient(web.app) as api:
            yield api, surface
    finally:
        deps.brain_instance = previous


def connect(api):
    return api.websocket_connect("/voice/ws", headers={"Authorization": f"Bearer {TOKEN}"})


def settled(predicate, tries: int = 300) -> None:
    """The endpoint runs on its own thread; give it a moment to catch up."""
    for _ in range(tries):
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("the channel never reached the expected state")


def test_the_channel_refuses_a_caller_without_the_token(client):
    api, surface = client
    with pytest.raises(WebSocketDisconnect):
        with api.websocket_connect("/voice/ws") as ws:
            ws.receive_text()
    assert not surface.channel.connected


def test_the_channel_refuses_the_wrong_token(client):
    api, surface = client
    with pytest.raises(WebSocketDisconnect):
        with api.websocket_connect("/voice/ws", headers={"Authorization": "Bearer nope"}) as ws:
            ws.receive_text()
    assert not surface.channel.connected


def test_the_bot_is_the_authority_on_which_call_she_is_in(client):
    api, surface = client
    with connect(api) as ws:
        ws.send_text(json.dumps({"type": "joined", "channel_id": "c1", "listeners": 3}))
        settled(lambda: surface.channel.live)
        assert surface.channel.channel_id == "c1"

        ws.send_text(json.dumps({"type": "members", "listeners": 4}))
        settled(lambda: surface.channel.listeners == 4)

        ws.send_text(json.dumps({"type": "left"}))
        settled(lambda: not surface.channel.live)


def test_her_voice_goes_down_the_socket_as_one_frame(client):
    api, surface = client
    pcm = b"\x00\x01" * 2000
    with connect(api) as ws:
        ws.send_text(json.dumps({"type": "joined", "channel_id": "c1", "listeners": 1}))
        settled(lambda: surface.channel.live)

        api.portal.call(partial(surface.channel.play, pcm, utterance_id="u1"))

        header, payload = unframe(ws.receive_bytes())
        assert header["type"] == "play" and header["utterance_id"] == "u1"
        assert payload == pcm


def test_a_bot_that_walks_away_leaves_her_unable_to_be_heard(client):
    api, surface = client
    with connect(api) as ws:
        ws.send_text(json.dumps({"type": "joined", "channel_id": "c1", "listeners": 1}))
        settled(lambda: surface.channel.live)

    settled(lambda: not surface.channel.connected)
    assert not surface.channel.live


def test_a_malformed_frame_does_not_take_the_socket_down(client):
    api, surface = client
    with connect(api) as ws:
        ws.send_text("{ this is not json")
        ws.send_text(json.dumps({"type": "joined", "channel_id": "c1", "listeners": 2}))
        settled(lambda: surface.channel.live)
