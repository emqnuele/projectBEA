"""A secret typed into the dashboard has to outlive the process.

`save_to_file` strips every secret on the way to config.json, by design. The
dashboard handed them to it anyway: the field said saved, the engine used the
value until it was stopped, and the next start came up without it. The only
trace was a warning in a log nobody reads, so the bug looked like "the Discord
bot randomly stops working".

They go to `.env` instead — the file the engine already reads them back from.
"""

import os

import pytest

from src.core import secrets as secret_store
from src.core.config import SECRET_ENV_VARS, SECRET_SKILL_FIELDS, BrainConfig
from src.setup.env_file import parse_env


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    monkeypatch.setattr(secret_store, "ENV_FILE", str(path))
    return path


def written(path) -> dict:
    return parse_env(path.read_text(encoding="utf-8"))


# --- the map itself ---------------------------------------------------------


def test_every_secret_the_config_knows_has_somewhere_to_go():
    """The drift guard: a new secret must not silently have no home."""
    expected = set(BrainConfig.SECRET_KEYS)
    expected |= {f"{skill}.{field}" for skill, field in SECRET_SKILL_FIELDS}

    assert set(SECRET_ENV_VARS) == expected


def test_the_variables_are_the_ones_the_engine_reads():
    # these names are read by os.getenv at the point of use, so a typo here is
    # a token that is written down and never found again
    assert SECRET_ENV_VARS["discord.token"] == "DISCORD_TOKEN"
    assert SECRET_ENV_VARS["telegram.token"] == "TELEGRAM_TOKEN"
    assert SECRET_ENV_VARS["twitch.oauth_token"] == "TWITCH_OAUTH_TOKEN"
    assert SECRET_ENV_VARS["openrouter_key"] == "OPENROUTER_API_KEY"


# --- writing ----------------------------------------------------------------


def test_a_token_reaches_the_file(env_file):
    secret_store.persist({"discord.token": "bot-token"})

    assert written(env_file)["DISCORD_TOKEN"] == "bot-token"


def test_a_top_level_key_reaches_the_file(env_file):
    secret_store.persist({"openrouter_key": "sk-or-abc"})

    assert written(env_file)["OPENROUTER_API_KEY"] == "sk-or-abc"


def test_the_running_process_moves_with_the_file(env_file):
    # the discord transport reads os.getenv("DISCORD_TOKEN") at launch, so the
    # bot has to work now and not only after a restart
    secret_store.persist({"discord.token": "bot-token"})

    assert os.environ["DISCORD_TOKEN"] == "bot-token"


def test_the_file_is_created_when_there_is_none(env_file):
    assert not env_file.exists()

    secret_store.persist({"groq_key": "gsk-1"})

    assert env_file.exists()


def test_what_was_already_there_survives(env_file):
    env_file.write_text(
        "# my own notes\nLOG_LEVEL=DEBUG\nOPENROUTER_API_KEY=old\n", encoding="utf-8"
    )

    secret_store.persist({"openrouter_key": "new"})

    text = env_file.read_text(encoding="utf-8")
    assert "# my own notes" in text
    assert parse_env(text)["LOG_LEVEL"] == "DEBUG"
    assert parse_env(text)["OPENROUTER_API_KEY"] == "new"


def test_a_key_is_rewritten_where_it_sits(env_file):
    env_file.write_text("A=1\nGROQ_API_KEY=old\nB=2\n", encoding="utf-8")

    secret_store.persist({"groq_key": "new"})

    lines = env_file.read_text(encoding="utf-8").strip().splitlines()
    assert lines == ["A=1", "GROQ_API_KEY=new", "B=2"]


def test_several_secrets_go_in_one_write(env_file):
    stored = secret_store.persist(
        {"discord.token": "d", "telegram.token": "t", "groq_key": "g"}
    )

    assert stored == ["DISCORD_TOKEN", "GROQ_API_KEY", "TELEGRAM_TOKEN"]
    assert set(written(env_file)) == {"DISCORD_TOKEN", "TELEGRAM_TOKEN", "GROQ_API_KEY"}


def test_it_says_which_variables_it_wrote(env_file):
    assert secret_store.persist({"groq_key": "g"}) == ["GROQ_API_KEY"]


def test_something_that_is_not_a_secret_is_ignored(env_file):
    assert secret_store.persist({"language": "it"}) == []
    assert not env_file.exists()


def test_nothing_to_write_touches_no_file(env_file):
    assert secret_store.persist({}) == []
    assert not env_file.exists()


# --- clearing ---------------------------------------------------------------


def test_an_emptied_field_clears_the_variable(env_file):
    env_file.write_text("GROQ_API_KEY=old\n", encoding="utf-8")
    os.environ["GROQ_API_KEY"] = "old"

    secret_store.persist({"groq_key": ""})

    assert written(env_file)["GROQ_API_KEY"] == ""
    assert "GROQ_API_KEY" not in os.environ


def test_clearing_a_key_that_was_never_there_adds_nothing(env_file):
    env_file.write_text("A=1\n", encoding="utf-8")

    secret_store.persist({"groq_key": ""})

    assert env_file.read_text(encoding="utf-8").strip() == "A=1"


# --- the restart the bug was about ------------------------------------------


def test_a_token_saved_in_the_dashboard_survives_a_restart(env_file, tmp_path, monkeypatch):
    """The whole point, end to end.

    Saving used to leave the token in memory only: `save_to_file` dropped it,
    and the next `BrainConfig()` came up without it.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    live = BrainConfig()
    live.openrouter_key = "sk-or-typed-into-the-dashboard"
    secret_store.persist({"openrouter_key": live.openrouter_key})
    live.save_to_file()

    # the restart: a brand new config, reading only what is on disk
    os.environ.pop("OPENROUTER_API_KEY", None)
    from dotenv import load_dotenv
    load_dotenv(env_file, override=True)

    assert BrainConfig().openrouter_key == "sk-or-typed-into-the-dashboard"


def test_config_json_still_never_carries_the_secret(env_file, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    live = BrainConfig()
    live.openrouter_key = "sk-or-secret"
    live.skills.setdefault("discord", {})["token"] = "bot-secret"
    secret_store.persist({"openrouter_key": "sk-or-secret", "discord.token": "bot-secret"})
    live.save_to_file()

    written_config = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert "sk-or-secret" not in written_config
    assert "bot-secret" not in written_config


# --- failure ----------------------------------------------------------------


def test_an_unwritable_env_file_is_raised_and_not_swallowed(env_file, monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr("pathlib.Path.write_text", refuse)

    with pytest.raises(OSError):
        secret_store.persist({"groq_key": "g"})


def test_a_failed_write_leaves_the_environment_alone(env_file, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    def refuse(*args, **kwargs):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr("pathlib.Path.write_text", refuse)

    with pytest.raises(OSError):
        secret_store.persist({"groq_key": "g"})

    assert "GROQ_API_KEY" not in os.environ
