"""`GET /config` is unauthenticated: it must never carry a usable secret."""

import json

from src.core.config import MASK, SECRET_SKILL_FIELDS, BrainConfig


def config(tmp_path, monkeypatch) -> BrainConfig:
    monkeypatch.chdir(tmp_path)
    cfg = BrainConfig()
    cfg.openrouter_key = "sk-or-secret"
    cfg.openai_key = "sk-openai-secret"
    cfg.groq_key = "gsk-secret"
    cfg.orpheus_key = "orpheus-secret"
    cfg.orpheus_endpoint = "https://private.endpoint"
    return cfg


def test_public_dict_drops_every_top_level_secret(tmp_path, monkeypatch):
    cfg = config(tmp_path, monkeypatch)
    public = cfg.public_dict()
    for key in BrainConfig.SECRET_KEYS:
        assert key not in public
    assert "secret" not in json.dumps(public)


def test_public_dict_masks_a_set_skill_token(tmp_path, monkeypatch):
    cfg = config(tmp_path, monkeypatch)
    cfg.skills.setdefault("discord", {})["token"] = "real-bot-token"
    assert cfg.public_dict()["skills"]["discord"]["token"] == MASK


def test_public_dict_leaves_an_unset_token_empty(tmp_path, monkeypatch):
    cfg = config(tmp_path, monkeypatch)
    cfg.skills.setdefault("discord", {})["token"] = ""
    assert cfg.public_dict()["skills"]["discord"]["token"] == ""


def test_public_dict_does_not_mutate_the_live_config(tmp_path, monkeypatch):
    cfg = config(tmp_path, monkeypatch)
    cfg.skills.setdefault("discord", {})["token"] = "real-bot-token"
    cfg.public_dict()
    assert cfg.skills["discord"]["token"] == "real-bot-token"
    assert cfg.openrouter_key == "sk-or-secret"


def test_saving_never_writes_a_secret_to_disk(tmp_path, monkeypatch):
    cfg = config(tmp_path, monkeypatch)
    cfg.skills.setdefault("discord", {})["token"] = "real-bot-token"
    cfg.save_to_file()

    written = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    for key in BrainConfig.SECRET_KEYS:
        assert key not in written
    for skill_key, field in SECRET_SKILL_FIELDS:
        assert field not in written.get("skills", {}).get(skill_key, {})


def test_the_default_config_ships_no_discord_token(tmp_path, monkeypatch):
    cfg = config(tmp_path, monkeypatch)
    assert "token" not in cfg.skills["discord"]


def test_env_secrets_win_over_config_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"openrouter_key": "from-file"}), encoding="utf-8"
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    assert BrainConfig().openrouter_key == "from-env"


def test_config_json_fills_a_secret_the_env_does_not_set(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"openrouter_key": "from-file"}), encoding="utf-8"
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert BrainConfig().openrouter_key == "from-file"
