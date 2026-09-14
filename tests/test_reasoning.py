"""Bea is in a voice call: a model that thinks for eight seconds is unusable.

Every provider spells "answer without reasoning" differently, so the intent is
translated once per provider and injected into every call. Models that force
reasoning reject those fields — then the call is retried without them rather
than failing.
"""

import pytest

from src.core.agent.types import AssistantMessage
from src.modules.llm.base import AsyncLLMClient
from src.modules.llm.reasoning import ReasoningStyle, style_for

# --- the translation, per provider -------------------------------------------


def test_openrouter_is_told_to_switch_reasoning_off():
    style = style_for("openrouter", "off")
    assert style.extra_body == {"reasoning": {"effort": "minimal"}}
    assert style.optional_keys == ("reasoning",)


def test_openrouter_low_asks_for_the_cheapest_reasoning():
    style = style_for("openrouter", "low")
    assert style.extra_body == {"reasoning": {"effort": "low"}}


def test_groq_hides_behind_the_same_effort_object():
    style = style_for("groq", "off")
    assert style.extra_body == {"reasoning": {"effort": "minimal"}}


def test_groq_low_keeps_the_effort_minimal():
    style = style_for("groq", "low")
    assert style.extra_body["reasoning"] == {"effort": "low"}


def test_openai_direct_uses_the_responses_shape():
    assert style_for("openai", "low").extra_body == {"reasoning": {"effort": "low"}}


def test_chat_shaped_providers_keep_their_own_field():
    assert style_for("openai_compat", "low").extra_body == {"reasoning_effort": "low"}
    assert style_for("openai_compat", "off").extra_body == {"reasoning_effort": "minimal"}


def test_local_off_really_switches_thinking_off():
    """ollama clamps minimal to low: only none stops a local thinker."""
    style = style_for("local", "off")
    assert style.extra_body == {"reasoning_effort": "none"}
    assert style.optional_keys == ("reasoning_effort",)
    assert style_for("local", "low").extra_body == {"reasoning_effort": "low"}


def test_google_and_claude_get_no_reasoning_hint():
    """Their endpoints document no equivalent: guessing turns calls into 400s."""
    assert style_for("google", "off").extra_body == {}
    assert style_for("claude", "off").extra_body == {}
    assert style_for("anthropic_compat", "low").extra_body == {}


def test_auto_means_do_not_interfere():
    for provider in ("openrouter", "groq", "openai", "local", "google", "claude"):
        style = style_for(provider, "auto")
        assert style.extra_body == {}
        assert style.optional_keys == ()


def test_an_unknown_provider_does_not_guess():
    assert style_for("something-else", "off").extra_body == {}


def test_an_unknown_level_falls_back_to_auto():
    assert style_for("openrouter", "banana").extra_body == {}


# --- what actually reaches the wire -------------------------------------------


class FakeContent:
    def __init__(self, lines):
        self._lines = lines

    def __aiter__(self):
        async def gen():
            for line in self._lines:
                yield (line + "\n").encode()
        return gen()


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self._payload = payload
        self.content = FakeContent([])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def text(self):
        import json as _json

        return _json.dumps(self._payload) if self._payload is not None else ""


class FakeSession:
    posts = []

    def __init__(self, shared):
        self._shared = shared

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, headers=None, json=None):
        FakeSession.posts.append(json)
        if len(self._shared) > 1:
            return self._shared.pop(0)
        return self._shared[0]


def serve(monkeypatch, *responses):
    import aiohttp

    FakeSession.posts = []
    shared = list(responses)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: FakeSession(shared))


def _reply(text: str):
    return {"id": "resp_1", "status": "completed",
            "output": [{"type": "message",
                        "content": [{"type": "output_text", "text": text}]}],
            "usage": {"input_tokens": 1, "output_tokens": 1}}


def client(monkeypatch, style: ReasoningStyle, fail_times: int = 0) -> AsyncLLMClient:
    from src.modules.llm.responses import ResponsesClient

    refused = FakeResponse(status=400, payload={"error": {"message": "reasoning refused"}})
    serve(monkeypatch, *([refused] * fail_times), FakeResponse(payload=_reply("ciao")))
    return ResponsesClient(base_url="https://x/v1", model_name="a/model", reasoning=style)


async def test_the_reasoning_fields_travel_with_every_call(monkeypatch):
    c = client(monkeypatch, style_for("openrouter", "off"))
    await c.complete([{"role": "user", "content": "ciao"}])
    assert FakeSession.posts[0]["reasoning"] == {"effort": "minimal"}


async def test_a_model_that_refuses_them_is_retried_without(monkeypatch):
    c = client(monkeypatch, style_for("openrouter", "off"), fail_times=1)
    reply = await c.complete([{"role": "user", "content": "ciao"}])
    assert len(FakeSession.posts) == 2
    assert "reasoning" not in FakeSession.posts[1]
    assert isinstance(reply, AssistantMessage)
    assert reply.content == "ciao"


async def test_a_real_failure_is_not_swallowed(monkeypatch):
    c = client(monkeypatch, style_for("openrouter", "off"), fail_times=2)
    with pytest.raises(RuntimeError):
        await c.complete([{"role": "user", "content": "ciao"}])


async def test_without_a_style_nothing_extra_is_sent(monkeypatch):
    from src.modules.llm.responses import ResponsesClient

    serve(monkeypatch, FakeResponse(payload=_reply("ciao")))
    c = ResponsesClient(base_url="https://x/v1", model_name="a/model")
    await c.complete([{"role": "user", "content": "ciao"}])
    assert "reasoning" not in FakeSession.posts[0]


def test_the_legacy_json_path_carries_it_too(monkeypatch):
    from src.modules.llm.chat import ChatCompletionsClient

    serve(monkeypatch, FakeResponse(payload={
        "choices": [{"message": {"content": '{"a": 1}'}}], "usage": {}}))
    c = ChatCompletionsClient(base_url="https://x/v1", model_name="a/model",
                              reasoning=style_for("local", "off"))
    import asyncio

    asyncio.run(c.complete_json("ciao"))
    assert FakeSession.posts[0]["reasoning_effort"] == "none"


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
    assert c.reasoning.extra_body == {"reasoning": {"effort": "minimal"}}


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
    assert cfg.attention["followup_window_seconds"] == 180
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
