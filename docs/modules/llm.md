# LLM Modules

← [Back to README](../../README.md) | [Architecture](../architecture.md)

---

## Overview

The LLM layer is provider-agnostic and **tool-aware**. The core primitive is
`LLMClient` (`src/core/agent/llm_client.py`); every model call in the app goes
through it.

Callers ask for a **role**, not for a model. The registry hands back a client —
usually a pool.

```
src/core/agent/
├── llm_client.py   LLMClient: complete(), complete_json(), reload_config()
├── registry.py     ModelRegistry + RotatingClient — the role pools
├── types.py        AssistantMessage, ToolCall, Usage
├── tools.py        Tool, ToolRegistry
├── messages.py     assistant/tool message shaping
└── runner.py       AgentRunner: the think → act → observe loop

src/modules/llm/
├── openai_compat.py  OpenAICompatibleClient — the shared base
├── openai_llm.py     OpenAI
├── groq_llm.py       Groq
├── openrouter_llm.py OpenRouter
└── factory.py        build_client(provider, model, config, stt)
```

All three providers speak the OpenAI Chat API, so they share
`OpenAICompatibleClient`; a subclass only sets a base URL and key and implements
`reload_config`.

---

## Roles, not models

```json
"models": {
  "mind":       ["openrouter:deepseek/deepseek-v4-flash", "groq:openai/gpt-oss-120b"],
  "background": ["openrouter:google/gemma-4-31b-it:free", "groq:openai/gpt-oss-20b"]
}
```

| Role | Who uses it | What it needs |
|---|---|---|
| `mind` | the consciousness, scoped conversation turns | **must support tool calling** |
| `background` | diary, dreamer, profiler, summaries, the Minecraft body | cheap and slow is fine |

A spec is `"provider:model"`, split on the **first** `:` so OpenRouter ids keep
their `/` and their `:free` suffix.

⚠️ Every model in the `mind` pool must support tool calls. Bea speaks *only*
through the `speak` tool, so a model without tool use would never say anything
at all. A provider rejecting tools is logged as a configuration mistake, not a
retryable hiccup — it will fail identically forever.

The `background` split exists so a dozen sessions being dreamed cannot compete
with the part of her that talks to people, for either latency or rate limit.

---

## Pools: rotation and fallback

`ModelRegistry.get(role)` builds one client per spec and, when there is more
than one, wraps them in a `RotatingClient`:

- **rotation** — each call starts at the next client in the pool, spreading load
  across providers and rate limits. The index advances on *dispatch*, not on
  success, which is what actually spreads it.
- **fallback** — on failure it walks the rest of the pool before giving up.
  `ModelPoolError` is raised only when every model failed.

A single 429 from one provider therefore does not make Bea mute.

If `models` is missing or a role's list is empty, the registry falls back to the
pre-pool `llm_provider` + `<provider>_model` fields, so old configs keep working.

---

## Interface

```python
class LLMClient(ABC):
    async def complete(messages, tools=None, response_format=None) -> AssistantMessage
    async def complete_json(user_input, system_prompt=None, history=None) -> dict | list
    def reload_config(config) -> None
```

`AssistantMessage` carries `.content`, `.tool_calls`, `.usage` and `.model`;
`.is_final` is simply "no tool calls".

`complete_json` is awaitable because background work runs inside the same event
loop as the consciousness. A blocking call there freezes the loop for its whole
duration: with a dozen sessions to dream, Bea goes deaf for minutes.

---

## How a turn ends

A turn ends when the model calls `speak(mood, message)` or `stay_silent()`.
Anything it writes as plain text is private thinking that nobody hears, which is
what makes her inner monologue possible.

`src/utils/llm_utils.parse_llm_json()` extracts JSON robustly (fenced blocks,
raw JSON, the first balanced `{ }`) for the JSON-mode background jobs — the
diary, the dreamer and the profiler.

Everything a model produces is passed through
[`clean_model_output()`](../../src/utils/sanitize.py) before it reaches the TTS:
cheap models leak `<think>` blocks, channel markers and `<|...|>` tokens, and
unfiltered Bea pronounces them out loud.

---

## Cost, per turn

`Usage` rides on the `AssistantMessage`, so a turn adds up what it spent without
threading a counter through every layer. The consciousness publishes it as a
`system`/`cost` event — the point of the attention gate is spending fewer calls,
and that cannot be tuned unseen.

---

## Providers

| Provider | Class | Key field | Env var |
|---|---|---|---|
| OpenRouter | `OpenRouterLLM` | `openrouter_key` | `OPENROUTER_API_KEY` |
| OpenAI | `OpenAILLM` | `openai_key` | `OPENAI_API_KEY` |
| Groq | `GroqLLM` | `groq_key` | `GROQ_API_KEY` |

Keys come from the environment first; `config.json` only fills a variable that
is not set. `GET /config` never returns them.

---

## Hot reload

`ModelRegistry.reload_config()` reloads every live client and then **drops the
cache**, so a changed pool or key takes effect on the next `get(role)` with no
restart.

---

## Adding a provider

If it speaks the OpenAI Chat API, it is about fifteen lines:

```python
class MyLLM(OpenAICompatibleClient):
    def __init__(self, api_key, model_name, stt_interface=None):
        self.api_key = api_key
        super().__init__(OpenAI(api_key=api_key, base_url="..."), model_name, stt_interface)

    def reload_config(self, config):
        ...
```

Then add it to `_PROVIDERS` and the branch in `factory.build_client()`, and to
the `--llm-provider` choices in `src/cli.py`.
