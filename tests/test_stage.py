"""The channel the browser source listens on.

Deliberately not the dashboard's event stream: OBS reloads a browser source
whenever you toggle it, and a backlog replay would have her act out the last
minute of the stream again.
"""

import asyncio
import json

import pytest

from src.core.config import BrainConfig
from src.core.stage import QUEUE_LIMIT, StageChannel
from src.modules.caption.factory import build_caption
from src.modules.caption.obs_text import ObsTextCaption
from src.modules.caption.stage import StageCaption
from src.modules.obs.obs_websocket import OBSController


class Obs:
    def set_image(self, *a, **k):
        pass

    def set_media(self, *a, **k):
        pass

    def set_text(self, *a, **k):
        pass

    async def type_text(self, **kwargs):
        return 0


# --- the channel -------------------------------------------------------------


def test_a_page_that_connects_is_told_how_she_looks_now():
    channel = StageChannel()
    channel.publish({"mood": "angry", "state": "talking"})

    assert channel.snapshot()["mood"] == "angry"
    assert channel.snapshot()["state"] == "talking"


def test_a_reconnecting_page_gets_no_backlog_to_act_out():
    """The whole reason this is not EventManager."""
    channel = StageChannel()
    for mood in ("happy", "sad", "angry"):
        channel.publish({"mood": mood})

    queue = channel.subscribe()

    assert queue.empty(), "a fresh subscriber must start from the snapshot, not a log"
    assert channel.snapshot()["mood"] == "angry"


def test_a_moment_is_not_remembered_as_a_state():
    """An envelope kept in the snapshot would mouth a sentence long finished."""
    channel = StageChannel()
    channel.publish({"mood": "happy", "envelope": [0.1, 0.2], "perform": "wave"})

    snapshot = channel.snapshot()
    assert snapshot["mood"] == "happy"
    assert "envelope" not in snapshot
    assert "perform" not in snapshot


def test_subscribers_are_handed_the_patch_and_not_the_whole_state():
    channel = StageChannel()
    queue = channel.subscribe()

    channel.publish({"mood": "surprised"})

    assert queue.get_nowait() == {"mood": "surprised"}


def test_a_page_that_stopped_reading_is_dropped_not_waited_for():
    """The engine must never block on a browser source that walked away."""
    channel = StageChannel()
    channel.subscribe()

    for i in range(QUEUE_LIMIT + 5):
        channel.publish({"mood": f"m{i}"})

    assert channel.subscriber_count == 0


def test_closing_the_channel_lets_go_of_every_page():
    channel = StageChannel()
    channel.subscribe()
    channel.close()
    assert channel.subscriber_count == 0


# --- the caption backends compared ------------------------------------------


async def test_a_caption_crosses_the_wire_once_instead_of_once_per_character():
    """The measurement that justified the whole browser source.

    `OBSController.type_text` calls `set_input_settings` for every character of
    every page, re-sending the font block each time.
    """
    line = ("Ok allora sentite questa, perche' e' veramente assurda: "
            "ieri sera uno in chat mi ha detto che non sono una vera vtuber "
            "solo perche' non ho un corpo. Ridicolo.")

    class CountingClient:
        def __init__(self):
            self.calls = 0

        def set_input_settings(self, name, settings, overlay):
            self.calls += 1

        def send(self, *a, **k):
            return {"inputSettings": {"font": {"face": "Arial", "size": 75}}}

    class Config:
        obs_text_source = "AIText"
        text_line_width = 40
        text_lines = 4
        text_font_size = 75
        text_min_font_size = 55
        text_font_step = 2
        typing_delay = 0.0
        text_min_duration = 0.0

    obs = OBSController("localhost", 4455, "", "BeaPNG")
    obs.client = CountingClient()
    await ObsTextCaption(Config(), obs).say(line)

    channel = StageChannel()
    queue = channel.subscribe()
    await StageCaption(Config(), channel).say(line)

    assert obs.client.calls > len(line), "the OBS path is one request per character"
    assert queue.qsize() == 1, "the stage path is one message per line"


async def test_each_line_carries_an_id_so_a_reload_does_not_retype_it():
    channel = StageChannel()
    caption = StageCaption(BrainConfig(), channel)

    await caption.say("prima")
    first = channel.snapshot()["caption_id"]
    await caption.say("seconda")

    assert first and channel.snapshot()["caption_id"] != first


async def test_clearing_leaves_nothing_for_a_reconnecting_page_to_show():
    channel = StageChannel()
    caption = StageCaption(BrainConfig(), channel)

    await caption.say("qualcosa")
    caption.clear()

    assert channel.snapshot()["caption"] == ""


def test_the_stage_caption_refuses_to_be_built_without_somewhere_to_publish():
    """Better the OBS bubble than a caption that silently goes nowhere."""
    config = BrainConfig()
    config.stage = {**config.stage, "caption_backend": "stage"}

    caption = build_caption(config, Obs(), publisher=None)

    assert isinstance(caption, ObsTextCaption)


# --- the endpoint ------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from src.web import app as web
    from src.web import deps

    class BrainStub:
        def __init__(self):
            self.config = BrainConfig()
            self.stage = StageChannel()

    stub = BrainStub()
    previous = deps.brain_instance
    deps.brain_instance = stub
    try:
        yield TestClient(web.app), stub
    finally:
        deps.brain_instance = previous


async def test_the_stream_opens_with_a_snapshot_before_any_patch(client):
    """Driven directly: an SSE endpoint never ends, so a client would hang."""
    from src.web.routers import stage

    _api, stub = client
    stub.stage.publish({"mood": "sad", "state": "talking"})

    class Disconnected:
        async def is_disconnected(self):
            return True

    response = await stage.stage_stream(Disconnected(), brain=stub)
    first = await response.body_iterator.__anext__()

    payload = json.loads(first[len("data: "):])
    assert payload["type"] == "snapshot"
    assert payload["mood"] == "sad"
    assert payload["state"] == "talking"


async def test_the_stream_lets_go_of_the_queue_when_the_page_leaves(client):
    from src.web.routers import stage

    _api, stub = client

    class Disconnected:
        async def is_disconnected(self):
            return True

    response = await stage.stage_stream(Disconnected(), brain=stub)
    async for _chunk in response.body_iterator:
        pass

    assert stub.stage.subscriber_count == 0


def test_the_stage_config_never_carries_a_secret(client):
    api, _ = client
    payload = api.get("/stage/config").json()

    flat = json.dumps(payload).lower()
    for word in ("key", "token", "password", "secret"):
        assert word not in flat, f"the browser source must not be told the {word}"


def test_the_preview_only_serves_images_the_avatar_map_names(client, tmp_path):
    """A preview that served any path in the query string would read any file."""
    api, stub = client
    secret = tmp_path / "id_rsa"
    secret.write_text("not an avatar")
    stub.config.avatar_map = {"neutral": {"idle": "", "talking": ""}}

    assert api.get("/stage/preview", params={"mood": "neutral"}).status_code == 404
    assert api.get("/stage/preview", params={"mood": str(secret)}).status_code == 404


async def test_the_engine_is_never_slowed_down_by_a_page(monkeypatch):
    """Publishing is synchronous and must stay non-blocking under any reader."""
    channel = StageChannel()
    channel.subscribe()

    async def publish_many():
        for i in range(50):
            channel.publish({"mood": f"m{i}"})

    await asyncio.wait_for(publish_many(), timeout=1.0)


# --- the model and the behaviours it plays ----------------------------------


def test_a_behaviour_name_cannot_walk_out_of_the_clips_folder(client, tmp_path):
    """The name comes from a page, so it is untrusted input.

    Driven through the route function rather than through the test client:
    httpx normalises `..` out of a URL before it is ever sent, so going through
    a client would test httpx and not the guard that has to hold when something
    less polite asks.
    """
    from fastapi import HTTPException

    from src.web.routers import stage

    _api, stub = client
    (tmp_path / "clips").mkdir()
    (tmp_path / "secret.vrma").write_text("not a clip")
    stub.config.stage = {**stub.config.stage, "clips_dir": str(tmp_path / "clips")}

    for name in ("../secret", "../../etc/passwd", "/etc/passwd"):
        with pytest.raises(HTTPException) as raised:
            stage.stage_clip(name, brain=stub)
        assert raised.value.status_code == 404


def test_the_clip_list_is_empty_rather_than_broken_without_a_folder(client):
    api, stub = client
    stub.config.stage = {**stub.config.stage, "clips_dir": "no/such/folder"}
    assert api.get("/stage/clips").json() == []


def test_asking_for_a_model_that_is_not_configured_says_so(client):
    api, stub = client
    stub.config.stage = {**stub.config.stage, "model_path": ""}
    response = api.get("/stage/model")
    assert response.status_code == 404
    assert "configured" in response.json()["detail"].lower()


def test_a_configured_model_that_is_not_on_disk_names_the_path(client, tmp_path):
    api, stub = client
    missing = tmp_path / "bea.vrm"
    stub.config.stage = {**stub.config.stage, "model_path": str(missing)}
    response = api.get("/stage/model")
    assert response.status_code == 404
    assert str(missing) in response.json()["detail"]


# --- settings reaching a running page ----------------------------------------


def test_the_public_config_is_the_same_whether_read_or_pushed(client):
    """The endpoint and the live patch must not describe her differently."""
    from src.core.stage import public_config

    api, stub = client
    assert api.get("/stage/config").json() == public_config(stub.config)


def test_the_page_is_told_when_the_model_changes(tmp_path):
    """A different file under the same path still has to reach the renderer."""
    from src.core.config import BrainConfig
    from src.core.stage import public_config

    model = tmp_path / "bea.vrm"
    model.write_bytes(b"glTF-ish")
    config = BrainConfig()
    config.stage = {**config.stage, "model_path": str(model)}

    before = public_config(config)["model_id"]
    import os
    os.utime(model, (0, 0))
    after = public_config(config)["model_id"]

    assert before and after and before != after


def test_a_model_that_is_not_there_still_has_an_id(tmp_path):
    from src.core.config import BrainConfig
    from src.core.stage import public_config

    config = BrainConfig()
    config.stage = {**config.stage, "model_path": str(tmp_path / "gone.vrm")}
    assert public_config(config)["model_id"] == "gone.vrm"


def test_no_model_configured_means_no_id():
    from src.core.config import BrainConfig
    from src.core.stage import public_config

    assert public_config(BrainConfig())["model_id"] == ""


def test_the_transparent_background_is_the_default():
    """OBS composites the page, so anything painted is on the stream."""
    from src.core.config import BrainConfig
    from src.core.stage import public_config

    assert public_config(BrainConfig())["background"] == ""
