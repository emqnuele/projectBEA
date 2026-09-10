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


# --- how she appears -------------------------------------------------------


def test_apply_answers_leaves_the_stage_alone_when_it_was_not_asked(tmp_path, monkeypatch):
    cfg = apply_answers(config(tmp_path, monkeypatch), base_answers())
    assert cfg.stage["avatar_backend"] == "png"
    assert cfg.stage["caption_backend"] == "obs"


def test_apply_answers_takes_the_two_choices_the_wizard_offers(tmp_path, monkeypatch):
    cfg = apply_answers(config(tmp_path, monkeypatch), base_answers(
        stage={"avatar_backend": "model", "caption_backend": "stage",
               "model_path": "data/models/bea.vrm"}))

    assert cfg.stage["avatar_backend"] == "model"
    assert cfg.stage["caption_backend"] == "stage"
    assert cfg.stage["model_path"] == "data/models/bea.vrm"


def test_the_wizard_never_has_to_ask_about_every_key_in_the_block(tmp_path, monkeypatch):
    """It asks two questions; the rest of the block keeps its defaults."""
    cfg = apply_answers(config(tmp_path, monkeypatch),
                        base_answers(stage={"avatar_backend": "vtube_studio"}))

    assert cfg.stage["avatar_backend"] == "vtube_studio"
    assert cfg.stage["lipsync_fps"] == 30
    assert cfg.stage["vts_mouth_param"] == "MouthOpen"


def ask_stage(monkeypatch, avatar: str, caption: str, connect_obs: bool = True):
    """Runs the wizard's stage question with the answers already decided."""
    from src.setup import wizard

    printed: list = []

    class Recorder:
        def print(self, *args, **kwargs):
            printed.append(" ".join(str(a) for a in args))

        def rule(self, *args, **kwargs):
            pass

    picked = iter([avatar, caption])
    monkeypatch.setattr(wizard, "_choose", lambda *a, **k: next(picked))
    monkeypatch.setattr(wizard.Confirm, "ask", lambda *a, **k: connect_obs)
    monkeypatch.setattr(wizard.Prompt, "ask", lambda *a, **k: "whatever")
    monkeypatch.setattr(wizard.IntPrompt, "ask", lambda *a, **k: 4455)

    answers: dict = {}
    wizard._ask_stage(Recorder(), answers)
    return answers, "\n".join(printed)


def test_the_setup_explains_the_browser_source_even_when_obs_is_also_needed(monkeypatch):
    """Images in OBS with her words in the browser needs both, and used to get one.

    The two questions were an if/elif, so this pairing — the one the wizard
    itself offers by default — never heard about the page it depends on.
    """
    answers, printed = ask_stage(monkeypatch, "png", "stage")

    assert "obs" in answers, "the images still live in an OBS source"
    assert "/stage" in printed, "nothing told her where the caption is drawn"


def test_the_setup_explains_the_browser_source_after_declining_obs(monkeypatch):
    answers, printed = ask_stage(monkeypatch, "model", "obs", connect_obs=False)

    assert "obs" not in answers
    assert "/stage" in printed


def test_the_setup_leaves_obs_out_when_nothing_goes_through_it(monkeypatch):
    answers, printed = ask_stage(monkeypatch, "model", "stage")

    assert "obs" not in answers
    assert "WebSocket Server Settings" not in printed
    assert "/stage" in printed


def test_the_setup_asks_for_a_page_exactly_when_the_engine_needs_one():
    """The wizard's rule and the factories' must not drift apart."""
    from src.modules.avatar.factory import BUILDERS as AVATARS
    from src.modules.avatar.factory import NEEDS_PUBLISHER as AVATAR_NEEDS_PAGE
    from src.modules.caption.factory import BUILDERS as CAPTIONS
    from src.modules.caption.factory import NEEDS_PUBLISHER as CAPTION_NEEDS_PAGE
    from src.setup.wizard import needs_browser_source

    for avatar in AVATARS:
        for caption in CAPTIONS:
            needs_page = avatar in AVATAR_NEEDS_PAGE or caption in CAPTION_NEEDS_PAGE
            assert needs_browser_source(avatar, caption) is needs_page, (avatar, caption)


def test_every_backend_the_wizard_offers_is_one_the_engine_can_build():
    """A wizard that offers a name the factory has never heard of is a dead end."""
    from src.modules.avatar.factory import BUILDERS as AVATARS
    from src.modules.caption.factory import BUILDERS as CAPTIONS
    from src.setup.wizard import AVATARS as OFFERED_AVATARS
    from src.setup.wizard import CAPTIONS as OFFERED_CAPTIONS

    assert {a[0] for a in OFFERED_AVATARS} <= set(AVATARS)
    assert {c[0] for c in OFFERED_CAPTIONS} <= set(CAPTIONS)


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
