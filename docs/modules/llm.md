# LLM Modules

← [Back to README](../../README.md) | [Architecture](../architecture.md)

---

## Overview

The LLM layer is provider-agnostic and **tool-aware**. The core primitive is
`LLMClient.complete()` (`src/core/agent/llm_client.py`), which every agent in
the app (the conversational brain, the Minecraft agent) drives through the
shared harness in `src/core/agent/`.

Providers are built by a single factory (`src/modules/llm/factory.py`) based on
the `--llm-provider` flag or `config.json`.

```
src/core/agent/
├── llm_client.py     LLMClient: async complete(messages, tools) -> AssistantMessage
├── tools.py          Tool, ToolRegistry
├── runner.py         AgentRunner: the think -> act -> observe loop
└── types.py          AssistantMessage, ToolCall

src/modules/llm/
├── openai_compat.py  OpenAICompatibleClient — shared base (complete + legacy helpers)
├── openai_llm.py     OpenAI
├── groq_llm.py       Groq (fast inference)
├── openrouter_llm.py OpenRouter (one endpoint, any model)
└── factory.py        build_llm(config, stt) -> LLMClient
```

All three providers speak the OpenAI Chat API, so they share
`OpenAICompatibleClient`; each subclass only sets a base URL / API key and
implements `reload_config`.

---

## Interface Contract

```python
class LLMClient(ABC):
    async def complete(messages, tools=None, response_format=None) -> AssistantMessage
    def reload_config(config) -> None
```

`AssistantMessage` has `.content` (text) and `.tool_calls` (list of `ToolCall`).
When the model wants to act it returns tool calls; when it answers it returns
content with no tool calls.

For backward compatibility, `OpenAICompatibleClient` also exposes the legacy
helpers `chat()`, `chat_audio()`, and `generate_json()` (used by the memory and
monologue skills), implemented on top of the same client.

---

## Response Format (conversational turns)

Bea's spoken replies stay in the existing JSON shape:

```json
{ "mood": "normal", "message": "The spoken response text." }
```

`src/utils/llm_utils.parse_llm_json()` extracts it robustly (fenced blocks, raw
JSON, first balanced `{ }`); on failure mood defaults to `normal` and the raw
text becomes the message. Tools are used for **actions**, not for the final
spoken answer, so a plain chat turn costs no extra tool-schema tokens.

---

## Providers

| Provider | Class | Config model key | Env var | Notes |
|---|---|---|---|---|
| OpenRouter | `OpenRouterLLM` | `openrouter_model` | `OPENROUTER_API_KEY` | Default. Routes to any model (`openai/...`, `anthropic/...`, `google/...`). |
| OpenAI | `OpenAILLM` | `openai_model` | `OPENAI_API_KEY` | Also used by the Memory skill embedding/diary. |
| Groq | `GroqLLM` | `groq_model` | `GROQ_API_KEY` | Fast inference; same key powers Groq STT. |

`chat_audio()` transcribes via the injected STT interface, then calls the text
path.

---

## Hot Reload

Every provider implements `reload_config(config)`: re-initializes the client if
the key changed, updates the model name in place. No restart needed.

---

## Adding a New Provider

If it speaks the OpenAI Chat API, it's ~15 lines:

```python
class MyLLM(OpenAICompatibleClient):
    def __init__(self, api_key, model_name, stt_interface=None):
        self.api_key = api_key
        super().__init__(OpenAI(api_key=api_key, base_url="..."), model_name, stt_interface)

    def reload_config(self, config):
        ...
```

Then register it in `_PROVIDERS` / the builder in `factory.py` and add it to the
`--llm-provider` choices in `src/cli.py`.
