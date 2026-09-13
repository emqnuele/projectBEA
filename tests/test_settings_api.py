"""The settings endpoints the dashboard drives.

`GET /settings` is the whole schema plus the current values; a POST validates
one section, saves, and hot-reloads. Anything that fails validation changes
nothing and says which field was wrong.
"""

import re
from pathlib import Path

import pytest

from src.core.config import MASK, BrainConfig
from src.core.settings_schema import SECTIONS


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from src.core import config as config_module
    from src.web import app as web
    from src.web import deps

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
    previous = deps.brain_instance
    deps.brain_instance = stub
    try:
        yield TestClient(web.app), stub
    finally:
        deps.brain_instance = previous


def test_a_partial_save_keeps_the_rest_of_the_stage_block(client):
    """The dashboard posts the block it is showing, not every key in it.

    `stage` is one field holding eleven settings. Assigning it wholesale, the way
    every other field is assigned, turned "use the 3D body" into "and forget the
    model, the clips and both VTube Studio maps".
    """
    api, stub = client
    stub.config.stage = {**stub.config.stage, "model_path": "data/models/bea.vrm",
                         "vts_expressions": {"angry": "furious.exp3.json"}}

    answer = api.post("/config", json={"config": {"stage": {"avatar_backend": "model"}}})

    assert answer.status_code == 200
    assert stub.config.stage["avatar_backend"] == "model"
    assert stub.config.stage["model_path"] == "data/models/bea.vrm"
    assert stub.config.stage["vts_expressions"] == {"angry": "furious.exp3.json"}
    assert stub.config.stage["lipsync_fps"] == 30


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


# --- the dashboard and the engine must agree ---------------------------------

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "src/web/frontend/src"


def _block(path: Path, pattern: str) -> str:
    found = re.search(pattern, path.read_text(), re.S)
    assert found, f"could not find {pattern} in {path.name}"
    return found.group(1)


def test_every_schema_screen_in_the_dashboard_exists_on_the_engine():
    """A menu entry pointing at a section the engine lacks is a 404 the user sees."""
    wanted = set(re.findall(r"'([a-z_]+)'", _block(
        FRONTEND / "pages/settings/sections.jsx", r"const SCHEMA_DRIVEN = \[(.*?)\]",
    )))
    assert wanted, "no schema-driven sections found in the dashboard"
    assert wanted <= {s.key for s in SECTIONS}


def test_every_screen_in_the_menu_has_something_to_render():
    menu = set(re.findall(r"id: '([a-z_]+)'", _block(
        FRONTEND / "lib/nav.js", r"SETTINGS_SECTIONS = \[(.*?)\];",
    )))
    hand_built = set(re.findall(r"^\s{4}([a-z_]+):", _block(
        FRONTEND / "pages/settings/sections.jsx",
        r"export const SECTIONS = \{(.*?)\.\.\.Object",
    ), re.M))
    # appearance is its own component, wired in the page rather than the registry
    known = {s.key for s in SECTIONS} | hand_built | {"appearance"}
    assert not (menu - known), f"menu entries with nothing behind them: {sorted(menu - known)}"


def test_the_menu_offers_every_platform():
    menu = set(re.findall(r"id: '([a-z_]+)'", _block(
        FRONTEND / "lib/nav.js", r"SETTINGS_SECTIONS = \[(.*?)\];",
    )))
    assert {"discord", "telegram", "twitch"} <= menu


# --- the write path, through the endpoints -----------------------------------


def test_a_class_attribute_cannot_be_written_through_the_config_endpoint(client):
    """The old gate was `hasattr`, which is true for this one.

    Emptying it made `save_to_file` stop stripping anything, so the next save
    wrote every API key into config.json in clear text.
    """
    api, stub = client

    res = api.post("/config", json={"config": {"SECRET_KEYS": []}})

    assert res.status_code == 422
    assert stub.config.SECRET_KEYS == BrainConfig.SECRET_KEYS


def test_a_method_cannot_be_written_through_the_config_endpoint(client):
    api, stub = client

    res = api.post("/config", json={"config": {"public_dict": 1}})

    assert res.status_code == 422
    assert api.get("/config").status_code == 200


def test_a_bad_type_is_refused_with_the_field_named(client):
    api, stub = client

    res = api.post("/config", json={"config": {"obs_port": "banana"}})

    assert res.status_code == 422
    assert "obs_port" in res.json()["detail"]
    assert stub.config.obs_port == 4455


def test_a_refused_config_save_writes_no_file(client, tmp_path):
    api, _ = client

    api.post("/config", json={"config": {"language": "it", "nonsense": 1}})

    assert not (tmp_path / "config.json").exists()


def test_a_refused_config_save_does_not_reload(client):
    api, stub = client

    api.post("/config", json={"config": {"nonsense": 1}})

    assert stub.reloads == 0


def test_an_ordinary_save_still_works(client, tmp_path):
    api, stub = client

    res = api.post("/config", json={"config": {"language": "it"}})

    assert res.status_code == 200
    assert stub.config.language == "it"
    assert stub.reloads == 1
    assert "it" in (tmp_path / "config.json").read_text(encoding="utf-8")


def test_saving_a_full_config_from_get_does_not_fail_on_persona(client):
    api, stub = client

    full = api.get("/config").json()
    full["language"] = "it"

    res = api.post("/config", json={"config": full})

    assert res.status_code == 200
    assert stub.config.language == "it"


# --- secrets go to .env, which is where they survive a restart ---------------


def test_a_key_saved_in_the_dashboard_lands_in_the_env_file(client, tmp_path):
    api, stub = client

    res = api.post("/config", json={"config": {"groq_key": "gsk-typed"}})

    assert res.status_code == 200
    assert res.json()["secrets_written_to_env"] == ["GROQ_API_KEY"]
    assert "GROQ_API_KEY=gsk-typed" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_a_bot_token_saved_in_a_section_lands_in_the_env_file(client, tmp_path):
    api, stub = client

    res = api.post("/settings/discord", json={"token": "bot-token"})

    assert res.status_code == 200
    assert res.json()["secrets_written_to_env"] == ["DISCORD_TOKEN"]
    assert "DISCORD_TOKEN=bot-token" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_a_saved_secret_never_reaches_config_json(client, tmp_path):
    api, _ = client

    api.post("/config", json={"config": {"groq_key": "gsk-typed"}})

    assert "gsk-typed" not in (tmp_path / "config.json").read_text(encoding="utf-8")


def test_saving_an_ordinary_setting_writes_no_env_file(client, tmp_path):
    api, _ = client

    res = api.post("/config", json={"config": {"language": "it"}})

    assert res.json()["secrets_written_to_env"] == []
    assert not (tmp_path / ".env").exists()


def test_a_masked_secret_coming_back_is_dropped(client, tmp_path):
    api, stub = client
    stub.config.skills["discord"]["token"] = "real-token"

    api.post("/config", json={"config": {"skills": {"discord": {"token": MASK}}}})

    assert stub.config.skills["discord"]["token"] == "real-token"
    assert not (tmp_path / ".env").exists()


def test_an_unwritable_env_file_fails_the_whole_save(client, tmp_path, monkeypatch):
    """Nothing half-applied: the config must not move if the secret cannot.

    Otherwise the token is live until the process stops and gone after it —
    which is the bug this endpoint had in the first place.
    """
    api, stub = client

    def refuse(*args, **kwargs):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr("pathlib.Path.write_text", refuse)

    res = api.post("/config", json={"config": {"groq_key": "gsk", "language": "it"}})

    assert res.status_code == 500
    assert stub.config.language == "en"
    assert stub.reloads == 0
