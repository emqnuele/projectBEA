"""What the dashboard is allowed to write, and what it is not.

The save used to gate on `hasattr`, which answers for methods and class
attributes as readily as for settings. Emptying `SECRET_KEYS` through it made
`save_to_file` stop stripping anything, so the very next save wrote every API
key into config.json in clear text; replacing `public_dict` with an integer
made `GET /config` fail until the engine was restarted. Nothing checked types
either, so a port could be stored as the word "banana".

Every case below is one of those, or one of the behaviours that had to survive
being fixed.
"""

import json

import pytest

from src.core.config import MASK, BrainConfig
from src.core.config_write import WriteRejected, apply_config, plan_config


@pytest.fixture
def config(tmp_path, monkeypatch) -> BrainConfig:
    monkeypatch.chdir(tmp_path)
    return BrainConfig()


def rejected(config, payload) -> str:
    with pytest.raises(WriteRejected) as caught:
        plan_config(config, payload)
    return str(caught.value)


# --- the hole ---------------------------------------------------------------


def test_a_class_attribute_is_not_a_setting(config):
    assert "SECRET_KEYS" in rejected(config, {"SECRET_KEYS": []})
    assert config.SECRET_KEYS == BrainConfig.SECRET_KEYS


def test_emptying_the_secret_list_cannot_leak_the_keys_to_disk(config, tmp_path):
    """The exploit end to end: the payload is refused, so the save still strips."""
    config.openrouter_key = "sk-or-please-do-not-write-me-down"

    rejected(config, {"SECRET_KEYS": [], "language": "it"})
    config.save_to_file()

    written = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert "sk-or-please-do-not-write-me-down" not in written
    assert "openrouter_key" not in json.loads(written)


def test_a_method_cannot_be_replaced(config):
    assert "save_to_file" in rejected(config, {"save_to_file": 1})
    assert callable(config.save_to_file)


def test_the_reader_the_dashboard_needs_cannot_be_broken(config):
    assert "public_dict" in rejected(config, {"public_dict": 1})
    assert isinstance(config.public_dict(), dict)


def test_a_dunder_is_not_a_setting(config):
    assert "__class__" in rejected(config, {"__class__": "nonsense"})


def test_a_key_nobody_declared_is_refused(config):
    assert "unknown setting" in rejected(config, {"not_a_setting": 1})


def test_the_persona_keeps_its_own_door(config):
    # `PUT /persona` refuses a blank name and a soul the size of a novel
    before = dict(config.persona)

    assert "not writable here" in rejected(config, {"persona": {"name": ""}})
    assert config.persona == before


# --- types ------------------------------------------------------------------


def test_a_port_is_a_number(config):
    assert "obs_port" in rejected(config, {"obs_port": "banana"})


def test_a_number_written_as_text_is_still_a_number(config):
    apply_config(config, {"obs_port": "4460"})
    assert config.obs_port == 4460


def test_a_boolean_is_not_a_port(config):
    assert "obs_port" in rejected(config, {"obs_port": True})


def test_an_object_is_not_a_name(config):
    # str({"a": 1}) is a perfectly good string, which is the trap
    assert "language" in rejected(config, {"language": {"a": 1}})
    assert config.language == "en"


def test_a_block_has_to_be_an_object(config):
    assert "stage" in rejected(config, {"stage": "png"})


def test_a_skill_block_has_to_be_an_object(config):
    assert "skills.discord" in rejected(config, {"skills": {"discord": "on"}})


def test_a_float_setting_takes_a_float(config):
    apply_config(config, {"typing_delay": "0.5"})
    assert config.typing_delay == 0.5


def test_zero_is_a_value(config):
    config.audio_device_id = 7
    apply_config(config, {"audio_device_id": 0})
    assert config.audio_device_id == 0


def test_an_optional_field_still_takes_none(config):
    apply_config(config, {"obs_text_source": None})
    assert config.obs_text_source is None


# --- all or nothing ---------------------------------------------------------


def test_one_bad_key_changes_nothing(config):
    before = (config.language, config.obs_port)

    rejected(config, {"language": "it", "obs_port": "banana"})

    assert (config.language, config.obs_port) == before


def test_every_offending_key_is_named(config):
    detail = rejected(config, {"obs_port": "banana", "nonsense": 1})

    assert "obs_port" in detail
    assert "nonsense" in detail


def test_planning_writes_nothing_on_its_own(config):
    plan = plan_config(config, {"language": "it"})

    assert config.language == "en"
    plan.apply(config)
    assert config.language == "it"


# --- what a partial save must not destroy -----------------------------------


def test_a_block_is_merged_and_not_replaced(config):
    config.stage = {**config.stage, "model_path": "data/models/bea.vrm"}

    apply_config(config, {"stage": {"avatar_backend": "model"}})

    assert config.stage["avatar_backend"] == "model"
    assert config.stage["model_path"] == "data/models/bea.vrm"


def test_a_skill_block_is_merged_and_not_replaced(config):
    config.skills["discord"]["admin_id"] = "1234"

    apply_config(config, {"skills": {"discord": {"api_port": 3040}}})

    assert config.skills["discord"]["api_port"] == 3040
    assert config.skills["discord"]["admin_id"] == "1234"


def test_a_skill_the_payload_never_mentions_survives(config):
    config.skills["telegram"]["owner_id"] = "999"

    apply_config(config, {"skills": {"discord": {"api_port": 3040}}})

    assert config.skills["telegram"]["owner_id"] == "999"


def test_a_map_keyed_by_mood_is_merged_one_mood_at_a_time(config):
    config.avatar_map = {"happy": {"idle": "a.png"}, "angry": {"idle": "b.png"}}

    apply_config(config, {"avatar_map": {"happy": {"talking": "c.png"}}})

    assert config.avatar_map["happy"] == {"idle": "a.png", "talking": "c.png"}
    assert config.avatar_map["angry"] == {"idle": "b.png"}


# --- the schema still has the last word where it declared something ---------


def test_a_declared_bound_is_enforced_through_the_whole_config_save(config):
    detail = rejected(config, {"skills": {"discord": {"silence_seconds": 900}}})

    assert "skills.discord.silence_seconds" in detail


def test_a_declared_choice_is_enforced(config):
    assert "models.reasoning" in rejected(config, {"models": {"reasoning": "very-hard"}})


def test_a_declared_setting_is_coerced(config):
    apply_config(config, {"skills": {"discord": {"api_port": "4040"}}})
    assert config.skills["discord"]["api_port"] == 4040


def test_a_knob_the_schema_never_declared_still_goes_through(config):
    # the minecraft screen has three of these; refusing them would break it
    apply_config(config, {"skills": {"minecraft": {"auto_chat_thoughts": True}}})
    assert config.skills["minecraft"]["auto_chat_thoughts"] is True


# --- secrets ----------------------------------------------------------------


def test_a_masked_secret_never_overwrites_the_real_one(config):
    config.openrouter_key = "sk-or-real"

    plan = plan_config(config, {"openrouter_key": MASK})
    plan.apply(config)

    assert config.openrouter_key == "sk-or-real"
    assert plan.secrets == {}


def test_a_masked_skill_token_never_overwrites_the_real_one(config):
    config.skills["discord"]["token"] = "real-token"

    plan = plan_config(config, {"skills": {"discord": {"token": MASK}}})
    plan.apply(config)

    assert config.skills["discord"]["token"] == "real-token"
    assert plan.secrets == {}


def test_a_new_secret_is_handed_back_for_the_env_file(config):
    plan = plan_config(config, {"groq_key": "gsk-new"})
    assert plan.secrets == {"groq_key": "gsk-new"}


def test_a_new_skill_token_is_handed_back_for_the_env_file(config):
    plan = plan_config(config, {"skills": {"telegram": {"token": "123:abc"}}})
    assert plan.secrets == {"telegram.token": "123:abc"}


def test_an_emptied_secret_is_a_deliberate_clearing(config):
    config.groq_key = "gsk-old"

    plan = plan_config(config, {"groq_key": ""})

    assert plan.secrets == {"groq_key": ""}


def test_an_ordinary_setting_is_not_mistaken_for_a_secret(config):
    plan = plan_config(config, {"skills": {"discord": {"admin_id": "1234"}}})
    assert plan.secrets == {}


# --- the one thing that needs a restart -------------------------------------


def test_changing_the_voice_provider_asks_for_a_restart(config):
    assert plan_config(config, {"tts_provider": "kokoro"}).restart_required


def test_saving_the_same_provider_does_not(config):
    assert not plan_config(config, {"tts_provider": config.tts_provider}).restart_required


def test_an_ordinary_setting_does_not(config):
    assert not plan_config(config, {"language": "it"}).restart_required
