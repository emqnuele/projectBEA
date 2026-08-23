"""Model pools: rotation to spread load, fallback so one dead provider is survivable."""

import asyncio

import pytest

from src.core.agent.registry import (
    ModelPoolError,
    ModelRegistry,
    RotatingClient,
    looks_like_missing_tool_support,
)
from src.core.agent.types import AssistantMessage


class StubClient:
    """A named client that can be told to fail."""

    def __init__(self, name: str, error: Exception = None):
        self.name = name
        self.error = error
        self.calls = 0
        self.reloads = 0

    async def complete(self, messages, tools=None, response_format=None):
        self.calls += 1
        if self.error:
            raise self.error
        return AssistantMessage(content=self.name)

    async def complete_json(self, user_input, system_prompt=None, history=None):
        self.calls += 1
        if self.error:
            raise self.error
        return {"from": self.name}

    def reload_config(self, config):
        self.reloads += 1


class Config:
    def __init__(self, models=None, **fields):
        self.models = models if models is not None else {}
        self.llm_provider = fields.pop("llm_provider", "openrouter")
        self.openrouter_model = fields.pop("openrouter_model", "deepseek/deepseek-v4-flash")
        self.groq_model = fields.pop("groq_model", "openai/gpt-oss-20b")
        self.openai_model = fields.pop("openai_model", "gpt-5")
        self.openrouter_key = fields.pop("openrouter_key", "or-key")
        self.groq_key = fields.pop("groq_key", "groq-key")
        self.openai_key = fields.pop("openai_key", None)
        for k, v in fields.items():
            setattr(self, k, v)


# --- RotatingClient ---------------------------------------------------------


async def test_a_single_client_is_always_used():
    a = StubClient("a")
    pool = RotatingClient([a])
    for _ in range(3):
        assert (await pool.complete([])).content == "a"
    assert a.calls == 3


async def test_calls_rotate_through_the_pool():
    a, b, c = StubClient("a"), StubClient("b"), StubClient("c")
    pool = RotatingClient([a, b, c])
    got = [(await pool.complete([])).content for _ in range(6)]
    assert got == ["a", "b", "c", "a", "b", "c"]


async def test_a_failing_client_falls_through_to_the_next():
    dead, alive = StubClient("dead", RuntimeError("429")), StubClient("alive")
    pool = RotatingClient([dead, alive])
    assert (await pool.complete([])).content == "alive"


async def test_a_dead_provider_never_makes_her_mute():
    """One provider down must not silence her: the pool keeps answering."""
    dead, alive = StubClient("dead", RuntimeError("503")), StubClient("alive")
    pool = RotatingClient([dead, alive])
    got = [(await pool.complete([])).content for _ in range(4)]
    assert got == ["alive"] * 4


async def test_an_empty_pool_is_refused_at_construction():
    with pytest.raises(ModelPoolError):
        RotatingClient([])


async def test_when_everything_fails_the_error_says_so():
    pool = RotatingClient([StubClient("a", RuntimeError("boom")),
                           StubClient("b", RuntimeError("bang"))])
    with pytest.raises(ModelPoolError, match="every model"):
        await pool.complete([])


async def test_cancellation_is_not_swallowed_as_a_failure():
    pool = RotatingClient([StubClient("a", asyncio.CancelledError())])
    with pytest.raises(asyncio.CancelledError):
        await pool.complete([])


async def test_json_calls_fall_back_too():
    pool = RotatingClient([StubClient("dead", RuntimeError("nope")), StubClient("alive")])
    assert await pool.complete_json("hi") == {"from": "alive"}


def test_reloading_reaches_every_client():
    a, b = StubClient("a"), StubClient("b")
    RotatingClient([a, b]).reload_config(Config())
    assert a.reloads == 1 and b.reloads == 1


# --- the tool-calling constraint --------------------------------------------


@pytest.mark.parametrize("message", [
    "This model does not support tools",
    "tool calling is not supported for this model",
    "Function calling not available on gemma",
])
def test_missing_tool_support_is_recognised(message):
    assert looks_like_missing_tool_support(RuntimeError(message)) is True


@pytest.mark.parametrize("message", ["rate limit exceeded", "502 bad gateway", "timeout"])
def test_ordinary_failures_are_not_mistaken_for_it(message):
    assert looks_like_missing_tool_support(RuntimeError(message)) is False


async def test_a_model_without_tool_support_is_skipped_not_fatal():
    """It is a configuration mistake, but Bea keeps talking through the next model."""
    no_tools = StubClient("gemma", RuntimeError("This model does not support tools"))
    good = StubClient("gpt-oss")
    pool = RotatingClient([no_tools, good])
    assert (await pool.complete([], tools=[{"function": {"name": "speak"}}])).content == "gpt-oss"


# --- ModelRegistry ----------------------------------------------------------


def test_a_pool_spec_builds_one_client_per_entry():
    registry = ModelRegistry(Config(models={
        "mind": ["openrouter:deepseek/deepseek-v4-flash", "groq:openai/gpt-oss-120b"]
    }))
    client = registry.get("mind")
    assert isinstance(client, RotatingClient)
    assert [c.model_name for c in client.clients] == [
        "deepseek/deepseek-v4-flash", "openai/gpt-oss-120b"
    ]


def test_openrouter_ids_keep_their_slash_and_free_suffix():
    """Splitting on the LAST colon would mangle `vendor/model:free`."""
    registry = ModelRegistry(Config(models={"mind": ["openrouter:google/gemma-4-31b-it:free"]}))
    assert registry.get("mind").model_name == "google/gemma-4-31b-it:free"


def test_a_single_entry_pool_is_not_wrapped():
    registry = ModelRegistry(Config(models={"mind": ["groq:openai/gpt-oss-20b"]}))
    assert not isinstance(registry.get("mind"), RotatingClient)


def test_a_role_is_built_once_and_cached():
    registry = ModelRegistry(Config(models={"mind": ["groq:openai/gpt-oss-20b"]}))
    assert registry.get("mind") is registry.get("mind")


def test_entries_without_a_key_are_skipped():
    registry = ModelRegistry(Config(models={"mind": ["openai:gpt-5", "groq:openai/gpt-oss-20b"]},
                                    openai_key=None))
    client = registry.get("mind")
    assert client.model_name == "openai/gpt-oss-20b"


def test_an_unusable_role_raises_with_an_actionable_message():
    registry = ModelRegistry(Config(models={"mind": ["openai:gpt-5"]}, openai_key=None))
    with pytest.raises(ModelPoolError, match="mind"):
        registry.get("mind")


def test_a_malformed_spec_is_skipped():
    registry = ModelRegistry(Config(models={"mind": ["nonsense", "groq:openai/gpt-oss-20b"]}))
    assert registry.get("mind").model_name == "openai/gpt-oss-20b"


def test_an_unknown_provider_is_skipped():
    registry = ModelRegistry(Config(models={"mind": ["ollama:llama3", "groq:openai/gpt-oss-20b"]}))
    assert registry.get("mind").model_name == "openai/gpt-oss-20b"


def test_an_empty_pool_falls_back_to_the_legacy_single_model():
    """Existing configs must keep working untouched after the upgrade."""
    registry = ModelRegistry(Config(models={}, llm_provider="groq"))
    assert registry.get("mind").model_name == "openai/gpt-oss-20b"


def test_background_and_mind_are_separate_clients():
    registry = ModelRegistry(Config(models={
        "mind": ["groq:openai/gpt-oss-120b"],
        "background": ["openrouter:google/gemma-4-31b-it:free"],
    }))
    assert registry.get("mind").model_name == "openai/gpt-oss-120b"
    assert registry.get("background").model_name == "google/gemma-4-31b-it:free"


def test_reloading_rebuilds_the_roles():
    config = Config(models={"mind": ["groq:openai/gpt-oss-20b"]})
    registry = ModelRegistry(config)
    first = registry.get("mind")
    config.models["mind"] = ["groq:openai/gpt-oss-120b"]
    registry.reload_config(config)
    assert registry.get("mind") is not first
    assert registry.get("mind").model_name == "openai/gpt-oss-120b"
