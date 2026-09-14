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
├── base.py         AsyncLLMClient — sessions, errors, stream assembly, reload
├── responses.py    the Responses API transport (POST {base}/responses)
├── chat.py         the Chat Completions transport (POST {base}/chat/completions)
├── anthropic.py    the Messages transport (POST {base}/messages)
├── providers.py    every provider as one row of data — no subclasses
└── factory.py      build_client(provider, model, config, stt)
```

Eight providers speak three protocols, so there are three transports and no
per-vendor subclasses. A provider is one row in `providers.py`: transport,
base url, env var, default model, whether the key is required. Adding a ninth
that speaks one of the three protocols is one entry there.

| Provider | Transport | Base URL | Key | Default model |
|---|---|---|---|---|
| OpenRouter | responses | `openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | `deepseek/deepseek-v4-flash` |
| OpenAI | responses | `api.openai.com/v1` | `OPENAI_API_KEY` | `gpt-5` |
| Groq | responses | `api.groq.com/openai/v1` | `GROQ_API_KEY` | `openai/gpt-oss-120b` |
| Google AI Studio | chat | `generativelanguage…/v1beta/openai` | `GOOGLE_API_KEY` | `gemini-3.8-flash` |
| Claude | messages | `api.anthropic.com/v1` | `ANTHROPIC_API_KEY` | `claude-sonnet-5` |
| Custom OpenAI | chat, or responses via `openai_compat_api` | yours | optional | — |
| Custom Anthropic | messages | yours | optional | — |
| Local (Ollama / LM Studio) | chat | `localhost:11434/v1` | none | `qwen3:8b` |

All three transports are natively async over `aiohttp`: no thread pools, no
sync SDKs. Every network error raises with the status and the provider's own
body in the message, which is what the pool's failover reads.

Keys come from the environment first; `config.json` only fills a variable that
is not set. `GET /config` never returns them.

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
| `mind` | the consciousness | **must support tool calling** |
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
    async def complete_stream(messages, tools=None) -> AsyncGenerator[str | ToolCall, None]
    async def complete_json(user_input, system_prompt=None, history=None) -> dict | list
    def reload_config(config) -> None
```

`AssistantMessage` carries `.content`, `.tool_calls`, `.usage` and `.model`;
`.is_final` is simply "no tool calls".

`complete_stream` returns an async generator yielding partial text blocks (for inner monologue or speech) or complete `ToolCall`s. The consciousness loop uses streaming to start Voice Synthesis (TTS) while the LLM is still writing, drastically reducing latency.

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

The table above is the whole list. Notes per transport:

**Responses** (`responses.py`). The item-based protocol: the system prompt
travels as `instructions`, tools are flat (`type`, `name`, `description`,
`parameters` — no nested `function` key), tool results come back as
`function_call_output` items linked by `call_id`. Every call sends the full
history and `store: false`: nothing is kept server-side, which is both a
privacy choice and a requirement on endpoints that reject stored state.
Streaming reads the semantic events (`output_text.delta`,
`function_call_arguments.delta`, `completed`). JSON mode uses `text.format`,
falling back to a plain prompt plus parsing when an endpoint refuses it.
`reasoning: {effort}` carries the latency setting; a model that rejects it is
retried without it rather than failing.

**Chat Completions** (`chat.py`). The industry-standard protocol every
compatible endpoint speaks. Messages and tools travel unchanged; `tool_choice`
is skipped per provider where the endpoint rejects it (Ollama documents tools
but not `tool_choice`). JSON mode uses `response_format` with the same
fallback. Google AI Studio is reached through Gemini's OpenAI-compatible
endpoint, which documents chat completions and nothing else.

**Messages** (`anthropic.py`). System messages become the `system` parameter,
assistant tool calls become `tool_use` blocks, `tool` turns become
`tool_result` blocks addressed by `tool_use_id`, and tool schemas are
flattened onto `input_schema`. Auth is `x-api-key`. There is no JSON mode on
this protocol, so JSON turns are prompt plus parse. `max_tokens` is required
by the API and defaults to 4096.

Every model in the `mind` pool must support tool calls, whichever protocol it
speaks — Bea speaks *only* through the `speak` tool.

`models.reasoning` (`off`, `low`, `medium`, `high`, `auto`) is a latency
setting, not a quality one: it translates per provider to the documented
minimum — `reasoning.effort: minimal` on Responses, `reasoning_effort: none`
on local runners (Ollama clamps `minimal` to `low`, so `none` is the only
real off), nothing at all where no equivalent exists (Gemini's thinking scale
has no shared floor, Anthropic thinking is opt-in and off by default). A
model that rejects its hint is retried without it rather than failing.

---

## Hot reload

`ModelRegistry.reload_config()` reloads every live client and then **drops the
cache**, so a changed pool or key takes effect on the next `get(role)` with no
restart.

---

## Adding a provider

If it speaks one of the three protocols, it is one row in `providers.py`:

```python
"mycloud": Provider(
    id="mycloud", transport=CHAT, base_url="https://mycloud.example/v1",
    key_field="mycloud_key", env_var="MYCLOUD_API_KEY",
    model_field="mycloud_model", default_model="my-model", needs_key=True),
```

plus the config fields, the CLI flags and the wizard entry — the factory,
the doctor and the dashboard read the same table, so they follow without
further branches. A genuinely new protocol means a new transport next to the
three: map its payloads onto `build_body` / `parse_message` / `iter_events`
and the pools, the streaming, the JSON turns and the reloads come for free.
