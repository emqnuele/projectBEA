"""Bea is in a voice call: a model that thinks for eight seconds is unusable.

Every provider spells "answer without reasoning" differently, so the intent is
translated once per provider and injected into every call. Models that force
reasoning reject those fields — then the call is retried without them rather
than failing.
"""

import pytest

from src.core.agent.types import AssistantMessage
from src.modules.llm.openai_compat import OpenAICompatibleClient
from src.modules.llm.reasoning import ReasoningStyle, style_for

# --- the translation, per provider -------------------------------------------


def test_openrouter_is_told_to_switch_reasoning_off():
    style = style_for("openrouter", "off")
    assert style.extra_body == {"reasoning": {"enabled": False}}
    assert style.optional_keys == ("reasoning",)


def test_openrouter_low_asks_for_the_cheapest_reasoning():
    style = style_for("openrouter", "low")
    assert style.extra_body == {"reasoning": {"effort": "low", "exclude": True}}


def test_groq_hides_the_reasoning_it_cannot_switch_off():
    style = style_for("groq", "off")
    assert style.extra_body["reasoning_format"] == "hidden"
    assert style.extra_body["reasoning_effort"] == "none"


def test_groq_low_keeps_the_effort_minimal():
    style = style_for("groq", "low")
    assert style.extra_body["reasoning_effort"] == "low"


def test_openai_uses_its_own_field():
    assert style_for("openai", "low").extra_body == {"reasoning_effort": "low"}


def test_auto_means_do_not_interfere():
    for provider in ("openrouter", "groq", "openai"):
        style = style_for(provider, "auto")
        assert style.extra_body == {}
        assert style.optional_keys == ()


def test_an_unknown_provider_does_not_guess():
    assert style_for("something-else", "off").extra_body == {}


def test_an_unknown_level_falls_back_to_auto():
    assert style_for("openrouter", "banana").extra_body == {}


# --- what actually reaches the sdk -------------------------------------------


class FakeCompletions:
    def __init__(self, fail_times: int = 0):
        self.calls = []
        self.fail_times = fail_times

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("Unrecognized request argument supplied: reasoning")
        return _reply("ciao")


class FakeSDK:
    def __init__(self, fail_times: int = 0):
        self.chat = type("Chat", (), {})()
        self.chat.completions = FakeCompletions(fail_times)


def _reply(text: str):
    message = type("Msg", (), {"content": text, "tool_calls": None})()
    choice = type("Choice", (), {"message": message})()
    return type("Response", (), {"choices": [choice], "usage": None})()


def client(style: ReasoningStyle, fail_times: int = 0) -> OpenAICompatibleClient:
    sdk = FakeSDK(fail_times)
    return OpenAICompatibleClient(sdk, "a/model", reasoning=style)


async def test_the_reasoning_fields_travel_with_every_call():
    c = client(style_for("openrouter", "off"))
    await c.complete([{"role": "user", "content": "ciao"}])
    assert c.client.chat.completions.calls[0]["extra_body"] == {"reasoning": {"enabled": False}}


async def test_a_model_that_refuses_them_is_retried_without():
    c = client(style_for("openrouter", "off"), fail_times=1)
    reply = await c.complete([{"role": "user", "content": "ciao"}])
    calls = c.client.chat.completions.calls
    assert len(calls) == 2
    assert "extra_body" not in calls[1] or not calls[1]["extra_body"]
    assert isinstance(reply, AssistantMessage)
    assert reply.content == "ciao"


async def test_a_real_failure_is_not_swallowed():
    c = client(style_for("openrouter", "off"), fail_times=2)
    with pytest.raises(RuntimeError):
        await c.complete([{"role": "user", "content": "ciao"}])


async def test_without_a_style_nothing_extra_is_sent():
    c = OpenAICompatibleClient(FakeSDK(), "a/model")
    await c.complete([{"role": "user", "content": "ciao"}])
    assert not c.client.chat.completions.calls[0].get("extra_body")


def test_the_legacy_json_path_carries_it_too():
    c = client(style_for("groq", "off"))
    c.generate_json("ciao")
    assert c.client.chat.completions.calls[0]["extra_body"]["reasoning_format"] == "hidden"


# --- the factory reads it from config ----------------------------------------


class Config:
    def __init__(self, **models):
        self.openrouter_key = "k"
        self.groq_key = "k"
        self.openai_key = "k"
        self.llm_provider = "openrouter"
        self.openrouter_model = "a/model"
        self.models = {"mind": [], "background": [], **models}


def test_the_default_is_no_thinking_for_speed():
    from src.core.config import BrainConfig

    assert BrainConfig().models["reasoning"] == "off"


def test_a_built_client_carries_the_configured_style():
    from src.modules.llm.factory import build_client

    c = build_client("openrouter", "a/model", Config(reasoning="off"))
    assert c.reasoning.extra_body == {"reasoning": {"enabled": False}}


def test_auto_builds_a_client_that_asks_for_nothing():
    from src.modules.llm.factory import build_client

    c = build_client("openrouter", "a/model", Config(reasoning="auto"))
    assert c.reasoning.extra_body == {}


# --- an existing config.json must not hide a new setting ---------------------


def test_a_config_file_without_the_key_keeps_the_default(tmp_path, monkeypatch):
    """Adding a setting must not vanish for everyone who already has a config."""
    import json

    from src.core import config as config_module

    old = tmp_path / "config.json"
    old.write_text(json.dumps({"models": {"mind": ["groq:a"], "background": []}}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", "config.json")

    cfg = config_module.BrainConfig()
    assert cfg.models["mind"] == ["groq:a"]
    assert cfg.models["reasoning"] == "off"


def test_the_same_holds_for_every_nested_block(tmp_path, monkeypatch):
    import json

    from src.core import config as config_module

    (tmp_path / "config.json").write_text(json.dumps({
        "attention": {"cooldown_seconds": 5},
        "rhythm": {"tick_seconds": 60},
        "consciousness": {"window": 0.9},
    }))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", "config.json")

    cfg = config_module.BrainConfig()
    assert cfg.attention["cooldown_seconds"] == 5
    assert cfg.attention["trigger_words"] == ["bea", "beatrice"]
    assert cfg.rhythm["tick_seconds"] == 60
    assert cfg.rhythm["spontaneous_enabled"] is True
    assert cfg.consciousness["window"] == 0.9
    assert cfg.consciousness["burst_steps"] == 6


def test_a_list_setting_is_replaced_not_merged(tmp_path, monkeypatch):
    import json

    from src.core import config as config_module

    (tmp_path / "config.json").write_text(json.dumps({
        "attention": {"trigger_words": ["bea"]},
    }))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", "config.json")

    assert config_module.BrainConfig().attention["trigger_words"] == ["bea"]
