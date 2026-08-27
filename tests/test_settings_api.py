"""The settings endpoints the dashboard drives.

`GET /settings` is the whole schema plus the current values; a POST validates
one section, saves, and hot-reloads. Anything that fails validation changes
nothing and says which field was wrong.
"""

import pytest

from src.core.config import MASK, BrainConfig


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from src.core import config as config_module
    from src.web import app as web

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", "config.json")

    class BrainStub:
        def __init__(self):
            self.config = BrainConfig()
            self.reloads = 0
            self.toggles = []

        def reload_configuration(self):
            self.reloads += 1

        async def set_skill_enabled(self, name, enable):
            self.toggles.append((name, enable))

    stub = BrainStub()
    previous = web.brain_instance
    web.brain_instance = stub
    try:
        yield TestClient(web.app), stub
    finally:
        web.brain_instance = previous


def _section(payload, key):
    return next(s for s in payload["sections"] if s["key"] == key)


# --- reading -----------------------------------------------------------------


def test_the_schema_is_served(client):
    api, _ = client
    body = api.get("/settings").json()
    keys = {s["key"] for s in body["sections"]}
    assert {"telegram", "discord", "twitch", "attention", "models"} <= keys


def test_a_section_carries_its_fields_and_values(client):
    api, _ = client
    telegram = _section(api.get("/settings").json(), "telegram")
    assert {f["key"] for f in telegram["settings"]} >= {"enabled", "token", "owner_id"}
    assert telegram["values"]["enabled"] is False


def test_one_section_can_be_asked_for_on_its_own(client):
    api, _ = client
    body = api.get("/settings/twitch").json()
    assert body["key"] == "twitch"
    assert "channel" in body["values"]


def test_an_unknown_section_is_a_404(client):
    api, _ = client
    assert api.get("/settings/banana").status_code == 404


def test_a_stored_token_never_leaves_the_process(client):
    api, stub = client
    stub.config.skills["telegram"]["token"] = "12345:realtoken"
    body = api.get("/settings").text
    assert "realtoken" not in body
    assert MASK in body


# --- writing -----------------------------------------------------------------


def test_a_setting_is_saved_and_applied(client):
    api, stub = client
    res = api.post("/settings/twitch", json={"channel": "emafaraci"})
    assert res.status_code == 200
    assert stub.config.skills["twitch"]["channel"] == "emafaraci"
    assert stub.reloads == 1


def test_saving_writes_the_config_file(client, tmp_path):
    api, _ = client
    api.post("/settings/twitch", json={"channel": "emafaraci"})
    assert "emafaraci" in (tmp_path / "config.json").read_text()


def test_a_root_block_is_writable_too(client):
    api, stub = client
    api.post("/settings/attention", json={"cooldown_seconds": 45})
    assert stub.config.attention["cooldown_seconds"] == 45


def test_a_bad_value_is_refused_with_the_field_named(client):
    api, stub = client
    res = api.post("/settings/attention", json={"interject_threshold": 9})
    assert res.status_code == 422
    assert "interject_threshold" in res.json()["detail"]
    assert stub.reloads == 0


def test_an_unknown_field_is_refused(client):
    api, _ = client
    assert api.post("/settings/telegram", json={"colour": "blue"}).status_code == 422


def test_an_unknown_section_cannot_be_written(client):
    api, _ = client
    assert api.post("/settings/banana", json={"x": 1}).status_code == 404


def test_a_refused_write_leaves_the_file_alone(client, tmp_path):
    api, _ = client
    api.post("/settings/twitch", json={"channel": "buono"})
    api.post("/settings/twitch", json={"channel": "cattivo", "nope": 1})
    assert "cattivo" not in (tmp_path / "config.json").read_text()


def test_the_response_says_when_a_restart_is_needed(client):
    api, _ = client
    body = api.post("/settings/models", json={"reasoning": "low"}).json()
    assert body["restart_required"] is True


def test_an_ordinary_change_needs_no_restart(client):
    api, _ = client
    body = api.post("/settings/attention", json={"cooldown_seconds": 30}).json()
    assert body["restart_required"] is False


# --- the on/off switch -------------------------------------------------------


def test_turning_a_platform_on_reaches_the_skill_registry(client):
    api, stub = client
    api.post("/settings/telegram", json={"enabled": True})
    assert stub.toggles == [("telegram", True)]


def test_a_setting_that_is_not_the_switch_does_not_toggle_anything(client):
    api, stub = client
    api.post("/settings/telegram", json={"owner_id": "7"})
    assert stub.toggles == []


def test_a_root_section_has_no_switch_to_flip(client):
    api, stub = client
    api.post("/settings/attention", json={"enabled": True})
    assert stub.toggles == []
