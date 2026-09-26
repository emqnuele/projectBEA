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

Every client on an event loop shares one connection pool
(`base._session()`). An idle connection to a provider is kept for
`KEEPALIVE_SECONDS` (90) and addresses are cached for five minutes, so a turn
does not pay dns, tcp and tls before its first token. A kept connection the
provider closed while it sat idle fails before any of the answer exists; that
request is sent once more. A host that cannot be reached is not retried — that
is the pool's failover. Shutdown closes the pool with `close_sessions()`.

A connection the network drops without a word never reports being closed, so
the pool would hand it to the next call, which then waits out
`STREAM_HEADERS_TIMEOUT` for nothing. Every socket therefore has tcp keepalive
on: the kernel probes it after `TCP_KEEPALIVE_IDLE` (10s) idle, every
`TCP_KEEPALIVE_INTERVAL` (5s), and drops it after `TCP_KEEPALIVE_PROBES` (3)
unanswered probes, so a dead idle connection is gone within about 25 seconds
and is never reused. The probes cost nothing on the calls themselves. macOS
names the idle option `TCP_KEEPALIVE`, Linux and Windows `TCP_KEEPIDLE`; an OS
that refuses the tuning still probes on its own schedule.

aiohttp reuses the oldest idle connection first. Each streamed call records
whether it went out on a reused or a new connection, and at debug level how
long the headers took; a stall names which of the two it was.

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
| `background` | diary, dreamer, profiler, the Minecraft body | cheap and slow is fine |

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
- **streaming** — `stream_complete` streams on the first client only, so she
  can start speaking before the answer is finished. Whoever picks up after a
  failure answers whole (`complete`): the first one may already have started a
  line, and the mind drops that line and says the answer that actually arrived.

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

Two of its four numbers are there to make an invisible problem visible:

- **`cached_tokens`** is the part of the prompt the provider recognised. It is
  the only signal that the prompt is still shaped the way caching wants it —
  something volatile moving near the top drives it to zero and nothing else
  about the turn looks different.
- **`reasoning_tokens`** is the part of the answer the model thought rather
  than said (`spoken_tokens` is the rest). A model that ignores the hint to
  stop reasoning looks exactly like a model writing a long answer, and the
  difference is several seconds of silence before she opens her mouth.

**What a provider can cache** is decided by message order, not by this module:
the loop keeps the stable half of the prompt first and the briefing for this
moment *below* the sliding window. Both item-based transports therefore hoist
only the **leading** system messages into `instructions` / `system`; one that
arrives after the conversation has started keeps its place. Collecting them all
would put a block that changes every turn in front of the whole window and
re-bill every token of it.

---

## Providers

The table above is the whole list. Notes per transport:

**Responses** (`responses.py`). The item-based protocol: the leading system
messages travel as `instructions`, tools are flat (`type`, `name`, `description`,
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

**Messages** (`anthropic.py`). The leading system messages become the `system`
parameter and a later one travels as a user turn in place,
assistant tool calls become `tool_use` blocks, `tool` turns become
`tool_result` blocks addressed by `tool_use_id`, and tool schemas are
flattened onto `input_schema`. Auth is `x-api-key`. There is no JSON mode on
this protocol, so JSON turns are prompt plus parse. `max_tokens` is required
by the API and defaults to 4096.

Every model in the `mind` pool must support tool calls, whichever protocol it
speaks — Bea speaks *only* through the `speak` tool.

`models.reasoning` (`off`, `low`, `medium`, `high`, `auto`) is a latency
setting, not a quality one. "Off" means *as little as this endpoint allows*,
and that is not the same request everywhere — writing one provider's spelling
into another's body is how a working model turns into a 400:

| Provider | `off` sends | Why |
|---|---|---|
| OpenRouter | `reasoning: {enabled: false}` | a switch that works on every family it routes to; `effort` is an OpenAI-family scale a DeepSeek or a Qwen ignores |
| OpenAI | `reasoning: {effort: "minimal"}` | gpt-5 has a floor rather than an off |
| Groq | `reasoning: {effort: "low"}` | gpt-oss takes low, medium and high and nothing below |
| Ollama / local | `reasoning_effort: "none"` | it clamps `minimal` to `low`, so `none` is the only real off, and omitting the field auto-enables thinking |
| Any OpenAI-compatible | `reasoning_effort: "minimal"` | the chat-shaped spelling of the same floor |
| Google, Anthropic | nothing | no documented equivalent; both are fast by default |

A model that rejects its hint is retried without it rather than failing — on
the streamed call as well as the ordinary one. Without that the streamed retry
was never attempted: the refused request was paid for, streaming was switched
off for two minutes, and she lost speaking-early for the next forty turns.

### A provider that never starts answering

A streamed call must get its response headers within 30 seconds
(`STREAM_HEADERS_TIMEOUT`). A provider that streams sends them at once, and
keeps the connection alive while it queues, so a silence that long is a
stalled request, not a slow model. The pool it stalled on is set aside first:
its other idle connections are as suspect as the one that stalled, and aiohttp
would hand the oldest of them out next. The request is sent again once on a new
pool, which the calls after it keep using; the old one is closed after
`REQUEST_TIMEOUT`, once every call still running on it has ended one way or the
other. A second stall raises `ProviderStalled`, which the pool fails over on. It is deliberately not a refusal, so no retry without reasoning and no
non-streaming fallback: each of those would wait on the same stalled provider
all over again.

Headers are not an answer, though. OpenRouter can send them early and then
hold the stream open with `: OPENROUTER PROCESSING` comments, so the headers
check alone let a stalled call run for the whole `REQUEST_TIMEOUT`. The mind
loop runs one turn at a time, so she heard nothing for those two minutes. The
stream is therefore watched on its data, and keep-alive comments do not count
as data:

- the first block of the answer must arrive within
  `STREAM_FIRST_BLOCK_BASE` (15s) plus the request size divided by
  `PREFILL_CHARS_PER_SECOND` (40k characters a second), because prefill time
  grows with the prompt. If the first block is late, the request is sent
  again once, like a header stall. Measured on OpenRouter with
  deepseek-v4-flash, cold cache, 4.49 request characters per input token:

  | input tokens | budget | first token |
  | --- | --- | --- |
  | 109,553 | 27.3s | 7.3s |
  | 383,374 | 58.0s | 19.1s, 26.8s |
- after that, no two blocks may be more than `STREAM_IDLE_TIMEOUT` (30s)
  apart. A stall at that point raises `ProviderStalled` and the request is
  **not** sent again: the start of the line may already be in the room, and
  a resend would say it twice.

A model on this machine or network (`localhost`, a private address, `.local`)
is exempt from both checks, since loading one can take longer than that. What still bounds every call
is `REQUEST_TIMEOUT`, 120 seconds for the whole request.

With a single model in the `mind` pool, a stall still costs the turn, but
within about half a minute rather than two. A second model in the pool is
what turns it into a failover.

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
