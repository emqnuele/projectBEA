"""Who she is called, everywhere at once.

Her name used to be the string "Bea" hardcoded in eight places, and her trigger
words were a separate list nobody kept in sync. Rename her in soul.md and she
stopped answering to her own name — the gate was still listening for "bea".

The test that matters here is the last one: rename her, then check that no path
still knows the old name.
"""

import pytest

from src.core.persona import DEFAULT_NAME, DEFAULT_PRONOUNS, Persona, persona_of

# --- reading it off the config ----------------------------------------------


class Config:
    def __init__(self, persona=None, attention=None):
        self.persona = persona if persona is not None else {}
        self.attention = attention if attention is not None else {}
        self.skills = {}


def test_an_unconfigured_persona_is_the_one_we_ship():
    p = persona_of(Config())
    assert p.name == DEFAULT_NAME
    assert p.pronouns == DEFAULT_PRONOUNS


def test_a_configured_name_wins():
    assert persona_of(Config({"name": "Luna"})).name == "Luna"


def test_a_blank_name_falls_back_rather_than_leaving_her_nameless():
    assert persona_of(Config({"name": "   "})).name == DEFAULT_NAME


def test_a_config_without_a_persona_block_at_all_still_works():
    class Bare:
        attention = {}

    assert persona_of(Bare()).name == DEFAULT_NAME


# --- pronouns ----------------------------------------------------------------


def test_a_two_part_pronoun_is_understood():
    p = Persona(name="Luna", pronouns="she/her")
    assert (p.subject, p.object, p.possessive) == ("she", "her", "her")


def test_a_three_part_pronoun_keeps_the_possessive_apart():
    p = Persona(name="Luna", pronouns="they/them/their")
    assert (p.subject, p.object, p.possessive) == ("they", "them", "their")


def test_pronouns_in_another_language_are_not_mangled():
    p = Persona(name="Bea", pronouns="lei/lei")
    assert p.subject == "lei"


def test_a_single_word_is_used_for_everything():
    p = Persona(name="Kai", pronouns="they")
    assert (p.subject, p.object, p.possessive) == ("they", "they", "they")


def test_nonsense_pronouns_fall_back_instead_of_crashing():
    assert Persona(name="Kai", pronouns="").subject == "she"


# --- what she is called, for the gate ---------------------------------------


def test_the_trigger_words_come_from_her_name():
    assert persona_of(Config({"name": "Luna"})).trigger_words == ["luna"]


def test_a_two_word_name_also_answers_to_the_first_part():
    """You call someone by their first name, not their full name."""
    assert persona_of(Config({"name": "Luna Rossi"})).trigger_words == ["luna rossi", "luna"]


def test_words_you_set_yourself_are_kept():
    config = Config({"name": "Luna"}, {"trigger_words": ["lu", "lulu"]})
    assert set(persona_of(config).trigger_words) >= {"lu", "lulu"}


def test_her_own_name_always_reaches_her_anyway():
    """Someone renaming her from the dashboard has an old trigger list in their
    config. Without this she would not answer to the name they just gave her."""
    config = Config({"name": "Luna"}, {"trigger_words": ["bea", "beatrice"]})
    assert "luna" in persona_of(config).trigger_words
    assert "bea" in persona_of(config).trigger_words


def test_the_aliases_come_first_because_they_were_chosen():
    config = Config({"name": "Luna"}, {"trigger_words": ["lu"]})
    assert persona_of(config).trigger_words[0] == "lu"


def test_nothing_is_listed_twice():
    config = Config({"name": "Luna"}, {"trigger_words": ["luna", "lu"]})
    words = persona_of(config).trigger_words
    assert len(words) == len(set(words))


def test_an_empty_list_means_derive_it_again():
    config = Config({"name": "Luna"}, {"trigger_words": []})
    assert persona_of(config).trigger_words == ["luna"]


def test_trigger_words_are_lowercase_so_the_matcher_can_use_them():
    assert persona_of(Config({"name": "LUNA"})).trigger_words == ["luna"]


# --- filling a prompt --------------------------------------------------------


def test_the_name_is_substituted():
    p = Persona(name="Luna", pronouns="she/her")
    assert p.fill("You are {name}.") == "You are Luna."


def test_the_pronouns_are_substituted():
    p = Persona(name="Luna", pronouns="they/them/their")
    assert p.fill("{subject} said it was {possessive} idea") == "they said it was their idea"
    assert p.fill("pronouns: {pronouns}") == "pronouns: they/them/their"


def test_a_prompt_with_no_placeholders_is_untouched():
    text = "You are Bea's body. She gave you a goal."
    assert Persona(name="Luna", pronouns="she/her").fill(text) == text


def test_a_placeholder_we_do_not_know_is_left_alone():
    """Prompt files are hand-edited; a typo must not eat the line."""
    p = Persona(name="Luna", pronouns="she/her")
    assert p.fill("hello {nmae} and {date}") == "hello {nmae} and {date}"


def test_filling_nothing_returns_nothing():
    assert Persona(name="Luna", pronouns="she/her").fill("") == ""


# --- the whole rename, path by path -----------------------------------------


@pytest.fixture
def renamed(tmp_path, monkeypatch):
    """A brain that was told she is called Luna, with the real prompt files."""
    import shutil
    from pathlib import Path

    from src.core import config as config_module
    from src.core.brain import AIVtuberBrain
    from src.core.config import BrainConfig
    from src.core.memory import embedder as embedder_module
    from tests.test_brain_wiring import FakeEmbedder, FakeOBS, FakeRegistry, FakeSTT, FakeTTS

    shutil.copytree(Path("data/prompts"), tmp_path / "data/prompts")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", "config.json")
    monkeypatch.setattr(embedder_module, "FastEmbedEmbedder", FakeEmbedder)

    config = BrainConfig()
    config.skills["memory"]["db_path"] = ":memory:"
    config.persona = {"name": "Luna", "pronouns": "she/her"}
    config.attention["trigger_words"] = []
    for key in ("discord", "telegram", "twitch", "minecraft", "donations", "dream"):
        config.skills.setdefault(key, {})["enabled"] = False

    engine = AIVtuberBrain(config, FakeRegistry(), FakeTTS(), FakeSTT(), FakeOBS())
    engine.initialize()
    return engine


def test_the_attention_gate_listens_for_the_new_name(renamed):
    assert list(renamed.attention.trigger_words) == ["luna"]


def test_telegram_listens_for_it_too(renamed):
    telegram = renamed.skill_registry.get("chat:telegram")
    assert telegram._trigger_words() == ["luna"]


def test_twitch_listens_for_it_too(renamed):
    twitch = renamed.skill_registry.get("chat:twitch")
    assert twitch._trigger_words() == ["luna"]


def test_the_body_prompt_no_longer_belongs_to_someone_else(renamed):
    """minecraft_body.md said "You are Bea's body" with the name baked in."""
    minecraft = renamed.skill_registry.get("game:mc")
    assert "Bea" not in minecraft._body_rules


def test_her_own_lines_are_filed_under_the_new_name(renamed):
    renamed.conversations._record_outgoing("telegram:2", ["ciao"], [])
    entry = renamed.memory.conversations.history("telegram:2")[0]
    assert entry["display_name"] == "Luna"


async def test_a_message_she_starts_herself_is_filed_under_it_too(renamed):
    renamed.memory.roster.record(identity="telegram:2", display_name="Ema", platform="telegram")
    card = renamed.memory.people.create_from_entry(renamed.memory.roster.get("telegram:2"))
    assert card

    class Telegram:
        platform = "telegram"
        supports_dm = True
        active = True
        name = "chat:telegram"

        async def send_dm(self, native_id, text):
            return native_id

    renamed.skill_registry._skills["chat:telegram"] = Telegram()
    await renamed.reach.message("Ema", "ehi")
    assert renamed.memory.conversations.history("telegram:2")[0]["display_name"] == "Luna"


def test_nothing_in_her_prompt_still_calls_her_bea(renamed):
    """The one that matters: after a rename, the old name is gone."""
    assert "Bea" not in renamed.system_prompt
    assert "{name}" not in renamed.system_prompt
    assert "Luna" in renamed.system_prompt


def test_the_default_persona_leaves_the_shipped_experience_alone(tmp_path, monkeypatch):
    """Someone who never opens the persona screen must see exactly what shipped."""
    from src.core.config import BrainConfig

    monkeypatch.chdir(tmp_path)
    config = BrainConfig()
    p = persona_of(config)
    assert p.name == "Bea"
    assert set(p.trigger_words) >= {"bea"}
