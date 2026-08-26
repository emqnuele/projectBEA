"""The wizard writes the two files everything else depends on: it may not
clobber a hand-edited `.env`, and it may not leave a skill armed that the user
did not ask for."""

from src.core.config import BrainConfig
from src.setup.config_plan import apply_answers, env_updates
from src.setup.env_file import merge_env, parse_env


def config(tmp_path, monkeypatch) -> BrainConfig:
    monkeypatch.chdir(tmp_path)
    return BrainConfig()


def base_answers(**overrides) -> dict:
    answers = {
        "llm_provider": "openrouter",
        "llm_key": "sk-or-live",
        "llm_model": "deepseek/deepseek-v4-flash",
        "skills": {},
    }
    answers.update(overrides)
    return answers


# --- .env ------------------------------------------------------------------


def test_parse_env_strips_quotes_and_ignores_comments():
    parsed = parse_env('# a note\nA="one"\nB=two\n\nexport C=\'three\'\n')
    assert parsed == {"A": "one", "B": "two", "C": "three"}


def test_merge_env_rewrites_a_key_where_it_already_sits():
    original = "# providers\nOPENROUTER_API_KEY=old\nOBS_PORT=4455\n"
    merged = merge_env(original, {"OPENROUTER_API_KEY": "new"})
    assert merged.splitlines() == ["# providers", "OPENROUTER_API_KEY=new", "OBS_PORT=4455"]


def test_merge_env_appends_keys_that_were_not_there():
    merged = merge_env("A=1\n", {"B": "2"})
    assert parse_env(merged) == {"A": "1", "B": "2"}


def test_merge_env_leaves_untouched_keys_alone():
    original = "DISCORD_TOKEN=hand-written\n"
    assert parse_env(merge_env(original, {"GROQ_API_KEY": "gsk"}))["DISCORD_TOKEN"] == "hand-written"


def test_merge_env_drops_empty_values_rather_than_blanking_a_key():
    merged = merge_env("GROQ_API_KEY=gsk-real\n", {"GROQ_API_KEY": ""})
    assert parse_env(merged)["GROQ_API_KEY"] == "gsk-real"


def test_merge_env_quotes_a_value_with_spaces():
    merged = merge_env("", {"OBS_PASSWORD": "two words"})
    assert parse_env(merged)["OBS_PASSWORD"] == "two words"


def test_merge_env_survives_a_round_trip_through_an_empty_file():
    merged = merge_env("", {"A": "1", "B": "2"})
    assert parse_env(merged) == {"A": "1", "B": "2"}


# --- config.json -----------------------------------------------------------


def test_apply_answers_sets_the_provider_and_its_own_model_field(tmp_path, monkeypatch):
    cfg = apply_answers(config(tmp_path, monkeypatch),
                        base_answers(llm_provider="groq", llm_model="openai/gpt-oss-120b"))
    assert cfg.llm_provider == "groq"
    assert cfg.groq_model == "openai/gpt-oss-120b"


def test_apply_answers_falls_back_to_a_known_model_when_none_is_given(tmp_path, monkeypatch):
    answers = base_answers()
    answers["llm_model"] = ""
    cfg = apply_answers(config(tmp_path, monkeypatch), answers)
    assert cfg.openrouter_model == "deepseek/deepseek-v4-flash"


def test_apply_answers_arms_only_the_chosen_skills(tmp_path, monkeypatch):
    cfg = config(tmp_path, monkeypatch)
    cfg.skills["minecraft"]["enabled"] = True  # left on by an earlier run
    cfg = apply_answers(cfg, base_answers(skills={"twitch": {"channel": "bea", "nick": "bea"}}))

    assert cfg.skills["twitch"]["enabled"] is True
    assert cfg.skills["twitch"]["channel"] == "bea"
    assert cfg.skills["minecraft"]["enabled"] is False
    assert cfg.skills["discord"]["enabled"] is False


def test_apply_answers_never_writes_a_skill_token_into_the_config(tmp_path, monkeypatch):
    cfg = apply_answers(config(tmp_path, monkeypatch),
                        base_answers(skills={"discord": {"token": "bot-token", "admin_id": "7"}}))
    assert "token" not in cfg.skills["discord"]
    assert cfg.skills["discord"]["admin_id"] == "7"


def test_apply_answers_leaves_obs_defaults_when_obs_was_declined(tmp_path, monkeypatch):
    cfg = apply_answers(config(tmp_path, monkeypatch), base_answers())
    assert cfg.obs_avatar_source == "BeaPNG"


def test_apply_answers_applies_obs_when_it_was_accepted(tmp_path, monkeypatch):
    cfg = apply_answers(config(tmp_path, monkeypatch),
                        base_answers(obs={"host": "10.0.0.2", "port": 4466,
                                          "avatar_source": "Avatar"}))
    assert (cfg.obs_host, cfg.obs_port, cfg.obs_avatar_source) == ("10.0.0.2", 4466, "Avatar")


def test_saved_config_carries_no_secret(tmp_path, monkeypatch):
    cfg = apply_answers(config(tmp_path, monkeypatch), base_answers())
    cfg.save_to_file()
    assert "sk-or-live" not in (tmp_path / "config.json").read_text(encoding="utf-8")


# --- the split between the two files ---------------------------------------


def test_env_updates_carries_the_llm_key_under_the_var_the_engine_reads():
    assert env_updates(base_answers())["OPENROUTER_API_KEY"] == "sk-or-live"


def test_env_updates_does_not_re_ask_for_a_key_the_mind_already_uses():
    updates = env_updates(base_answers(stt_provider="openrouter"))
    assert list(updates) == ["OPENROUTER_API_KEY"]


def test_env_updates_carries_a_separate_stt_key_when_the_provider_differs():
    updates = env_updates(base_answers(stt_provider="groq", stt_key="gsk-live"))
    assert updates["GROQ_API_KEY"] == "gsk-live"
    assert updates["OPENROUTER_API_KEY"] == "sk-or-live"


def test_env_updates_carries_every_skill_token():
    updates = env_updates(base_answers(skills={
        "discord": {"token": "discord-token"},
        "telegram": {"token": "telegram-token"},
        "twitch": {"channel": "bea"},
    }))
    assert updates["DISCORD_TOKEN"] == "discord-token"
    assert updates["TELEGRAM_TOKEN"] == "telegram-token"
    assert "TWITCH_OAUTH_TOKEN" not in updates
