"""The eight providers as one table: buildable, keyless where promised, precise errors.

The factory is the single place that instantiates a provider, so every way to
misconfigure one — a missing key, a custom endpoint with no url, an unknown id
— must fail here with a message that names the missing thing, not somewhere
down the line with a connection error.
"""

import pytest

from src.modules.llm.anthropic import AnthropicClient
from src.modules.llm.chat import ChatCompletionsClient
from src.modules.llm.factory import LLMConfigError, build_client, build_llm
from src.modules.llm.providers import PROVIDERS, get
from src.modules.llm.responses import ResponsesClient


class Config:
    def __init__(self, **overrides):
        self.llm_provider = "openrouter"
        self.models = {"mind": [], "background": [], "reasoning": "off"}
        self.openrouter_key = "or-k"
        self.openrouter_model = "deepseek/deepseek-v4-flash"
        self.openai_key = "sk-k"
        self.openai_model = "gpt-5"
        self.groq_key = "gsk-k"
        self.groq_model = "openai/gpt-oss-20b"
        self.google_key = "AIza-k"
        self.google_model = "gemini-3.8-flash"
        self.claude_key = "sk-ant-k"
        self.claude_model = "claude-sonnet-5"
        self.openai_compat_key = None
        self.openai_compat_base_url = "https://x/v1"
        self.openai_compat_model = "m"
        self.openai_compat_api = "chat"
        self.anthropic_compat_key = None
        self.anthropic_compat_base_url = "https://y/v1"
        self.anthropic_compat_model = "m"
        self.local_key = None
        self.local_base_url = "http://localhost:11434/v1"
        self.local_model = "qwen3:8b"
        for key, value in overrides.items():
            setattr(self, key, value)


# --- the table ---------------------------------------------------------------


def test_every_provider_names_a_known_transport():
    from src.modules.llm.providers import TRANSPORTS

    assert set(PROVIDERS) == {"openrouter", "openai", "groq", "google", "claude",
                              "openai_compat", "anthropic_compat", "local"}
    for preset in PROVIDERS.values():
        assert preset.transport in TRANSPORTS


def test_first_party_providers_come_with_url_and_default_model():
    for provider_id in ("openai", "openrouter", "groq", "google", "claude", "local"):
        preset = get(provider_id)
        assert preset.base_url.startswith("https://" if provider_id != "local" else "http://")
        assert preset.default_model
        assert preset.env_var


def test_brought_your_own_endpoints_have_no_defaults_to_guess():
    assert get("openai_compat").default_model == ""
    assert get("openai_compat").base_url == ""
    assert get("anthropic_compat").default_model == ""


def test_every_config_field_the_table_names_exists():
    import dataclasses

    from src.core.config import BrainConfig

    fields = {f.name for f in dataclasses.fields(BrainConfig)}
    for preset in PROVIDERS.values():
        assert preset.model_field in fields
        if preset.key_field:
            assert preset.key_field in fields
        if preset.url_field:
            assert preset.url_field in fields
        if preset.api_choice_field:
            assert preset.api_choice_field in fields


# --- building -----------------------------------------------------------------


def test_openai_builds_a_responses_client():
    client = build_client("openai", "gpt-5", Config())
    assert isinstance(client, ResponsesClient)
    assert client.base_url == "https://api.openai.com/v1"


def test_openrouter_and_groq_ride_the_same_transport():
    assert isinstance(build_client("openrouter", "m", Config()), ResponsesClient)
    assert isinstance(build_client("groq", "m", Config()), ResponsesClient)


def test_google_builds_a_chat_client_on_its_own_endpoint():
    client = build_client("google", "gemini-3.8-flash", Config())
    assert isinstance(client, ChatCompletionsClient)
    assert client.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"


def test_claude_builds_an_anthropic_client():
    client = build_client("claude", "claude-sonnet-5", Config())
    assert isinstance(client, AnthropicClient)
    assert client.base_url == "https://api.anthropic.com/v1"


def test_local_needs_no_key_and_skips_tool_choice():
    client = build_client("local", "qwen3:8b", Config())
    assert isinstance(client, ChatCompletionsClient)
    assert client.base_url == "http://localhost:11434/v1"
    assert client.send_tool_choice is False


def test_local_points_where_it_is_told_to():
    client = build_client("local", "m", Config(local_base_url="http://localhost:1234/v1"))
    assert client.base_url == "http://localhost:1234/v1"


def test_openai_compat_defaults_to_chat_and_honours_the_knob():
    assert isinstance(build_client("openai_compat", "m", Config()), ChatCompletionsClient)
    switched = build_client("openai_compat", "m", Config(openai_compat_api="responses"))
    assert isinstance(switched, ResponsesClient)


def test_anthropic_compat_builds_an_anthropic_client():
    assert isinstance(build_client("anthropic_compat", "m", Config()), AnthropicClient)


def test_a_keyed_provider_without_its_key_names_the_field():
    with pytest.raises(LLMConfigError, match="google_key"):
        build_client("google", "m", Config(google_key=None))


def test_a_custom_endpoint_without_its_url_names_the_field():
    with pytest.raises(LLMConfigError, match="openai_compat_base_url"):
        build_client("openai_compat", "m", Config(openai_compat_base_url=""))


def test_an_unknown_provider_lists_what_exists():
    with pytest.raises(LLMConfigError, match="Unknown LLM provider.*local"):
        build_client("ollama", "m", Config())


def test_a_bad_protocol_choice_is_rejected():
    with pytest.raises(LLMConfigError, match="openai_compat_api"):
        build_client("openai_compat", "m", Config(openai_compat_api="smoke-signals"))


def test_the_legacy_single_model_path_reaches_the_new_providers():
    client = build_llm(Config(llm_provider="local", local_model="qwen3:8b"))
    assert isinstance(client, ChatCompletionsClient)
    assert client.model_name == "qwen3:8b"


def test_reload_picks_up_key_url_and_model():
    client = build_client("openai_compat", "m", Config())
    build_client("openai_compat", "m", Config())  # a second client is unaffected
    client.reload_config(Config(openai_compat_key="new",
                                openai_compat_base_url="https://z/v1",
                                openai_compat_model="other"))
    assert client.api_key == "new"
    assert client.base_url == "https://z/v1"
    assert client.model_name == "other"


# --- pools ---------------------------------------------------------------------


def test_a_local_pool_builds_with_no_key_at_all():
    from src.core.agent.registry import ModelRegistry

    registry = ModelRegistry(Config(models={"mind": ["local:qwen3:8b"],
                                            "background": [], "reasoning": "off"}))
    assert registry.get("mind").model_name == "qwen3:8b"


def test_a_mixed_pool_falls_back_across_protocols():
    from src.core.agent.registry import ModelRegistry, RotatingClient

    registry = ModelRegistry(Config(models={
        "mind": ["claude:claude-sonnet-5", "local:qwen3:8b"],
        "background": [], "reasoning": "off"}))
    pool = registry.get("mind")
    assert isinstance(pool, RotatingClient)
    assert [c.model_name for c in pool.clients] == ["claude-sonnet-5", "qwen3:8b"]


# --- end to end: the runner drives a real transport ------------------------------
#
# The minecraft body (and every sub-agent) runs this exact loop: think, act on
# tools, observe, repeat. Fakes on both sides would prove nothing about the
# wire; here the runner is real, the transport is real, and only https is
# faked — including the second turn, where yesterday's tool calls must travel
# back in a shape the endpoint accepts.


def _registry():
    from src.core.agent.tools import ToolRegistry

    dug = []
    registry = ToolRegistry()
    registry.add("dig", "Dig a block.",
                 {"type": "object", "properties": {"block": {"type": "string"}}},
                 lambda block: dug.append(block) or "dug " + block)
    registry.dug = dug
    return registry


def _wire(monkeypatch, *responses):
    import json as _json

    import aiohttp

    class Content:
        def __init__(self, lines):
            self._lines = lines

        def __aiter__(self):
            async def gen():
                for line in self._lines:
                    yield (line + "\n").encode()
            return gen()

    class Response:
        def __init__(self, status=200, payload=None, lines=None):
            self.status = status
            self._payload = payload
            self.content = Content(lines or [])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def text(self):
            return _json.dumps(self._payload) if self._payload is not None else ""

    class Session:
        posts = []

        def __init__(self, shared):
            self._shared = shared

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, url, headers=None, json=None):
            Session.posts.append(json)
            item = self._shared.pop(0)
            if isinstance(item, _Resp):
                item = Response(status=item.status, payload=item.payload,
                                lines=item.lines)
            return item

    Session.posts = []
    shared = list(responses)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: Session(shared))
    return Session


def _chat_turn(calls=(), text=None):
    import json as _json

    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = [
            {"id": i, "type": "function",
             "function": {"name": n, "arguments": _json.dumps(a)}} for i, n, a in calls]
    return {"choices": [{"message": message}], "usage": {}}


class _Resp:
    def __init__(self, status=200, payload=None, lines=None):
        self.status = status
        self.payload = payload
        self.lines = lines


async def test_the_runner_thinks_acts_and_observes_over_chat(monkeypatch):
    from src.core.agent.runner import AgentRunner
    from src.modules.llm.chat import ChatCompletionsClient

    dug_turn = _Resp(payload=_chat_turn(calls=[("c1", "dig", {"block": "stone"})]))
    done_turn = _Resp(payload=_chat_turn(text="all dug"))
    session = _wire(monkeypatch, dug_turn, done_turn)

    client = ChatCompletionsClient(base_url="https://x/v1", model_name="m")
    registry = _registry()
    final = await AgentRunner(client, registry, max_steps=3).run(
        [{"role": "user", "content": "dig something"}])

    assert registry.dug == ["stone"]
    assert final.content == "all dug"
    replayed = session.posts[1]["messages"]
    assistant = next(m for m in replayed if m.get("role") == "assistant")
    assert assistant["tool_calls"][0]["id"] == "c1"
    tool = next(m for m in replayed if m.get("role") == "tool")
    assert tool["tool_call_id"] == "c1" and "dug stone" in tool["content"]


async def test_the_runner_replays_tool_history_over_anthropic(monkeypatch):
    from src.core.agent.runner import AgentRunner
    from src.modules.llm.anthropic import AnthropicClient

    first = {"content": [{"type": "tool_use", "id": "tu_1", "name": "dig",
                          "input": {"block": "dirt"}}],
             "usage": {"input_tokens": 5, "output_tokens": 5}}
    second = {"content": [{"type": "text", "text": "dug it"}],
              "usage": {"input_tokens": 9, "output_tokens": 2}}
    session = _wire(monkeypatch, _Resp(payload=first), _Resp(payload=second))

    client = AnthropicClient(base_url="https://y/v1", model_name="m", api_key="k")
    registry = _registry()
    final = await AgentRunner(client, registry, max_steps=3).run(
        [{"role": "user", "content": "dig something"}])

    assert registry.dug == ["dirt"]
    assert final.content == "dug it"
    replayed = session.posts[1]["messages"]
    blocks = [b for m in replayed if isinstance(m.get("content"), list)
              for b in m["content"]]
    use = next(b for b in blocks if b["type"] == "tool_use")
    assert use["id"] == "tu_1" and use["input"] == {"block": "dirt"}
    result = next(b for b in blocks if b["type"] == "tool_result")
    assert result["tool_use_id"] == "tu_1" and "dug dirt" in result["content"]


# --- the doctor looks at them too -----------------------------------------------


def doctor_config(**kwargs):
    from src.core.config import BrainConfig

    settings = BrainConfig()
    for key, value in kwargs.items():
        setattr(settings, key, value)
    return settings


async def test_a_local_pool_is_not_asked_for_a_key_it_cannot_have(monkeypatch):
    from src.setup.doctor import check_keys

    monkeypatch.delenv("LOCAL_API_KEY", raising=False)
    settings = doctor_config(models={"mind": ["local:qwen3:8b"], "background": []},
                             stt_provider="faster_whisper", local_key=None)
    assert (await check_keys(settings)).ok


async def test_a_custom_endpoint_without_a_url_is_named(monkeypatch):
    from src.setup.doctor import check_keys

    settings = doctor_config(models={"mind": ["openai_compat:m"], "background": []},
                             stt_provider="faster_whisper",
                             openai_compat_base_url="")
    found = await check_keys(settings)
    assert not found.ok and found.stops
    assert "openai_compat_base_url" in found.fix


async def test_an_unknown_provider_in_a_pool_is_named():
    from src.setup.doctor import check_keys

    settings = doctor_config(models={"mind": ["hal9000:m"], "background": []},
                             stt_provider="faster_whisper")
    found = await check_keys(settings)
    assert not found.ok and "hal9000" in found.detail


async def test_a_claude_pool_without_a_key_names_the_variable(monkeypatch):
    from src.setup.doctor import check_keys

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = doctor_config(models={"mind": ["claude:claude-sonnet-5"], "background": []},
                             stt_provider="faster_whisper", claude_key=None)
    found = await check_keys(settings)
    assert not found.ok and "ANTHROPIC_API_KEY" in found.fix


# --- the wizard writes them -----------------------------------------------------


def test_apply_answers_sets_a_bring_your_own_endpoint(tmp_path, monkeypatch):
    from src.setup.config_plan import apply_answers

    monkeypatch.chdir(tmp_path)
    from src.core.config import BrainConfig

    cfg = apply_answers(BrainConfig(), {
        "llm_provider": "openai_compat", "llm_key": "k", "llm_model": "m",
        "llm_base_url": "https://x/v1", "skills": {}})
    assert (cfg.openai_compat_base_url, cfg.openai_compat_model) == ("https://x/v1", "m")
    assert cfg.openai_compat_key == "k"


def test_apply_answers_leaves_a_keyless_local_alone(tmp_path, monkeypatch):
    from src.setup.config_plan import apply_answers

    monkeypatch.chdir(tmp_path)
    from src.core.config import BrainConfig

    cfg = apply_answers(BrainConfig(), {
        "llm_provider": "local", "llm_model": "qwen3:8b",
        "llm_base_url": "http://localhost:1234/v1", "skills": {}})
    assert cfg.local_key is None
    assert cfg.local_base_url == "http://localhost:1234/v1"
    assert cfg.local_model == "qwen3:8b"


def test_env_updates_writes_no_secret_for_a_keyless_local():
    from src.setup.config_plan import env_updates

    assert env_updates({"llm_provider": "local", "skills": {}}) == {}


def test_env_updates_carries_a_custom_endpoint_key():
    from src.setup.config_plan import env_updates

    updates = env_updates({"llm_provider": "openai_compat", "llm_key": "k",
                           "skills": {}})
    assert updates == {"OPENAI_COMPAT_API_KEY": "k"}


# --- the cli reaches them ---------------------------------------------------------


def test_every_provider_is_passable_on_the_command_line():
    from src import cli
    from src.modules.llm.providers import PROVIDERS

    for provider_id in PROVIDERS:
        assert cli.parse_args(["--llm-provider", provider_id]).llm_provider == provider_id


def test_the_new_flags_reach_the_fields_they_name():
    from src import cli
    from src.core.config import BrainConfig

    config = BrainConfig()
    cli.apply_cli_overrides(config, cli.parse_args([
        "--google-model", "gemini-3.8-flash",
        "--claude-model", "claude-sonnet-5",
        "--local-model", "qwen3:8b",
        "--local-base-url", "http://localhost:1234/v1",
        "--openai-compat-base-url", "https://x/v1",
        "--openai-compat-api", "responses",
    ]))
    assert config.google_model == "gemini-3.8-flash"
    assert config.claude_model == "claude-sonnet-5"
    assert config.local_model == "qwen3:8b"
    assert config.local_base_url == "http://localhost:1234/v1"
    assert config.openai_compat_base_url == "https://x/v1"
    assert config.openai_compat_api == "responses"
