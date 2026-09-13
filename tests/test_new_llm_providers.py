"""Tests for the 5 new LLM providers:
- Google AI Studio
- OpenAI Compatible (Generic)
- Local LLM (Ollama, LM Studio)
- Claude (Anthropic)
- Anthropic Compatible (Generic)
"""

import pytest

from src.cli import apply_cli_overrides, parse_args
from src.core.config import BrainConfig
from src.modules.llm.anthropic_compat import (
    _clean_schema,
    _convert_messages,
    _convert_tools,
)
from src.modules.llm.anthropic_compat_llm import AnthropicCompatLLM
from src.modules.llm.claude_llm import ClaudeLLM
from src.modules.llm.factory import LLMConfigError, build_client
from src.modules.llm.google_ai_studio_llm import GoogleAIStudioLLM
from src.modules.llm.local_llm import LocalLLM
from src.modules.llm.openai_compat_generic_llm import OpenAICompatibleGenericLLM
from src.setup.doctor import _env_var, _key_for, check_keys


class DummyConfig:
    def __init__(self, **kwargs):
        self.google_ai_studio_key = kwargs.get("google_ai_studio_key", "test-google-key")
        self.google_ai_studio_model = kwargs.get("google_ai_studio_model", "gemini-2.0-flash")

        self.openai_compat_key = kwargs.get("openai_compat_key", None)
        self.openai_compat_base_url = kwargs.get("openai_compat_base_url", "http://localhost:8000/v1")
        self.openai_compat_model = kwargs.get("openai_compat_model", "gpt-4o-mini")

        self.local_key = kwargs.get("local_key", None)
        self.local_base_url = kwargs.get("local_base_url", "http://localhost:11434/v1")
        self.local_model = kwargs.get("local_model", "llama3.2")

        self.claude_key = kwargs.get("claude_key", "test-claude-key")
        self.claude_model = kwargs.get("claude_model", "claude-3-7-sonnet-latest")

        self.anthropic_compat_key = kwargs.get("anthropic_compat_key", None)
        self.anthropic_compat_base_url = kwargs.get("anthropic_compat_base_url", "https://api.anthropic.com/v1")
        self.anthropic_compat_model = kwargs.get("anthropic_compat_model", "claude-3-7-sonnet-latest")

        self.models = kwargs.get("models", {})


# --- 1. Factory Instantiation and Aliases ---


@pytest.mark.parametrize(
    ("provider", "expected_cls"),
    [
        ("google_ai_studio", GoogleAIStudioLLM),
        ("google", GoogleAIStudioLLM),
        ("gemini", GoogleAIStudioLLM),
        ("openai_compat", OpenAICompatibleGenericLLM),
        ("openai_compatible", OpenAICompatibleGenericLLM),
        ("local", LocalLLM),
        ("ollama", LocalLLM),
        ("lmstudio", LocalLLM),
        ("claude", ClaudeLLM),
        ("anthropic", ClaudeLLM),
        ("anthropic_compat", AnthropicCompatLLM),
        ("anthropic_compatible", AnthropicCompatLLM),
    ],
)
def test_factory_builds_all_new_providers_and_aliases(provider, expected_cls):
    cfg = DummyConfig()
    client = build_client(provider, "test-model", cfg)
    assert isinstance(client, expected_cls)
    assert client.model_name == "test-model"


# --- 2. Key Requirements and Optional Key Allowance ---


def test_google_ai_studio_requires_key():
    cfg = DummyConfig(google_ai_studio_key=None)
    with pytest.raises(LLMConfigError, match="google_ai_studio_key is missing"):
        build_client("google_ai_studio", "gemini-2.0-flash", cfg)


def test_claude_requires_key():
    cfg = DummyConfig(claude_key=None)
    with pytest.raises(LLMConfigError, match="claude_key is missing"):
        build_client("claude", "claude-3-7-sonnet-latest", cfg)


@pytest.mark.parametrize(
    "provider",
    ["local", "ollama", "lmstudio", "openai_compat", "openai_compatible", "anthropic_compat", "anthropic_compatible"],
)
def test_optional_key_providers_allow_missing_key(provider):
    cfg = DummyConfig(local_key=None, openai_compat_key=None, anthropic_compat_key=None)
    client = build_client(provider, "test-model", cfg)
    assert client is not None


# --- 3. Dynamic Config Reload ---


def test_google_ai_studio_reload_config():
    cfg = DummyConfig(google_ai_studio_key="key1", google_ai_studio_model="gemini-2.0-flash")
    client = build_client("google_ai_studio", "gemini-2.0-flash", cfg)
    assert client.api_key == "key1"

    cfg.google_ai_studio_key = "key2"
    cfg.google_ai_studio_model = "gemini-1.5-pro"
    client.reload_config(cfg)

    assert client.api_key == "key2"
    assert client.model_name == "gemini-1.5-pro"


def test_local_llm_reload_config():
    cfg = DummyConfig(local_base_url="http://localhost:11434/v1", local_model="llama3.2")
    client = build_client("local", "llama3.2", cfg)
    assert client.base_url == "http://localhost:11434/v1"

    cfg.local_base_url = "http://localhost:1234/v1"
    cfg.local_model = "mistral"
    client.reload_config(cfg)

    assert client.base_url == "http://localhost:1234/v1"
    assert client.model_name == "mistral"


def test_anthropic_compat_reload_config():
    cfg = DummyConfig(
        anthropic_compat_base_url="https://api.anthropic.com/v1",
        anthropic_compat_key="key-a",
        anthropic_compat_model="claude-3-5-sonnet",
    )
    client = build_client("anthropic_compat", "claude-3-5-sonnet", cfg)
    assert client.api_key == "key-a"

    cfg.anthropic_compat_base_url = "https://proxy.example.com/v1"
    cfg.anthropic_compat_key = "key-b"
    cfg.anthropic_compat_model = "claude-3-7-sonnet"
    client.reload_config(cfg)

    assert client.api_key == "key-b"
    assert client.base_url == "https://proxy.example.com/v1"
    assert client.model_name == "claude-3-7-sonnet"


# --- 4. Anthropic Messages API Conversion Helpers ---


def test_anthropic_tool_schema_conversion():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "speak",
                "description": "Speak text",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        }
    ]
    converted = _convert_tools(tools)
    assert len(converted) == 1
    assert converted[0]["name"] == "speak"
    assert converted[0]["description"] == "Speak text"
    assert "input_schema" in converted[0]
    assert converted[0]["input_schema"]["properties"]["text"]["type"] == "string"


def test_clean_schema_removes_unsupported_keys():
    raw_schema = {
        "type": "object",
        "title": "UnwantedTitle",
        "description": "ValidDescription",
        "default": "UnwantedDefault",
        "properties": {
            "query": {
                "type": "string",
                "title": "QueryTitle",
                "examples": ["sample"],
            }
        },
    }
    cleaned = _clean_schema(raw_schema)
    assert "title" not in cleaned
    assert "default" not in cleaned
    assert "title" not in cleaned["properties"]["query"]
    assert "examples" not in cleaned["properties"]["query"]
    assert cleaned["description"] == "ValidDescription"


def test_anthropic_message_conversion():
    messages = [
        {"role": "system", "content": "You are Bea."},
        {"role": "user", "content": "Hello"},
        {
            "role": "assistant",
            "content": "Thinking...",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "speak", "arguments": '{"text": "hi"}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_123",
            "content": "spoken",
        },
    ]
    system, converted = _convert_messages(messages)
    assert system == "You are Bea."
    assert len(converted) == 3

    assert converted[0]["role"] == "user"
    assert converted[0]["content"] == "Hello"

    assert converted[1]["role"] == "assistant"
    # Assistant has text block and tool_use block
    assert any(b.get("type") == "tool_use" and b.get("name") == "speak" for b in converted[1]["content"])

    # Tool response mapped to user role tool_result
    assert converted[2]["role"] == "user"
    assert converted[2]["content"][0]["type"] == "tool_result"
    assert converted[2]["content"][0]["tool_use_id"] == "call_123"


def test_anthropic_message_coalescing():
    messages = [
        {"role": "user", "content": "Part 1"},
        {"role": "user", "content": "Part 2"},
    ]
    system, converted = _convert_messages(messages)
    assert len(converted) == 1
    assert converted[0]["role"] == "user"
    assert "Part 1\nPart 2" in converted[0]["content"]


# --- 5. CLI Argument Parsing and Overrides ---


def test_cli_overrides_for_new_providers():
    argv = [
        "--llm-provider", "google_ai_studio",
        "--google-ai-studio-key", "my-gemini-key",
        "--google-ai-studio-model", "gemini-2.5-flash",
        "--local-base-url", "http://127.0.0.1:11434/v1",
        "--local-model", "qwen2.5",
        "--openai-compat-base-url", "http://127.0.0.1:8000/v1",
        "--claude-key", "my-claude-key",
        "--anthropic-compat-base-url", "https://proxy.ai/v1",
    ]
    args = parse_args(argv)
    config = BrainConfig()
    apply_cli_overrides(config, args)

    assert config.llm_provider == "google_ai_studio"
    assert config.google_ai_studio_key == "my-gemini-key"
    assert config.google_ai_studio_model == "gemini-2.5-flash"
    assert config.local_base_url == "http://127.0.0.1:11434/v1"
    assert config.local_model == "qwen2.5"
    assert config.openai_compat_base_url == "http://127.0.0.1:8000/v1"
    assert config.claude_key == "my-claude-key"
    assert config.anthropic_compat_base_url == "https://proxy.ai/v1"


# --- 6. Doctor Check and Key Resolution ---


def test_doctor_env_vars():
    assert _env_var("google_ai_studio") == "GOOGLE_AI_STUDIO_KEY"
    assert _env_var("openai_compat") == "OPENAI_COMPAT_API_KEY"
    assert _env_var("local") == "LOCAL_API_KEY"
    assert _env_var("claude") == "ANTHROPIC_API_KEY"
    assert _env_var("anthropic_compat") == "ANTHROPIC_COMPAT_API_KEY"


def test_doctor_key_for_fallbacks(monkeypatch):
    config = BrainConfig()
    config.google_ai_studio_key = None
    config.claude_key = None

    monkeypatch.setenv("GEMINI_API_KEY", "fallback-gemini-key")
    assert _key_for(config, "google_ai_studio") == "fallback-gemini-key"

    monkeypatch.setenv("CLAUDE_API_KEY", "fallback-claude-key")
    assert _key_for(config, "claude") == "fallback-claude-key"

    # Local LLMs default to "local" if no key is set
    assert _key_for(config, "local") == "local"


@pytest.mark.asyncio
async def test_doctor_skips_optional_keys():
    config = BrainConfig()
    config.llm_provider = "local"
    config.models = {"mind": ["local:llama3.2"], "background": []}
    config.local_key = None
    config.stt_provider = "faster_whisper"

    finding = await check_keys(config)
    assert finding.ok is True
