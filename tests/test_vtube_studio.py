"""Driving a Live2D model that belongs to the user, over the VTube Studio API.

Nothing here talks to a real VTube Studio: the socket is faked, and what is
checked is the protocol projectBEA speaks and the promises the port makes —
above all that a slow or absent VTube Studio never makes her wait.

Protocol reference: https://github.com/DenchiSoft/VTubeStudio
"""

import asyncio
import json

import pytest

from src.core.config import BrainConfig
from src.modules.avatar.vtube_studio import (
    API_NAME,
    API_VERSION,
    VTubeStudioAvatar,
    VTubeStudioClient,
    VTubeStudioError,
    probe,
)


class FakeSocket:
    """A VTube Studio that answers whatever the test tells it to."""

    def __init__(self, answers=None, authenticated=True, token="tok-123"):
        self.sent = []
        self.closed = False
        self.answers = answers or {}
        self.authenticated = authenticated
        self.token = token

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        request = self.sent[-1]
        kind = request["messageType"]
        if kind in self.answers:
            data = self.answers[kind]
        elif kind == "AuthenticationTokenRequest":
            data = {"authenticationToken": self.token}
        elif kind == "AuthenticationRequest":
            data = {"authenticated": self.authenticated, "reason": "nope"}
        else:
            data = {}
        return json.dumps({"messageType": f"{kind[:-7]}Response", "data": data})

    async def close(self):
        self.closed = True

    def of_type(self, kind):
        return [m for m in self.sent if m["messageType"] == kind]


def client_with(socket, tmp_path, **kwargs) -> VTubeStudioClient:
    client = VTubeStudioClient("127.0.0.1", 8001, tmp_path / "token.json", **kwargs)
    client._socket = socket
    return client


def config(**stage) -> BrainConfig:
    cfg = BrainConfig()
    cfg.stage = {**cfg.stage, "avatar_backend": "vtube_studio", **stage}
    return cfg


# --- the protocol ------------------------------------------------------------


async def test_every_request_carries_the_envelope_the_api_documents(tmp_path):
    socket = FakeSocket()
    await client_with(socket, tmp_path).trigger("hk-1")

    sent = socket.sent[-1]
    assert sent["apiName"] == API_NAME
    assert sent["apiVersion"] == API_VERSION
    assert sent["messageType"] == "HotkeyTriggerRequest"
    assert sent["requestID"]
    assert sent["data"] == {"hotkeyID": "hk-1"}


async def test_the_mouth_is_set_rather_than_added_to(tmp_path):
    """"add" lets other plugins move it too; while she talks the mouth is hers."""
    socket = FakeSocket()
    await client_with(socket, tmp_path).set_parameter("MouthOpen", 0.6667)

    data = socket.sent[-1]["data"]
    assert data["mode"] == "set"
    assert data["faceFound"] is False
    assert data["parameterValues"] == [{"id": "MouthOpen", "value": 0.667}]


async def test_an_api_error_is_raised_and_not_read_as_a_result(tmp_path):
    class Angry(FakeSocket):
        async def recv(self):
            return json.dumps({"messageType": "APIError",
                               "data": {"errorID": 8, "message": "no model loaded"}})

    with pytest.raises(VTubeStudioError, match="no model loaded"):
        await client_with(Angry(), tmp_path).current_model()


# --- being allowed in --------------------------------------------------------


async def test_the_first_connection_asks_to_be_allowed_and_keeps_the_token(tmp_path, monkeypatch):
    socket = FakeSocket()
    client = VTubeStudioClient("127.0.0.1", 8001, tmp_path / "token.json")

    async def fake_connect(url, **kwargs):
        return socket

    monkeypatch.setattr("websockets.connect", fake_connect)
    await client.connect()

    assert socket.of_type("AuthenticationTokenRequest"), "it must ask the user"
    assert json.loads((tmp_path / "token.json").read_text())["token"] == "tok-123"


async def test_a_stored_token_is_reused_instead_of_asking_again(tmp_path, monkeypatch):
    (tmp_path / "token.json").write_text(json.dumps({"token": "already-allowed"}))
    socket = FakeSocket()

    async def fake_connect(url, **kwargs):
        return socket

    monkeypatch.setattr("websockets.connect", fake_connect)
    await VTubeStudioClient("127.0.0.1", 8001, tmp_path / "token.json").connect()

    assert not socket.of_type("AuthenticationTokenRequest")
    assert socket.of_type("AuthenticationRequest")[0]["data"]["authenticationToken"] == "already-allowed"


async def test_a_token_that_no_longer_works_is_thrown_away(tmp_path, monkeypatch):
    """Otherwise she would fail with the same dead token forever."""
    token_file = tmp_path / "token.json"
    token_file.write_text(json.dumps({"token": "revoked"}))

    async def fake_connect(url, **kwargs):
        return FakeSocket(authenticated=False)

    monkeypatch.setattr("websockets.connect", fake_connect)
    with pytest.raises(VTubeStudioError):
        await VTubeStudioClient("127.0.0.1", 8001, token_file).connect()

    assert not token_file.exists()


def test_the_token_is_never_kept_in_the_config(tmp_path):
    """`/config` is unauthenticated, so a credential must not live there."""
    flat = json.dumps(BrainConfig().stage).lower()
    assert "token" not in flat


# --- the port's promises -----------------------------------------------------


def test_nothing_blocks_when_vtube_studio_is_not_there():
    """Every call is synchronous and must return whether or not it is running."""
    avatar = VTubeStudioAvatar(config(vts_expressions={"angry": "angry.exp3.json"}))

    avatar.show("angry", "talking")
    avatar.perform("wave")
    avatar.mouth([0.2, 0.9], 30)
    avatar.close()


async def test_a_mood_becomes_the_expression_file_the_users_model_has(tmp_path):
    avatar = VTubeStudioAvatar(
        config(vts_expressions={"angry": "furious.exp3.json"}), tmp_path / "token.json")

    avatar.show("angry", "talking")
    kind, value = avatar._commands.get_nowait()

    assert (kind, value) == ("expression", "furious.exp3.json")


async def test_a_mood_with_no_expression_mapped_asks_for_none(tmp_path):
    avatar = VTubeStudioAvatar(config(vts_expressions={}), tmp_path / "token.json")
    avatar.show("angry", "idle")
    assert avatar._commands.get_nowait() == ("expression", None)


async def test_a_behaviour_becomes_the_hotkey_id_it_is_mapped_to(tmp_path):
    avatar = VTubeStudioAvatar(config(vts_clips={"wave": "hk-42"}), tmp_path / "token.json")
    avatar.perform("wave")
    assert avatar._commands.get_nowait() == ("hotkey", "hk-42")


async def test_an_unmapped_behaviour_is_passed_through_as_a_hotkey_name(tmp_path):
    """VTube Studio accepts a hotkey's name as well as its id."""
    avatar = VTubeStudioAvatar(config(vts_clips={}), tmp_path / "token.json")
    avatar.perform("Wave hand")
    assert avatar._commands.get_nowait() == ("hotkey", "Wave hand")


async def test_a_backlog_keeps_the_newest_face_not_the_oldest(tmp_path):
    """If she outruns VTube Studio, the face she has now is the right one."""
    avatar = VTubeStudioAvatar(config(), tmp_path / "token.json")
    for i in range(avatar._commands.maxsize + 5):
        avatar._enqueue(("expression", f"e{i}.exp3.json"))

    queued = []
    while not avatar._commands.empty():
        queued.append(avatar._commands.get_nowait()[1])

    assert queued[-1] == f"e{avatar._commands.maxsize + 4}.exp3.json"
    assert len(queued) <= avatar._commands.maxsize


async def test_only_one_expression_is_active_at_a_time(tmp_path):
    """VTS leaves an expression on until told otherwise; they would stack up."""
    socket = FakeSocket()
    client = client_with(socket, tmp_path)
    avatar = VTubeStudioAvatar(config(), tmp_path / "token.json")

    await avatar._apply_expression(client, "a.exp3.json")
    await avatar._apply_expression(client, "b.exp3.json")

    calls = [m["data"] for m in socket.of_type("ExpressionActivationRequest")]
    assert calls[0] == {"expressionFile": "a.exp3.json", "fadeTime": 0.25, "active": True}
    assert calls[1] == {"expressionFile": "a.exp3.json", "fadeTime": 0.25, "active": False}
    assert calls[2] == {"expressionFile": "b.exp3.json", "fadeTime": 0.25, "active": True}


async def test_asking_for_the_same_face_twice_says_nothing_twice(tmp_path):
    socket = FakeSocket()
    client = client_with(socket, tmp_path)
    avatar = VTubeStudioAvatar(config(), tmp_path / "token.json")

    await avatar._apply_expression(client, "a.exp3.json")
    await avatar._apply_expression(client, "a.exp3.json")

    assert len(socket.of_type("ExpressionActivationRequest")) == 1


# --- the mouth ---------------------------------------------------------------


async def test_the_mouth_is_paced_here_because_vtube_studio_has_no_clock(tmp_path):
    """The browser gets the whole envelope; VTS needs one message per frame."""
    socket = FakeSocket()
    avatar = VTubeStudioAvatar(config(), tmp_path / "token.json")
    avatar._connected = client_with(socket, tmp_path)

    await avatar._run_mouth([0.1, 0.5, 0.9], fps=1000)

    values = [m["data"]["parameterValues"][0]["value"]
              for m in socket.of_type("InjectParameterDataRequest")]
    assert values[:3] == [0.1, 0.5, 0.9]
    assert values[-1] == 0.0, "her mouth must close when the line ends"


async def test_an_interrupted_line_closes_her_mouth(tmp_path):
    socket = FakeSocket()
    avatar = VTubeStudioAvatar(config(), tmp_path / "token.json")
    avatar._connected = client_with(socket, tmp_path)

    task = asyncio.get_running_loop().create_task(avatar._run_mouth([0.5] * 100, fps=50))
    await asyncio.sleep(0.03)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    values = [m["data"]["parameterValues"][0]["value"]
              for m in socket.of_type("InjectParameterDataRequest")]
    assert values[-1] == 0.0


async def test_a_mouth_with_nowhere_to_go_is_not_an_error(tmp_path):
    avatar = VTubeStudioAvatar(config(), tmp_path / "token.json")
    await avatar._run_mouth([0.5], fps=1000)


async def test_the_mouth_parameter_is_configurable(tmp_path):
    socket = FakeSocket()
    avatar = VTubeStudioAvatar(config(vts_mouth_param="ParamMouthOpenY"), tmp_path / "token.json")
    avatar._connected = client_with(socket, tmp_path)

    await avatar._run_mouth([0.4], fps=1000)

    assert socket.sent[0]["data"]["parameterValues"][0]["id"] == "ParamMouthOpenY"


# --- what the dashboard asks -------------------------------------------------


async def test_the_dashboard_is_told_what_the_users_model_actually_has(tmp_path, monkeypatch):
    socket = FakeSocket(answers={
        "CurrentModelRequest": {"modelLoaded": True, "modelName": "Hiyori"},
        "ExpressionStateRequest": {"expressions": [
            {"name": "angry", "file": "angry.exp3.json"},
            {"name": "smile", "file": "smile.exp3.json"},
        ]},
        "HotkeysInCurrentModelRequest": {"availableHotkeys": [
            {"hotkeyID": "hk-1", "name": "Wave"},
        ]},
    })

    async def fake_connect(url, **kwargs):
        return socket

    monkeypatch.setattr("websockets.connect", fake_connect)
    found = await probe(config(), tmp_path / "token.json")

    assert found["ok"] and found["model"] == "Hiyori"
    assert found["expressions"] == ["angry.exp3.json", "smile.exp3.json"]
    assert found["hotkeys"] == [{"id": "hk-1", "name": "Wave"}]


async def test_vtube_studio_running_with_no_model_says_exactly_that(tmp_path, monkeypatch):
    socket = FakeSocket(answers={"CurrentModelRequest": {"modelLoaded": False}})

    async def fake_connect(url, **kwargs):
        return socket

    monkeypatch.setattr("websockets.connect", fake_connect)
    found = await probe(config(), tmp_path / "token.json")

    assert found["ok"] and found["model"] is None
    assert "no model is loaded" in found["message"].lower()


async def test_vtube_studio_not_running_is_reported_and_not_raised(tmp_path, monkeypatch):
    async def refuse(url, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("websockets.connect", refuse)
    found = await probe(config(), tmp_path / "token.json")

    assert found["ok"] is False
    assert "refused" in found["message"]
    assert found["expressions"] == [] and found["hotkeys"] == []


# --- the endpoints the dashboard calls ---------------------------------------


@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from src.web import app as web

    class BrainStub:
        def __init__(self):
            self.config = config()

    stub = BrainStub()
    previous = web.brain_instance
    web.brain_instance = stub
    try:
        yield TestClient(web.app), stub
    finally:
        web.brain_instance = previous


def test_the_connection_test_reports_a_failure_instead_of_blowing_up(client, monkeypatch):
    """`detail` is a str: answering None here raised where it should report.

    This is the path that runs when VTube Studio is not open — the single most
    likely thing to happen when somebody first tries the backend.
    """
    async def refuse(url, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("websockets.connect", refuse)
    api, _ = client

    response = api.post("/test/vts")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "refused" in body["message"]
    assert body["detail"] == ""


def test_the_connection_test_counts_what_the_model_offers(client, monkeypatch):
    socket = FakeSocket(answers={
        "CurrentModelRequest": {"modelLoaded": True, "modelName": "Hiyori"},
        "ExpressionStateRequest": {"expressions": [{"name": "a", "file": "a.exp3.json"}]},
        "HotkeysInCurrentModelRequest": {"availableHotkeys": [{"hotkeyID": "h", "name": "Wave"}]},
    })

    async def fake_connect(url, **kwargs):
        return socket

    monkeypatch.setattr("websockets.connect", fake_connect)
    api, _ = client

    body = api.post("/test/vts").json()

    assert body["ok"] is True
    assert body["detail"] == "1 expressions, 1 hotkeys"
