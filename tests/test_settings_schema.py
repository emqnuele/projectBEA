"""Every knob Bea has, described once, so the dashboard can render it blind.

Before this, a new setting meant editing the config dataclass, the API and the
React page by hand — so most settings never got a UI at all and lived only in
config.json. The schema is the single source: add a `Setting` and it appears,
typed and validated, in the dashboard.
"""

import pytest

from src.core.config import MASK, BrainConfig
from src.core.settings_schema import (
    SECTIONS,
    Setting,
    ValidationError,
    apply_section,
    describe,
    section,
)


def config() -> BrainConfig:
    cfg = BrainConfig()
    cfg.skills = {
        "telegram": {"enabled": False, "owner_id": "", "allowed_chats": []},
        "twitch": {"enabled": False, "channel": "", "nick": ""},
        "discord": {"enabled": False, "api_port": 3030},
    }
    return cfg


# --- the shape of it ---------------------------------------------------------


def test_every_platform_has_a_section():
    keys = {s.key for s in SECTIONS}
    assert {"telegram", "discord", "twitch"} <= keys


def test_the_core_blocks_are_configurable_too():
    keys = {s.key for s in SECTIONS}
    assert {"attention", "rhythm", "models", "consciousness"} <= keys


def test_a_section_knows_where_it_lives():
    assert section("telegram").scope == "skills"
    assert section("attention").scope == "root"


def test_every_setting_declares_a_type_a_label_and_a_default():
    for s in SECTIONS:
        for f in s.settings:
            assert f.label, f"{s.key}.{f.key} has no label"
            assert f.type in {"bool", "int", "float", "string", "secret", "select", "list"}
            assert f.default is not None or f.type in {"string", "secret"}


def test_an_unknown_section_is_not_invented():
    with pytest.raises(KeyError):
        section("banana")


# --- reading -----------------------------------------------------------------


def test_describe_carries_the_current_values():
    cfg = config()
    cfg.skills["twitch"]["channel"] = "emafaraci"
    data = describe(cfg)
    twitch = next(s for s in data["sections"] if s["key"] == "twitch")
    assert twitch["values"]["channel"] == "emafaraci"


def test_a_missing_value_falls_back_to_the_declared_default():
    cfg = config()
    cfg.skills["telegram"].pop("enabled", None)
    data = describe(cfg)
    telegram = next(s for s in data["sections"] if s["key"] == "telegram")
    assert telegram["values"]["enabled"] is False


def test_a_secret_is_never_sent_back():
    cfg = config()
    cfg.skills["telegram"]["token"] = "12345:realtoken"
    data = describe(cfg)
    telegram = next(s for s in data["sections"] if s["key"] == "telegram")
    assert telegram["values"]["token"] == MASK
    assert "realtoken" not in str(data)


def test_an_empty_secret_reads_as_empty_not_as_a_mask():
    data = describe(config())
    telegram = next(s for s in data["sections"] if s["key"] == "telegram")
    assert telegram["values"]["token"] == ""


def test_a_root_block_is_described_too():
    cfg = config()
    cfg.attention["cooldown_seconds"] = 33
    data = describe(cfg)
    attention = next(s for s in data["sections"] if s["key"] == "attention")
    assert attention["values"]["cooldown_seconds"] == 33


# --- writing -----------------------------------------------------------------


def test_a_value_is_stored_where_the_section_says():
    cfg = config()
    apply_section(cfg, "twitch", {"channel": "emafaraci"})
    assert cfg.skills["twitch"]["channel"] == "emafaraci"


def test_a_root_block_is_written_to_the_root():
    cfg = config()
    apply_section(cfg, "attention", {"cooldown_seconds": 45})
    assert cfg.attention["cooldown_seconds"] == 45


def test_a_number_arriving_as_text_is_coerced():
    cfg = config()
    apply_section(cfg, "discord", {"api_port": "4040"})
    assert cfg.skills["discord"]["api_port"] == 4040


def test_a_checkbox_arriving_as_text_is_coerced():
    cfg = config()
    apply_section(cfg, "telegram", {"enabled": "true"})
    assert cfg.skills["telegram"]["enabled"] is True


def test_a_comma_separated_list_becomes_a_list():
    cfg = config()
    apply_section(cfg, "attention", {"trigger_words": "bea, beatrice ,  bee"})
    assert cfg.attention["trigger_words"] == ["bea", "beatrice", "bee"]


def test_a_list_that_is_already_a_list_survives():
    cfg = config()
    apply_section(cfg, "attention", {"hot_names": ["ema", "marco"]})
    assert cfg.attention["hot_names"] == ["ema", "marco"]


def test_omitted_settings_are_left_alone():
    cfg = config()
    cfg.skills["twitch"]["nick"] = "beabot"
    apply_section(cfg, "twitch", {"channel": "ema"})
    assert cfg.skills["twitch"]["nick"] == "beabot"


# --- refusing bad input ------------------------------------------------------


def test_a_value_out_of_range_is_refused():
    with pytest.raises(ValidationError) as e:
        apply_section(config(), "attention", {"interject_threshold": 4.0})
    assert "interject_threshold" in str(e.value)


def test_a_choice_that_is_not_on_the_list_is_refused():
    with pytest.raises(ValidationError):
        apply_section(config(), "models", {"reasoning": "very-hard"})


def test_a_number_that_is_not_a_number_is_refused():
    with pytest.raises(ValidationError):
        apply_section(config(), "discord", {"api_port": "abc"})


def test_an_unknown_key_is_refused_rather_than_ignored():
    with pytest.raises(ValidationError) as e:
        apply_section(config(), "telegram", {"colour": "blue"})
    assert "colour" in str(e.value)


def test_a_refused_payload_changes_nothing():
    cfg = config()
    apply_section(cfg, "twitch", {"channel": "ema"})
    with pytest.raises(ValidationError):
        apply_section(cfg, "twitch", {"channel": "altro", "nope": 1})
    assert cfg.skills["twitch"]["channel"] == "ema"


# --- secrets -----------------------------------------------------------------


def test_writing_the_mask_back_keeps_the_stored_secret():
    cfg = config()
    cfg.skills["telegram"]["token"] = "12345:realtoken"
    apply_section(cfg, "telegram", {"token": MASK, "owner_id": "7"})
    assert cfg.skills["telegram"]["token"] == "12345:realtoken"
    assert cfg.skills["telegram"]["owner_id"] == "7"


def test_a_new_secret_replaces_the_old_one():
    cfg = config()
    cfg.skills["telegram"]["token"] = "old"
    apply_section(cfg, "telegram", {"token": "new"})
    assert cfg.skills["telegram"]["token"] == "new"


def test_an_emptied_secret_is_cleared():
    cfg = config()
    cfg.skills["telegram"]["token"] = "old"
    apply_section(cfg, "telegram", {"token": ""})
    assert cfg.skills["telegram"]["token"] == ""


# --- the knobs the platforms actually gained ---------------------------------


def _keys(name: str) -> set:
    return {f.key for f in section(name).settings}


def test_telegram_can_be_told_what_to_read_and_how_to_answer():
    assert {"enabled", "token", "owner_id", "allowed_chats", "read_media",
            "reactions", "followup_enabled", "followup_max_turns"} <= _keys("telegram")


def test_discord_exposes_its_safety_valves():
    assert {"invite_max_age_seconds", "invite_max_uses", "access_mode",
            "interrupt_threshold_ms"} <= _keys("discord")


def test_twitch_exposes_the_events_it_can_now_see():
    assert {"channel", "oauth_token", "announce_raids", "announce_subs",
            "say_rate_limit"} <= _keys("twitch")


def test_the_reasoning_level_is_a_setting():
    reasoning = next(f for f in section("models").settings if f.key == "reasoning")
    assert reasoning.type == "select"
    assert "off" in reasoning.options


def test_a_setting_can_describe_itself_to_a_human():
    for s in SECTIONS:
        for f in s.settings:
            assert isinstance(f, Setting)
            assert f.help, f"{s.key}.{f.key} has no help text"


def test_the_follow_up_gate_is_tunable_from_the_dashboard():
    assert {"followup_enabled", "followup_window_seconds", "followup_max_turns"} <= _keys("attention")
