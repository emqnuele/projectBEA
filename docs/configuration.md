# Configuration Reference

← [Back to README](../README.md)

---

## Overview

Configuration is managed via two sources that are merged at startup:

1. **`config.json`** (project root) — persistent settings, edited by the web dashboard or manually.
2. **Environment variables** (`.env` or shell) — secret API keys (only consulted for secret fields).
3. **CLI arguments** — one-shot overrides at launch time.

**Priority (highest → lowest):**

| Field type | Priority order |
|---|---|
| **Non-secret fields** (`language`, `llm_provider`, `obs_host`, etc.) | CLI arg → `config.json` → dataclass default *(no env-var support)* |
| **Secret fields** (`*_key`, `orpheus_endpoint`) | CLI arg → environment variable → `config.json` fallback → `None` |

> **Secret field env var behaviour:** Environment variables **always win** over `config.json` for secret fields. If the env var is set and non-empty, the `config.json` value is silently skipped — even if it is also non-empty. If the env var is not set, a non-empty `config.json` value is used as fallback. Non-secret fields have no env-var integration at all.

---

## config.json — Full Reference

```json
{
  "language": "en",
  "system_prompt_path": "data/prompts/sys-prompt.txt",

  "llm_provider": "openrouter",
  "openrouter_model": "openai/gpt-4o-mini",
  "openai_model": "gpt-5",
  "groq_model": "openai/gpt-oss-20b",

  "obs_avatar_source": "BeaPNG",
  "obs_text_source": "AIText",
  "obs_source_type": "image",
  "obs_host": "localhost",
  "obs_port": 4455,
  "obs_password": "",

  "audio_device_id": 0,

  "tts_provider": "edge",
  "tts_voice": "en-US-AvaNeural",
  "tts_pitch": "+5Hz",
  "tts_rate": "+10%",
  "tts_volume": "+33%",

  "orpheus_voice": "zoe",

  "kokoro_model": "kokoro-v0_19.onnx",
  "kokoro_voices_file": "voices.bin",
  "kokoro_voice": "af_bella",
  "kokoro_speed": 1,
  "kokoro_lang": "en-us",

  "avatar_map": {
    "normal": { "idle": "", "talking": "" },
    "angry":  { "idle": "", "talking": "" },
    "bored":  { "idle": "", "talking": "" },
    "cry":    { "idle": "", "talking": "" },
    "ew":     { "idle": "", "talking": "" },
    "love":   { "idle": "", "talking": "" },
    "shock":  { "idle": "", "talking": "" }
  },
  "png_dir": "data/pngs",

  "text_line_width": 40,
  "text_lines": 4,
  "text_font_size": 75,
  "text_min_font_size": 55,
  "text_font_step": 2,
  "typing_delay": 0.03,
  "text_min_duration": 2,

  "stt_provider": "groq",
  "stt_model": "whisper-large-v3-turbo",

  "skills": {
    "monologue": {
      "enabled": false,
      "interval_seconds": 30,
      "chunk_pause_seconds": 4.0,
      "prompt_path": "data/prompts/monologue.txt"
    },
    "memory": {
      "enabled": true,
      "chroma_path": "data/memory_db",
      "openai_model": "gpt-4o-mini",
      "embedding_model": "openai/text-embedding-3-small"
    },
    "minecraft": {
      "enabled": false,
      "server_url": "ws://localhost:8080",
      "auto_chat_thoughts": false,
      "auto_speak_thoughts": false,
      "system_prompt_path": "data/prompts/minecraft.txt"
    },
    "discord": {
      "enabled": false,
      "token": "",
      "target_channel": "",
      "api_port": 3030,
      "interrupt_threshold_ms": 3000
    }
  }
}
```

---

## Field Descriptions

### Core

| Field | Default | Description |
|---|---|---|
| `language` | `"en"` | Language code passed to the STT transcriber |
| `system_prompt_path` | `"data/prompts/sys-prompt.txt"` | Path to the AI persona system prompt file |
| `llm_provider` | `"openrouter"` | Active LLM: `openrouter`, `openai`, `groq` |

### LLM Models

Two ways to configure models. The **pool** form is preferred.

#### `models` — one pool per role (preferred)

```json
"models": {
  "mind":       ["openrouter:deepseek/deepseek-v4-flash", "groq:openai/gpt-oss-120b"],
  "background": ["openrouter:google/gemma-4-31b-it:free", "groq:openai/gpt-oss-20b"]
}
```

Each entry is `provider:model`, split on the **first** `:` so OpenRouter ids keep
their `/` and their `:free` suffix. Calls round-robin through a pool to spread
rate limits; if one model fails, the next one serves the call — a single 429 no
longer silences Bea.

| Role | Used by | Requirement |
|---|---|---|
| `mind` | the consciousness | **must support tool calling** — Bea speaks only through tools, so a model without it would never say anything |
| `background` | diary, dreamer, summaries | none; a cheap, slow model is the point — it must not compete with the mind |

A model that rejects tool calls is skipped at runtime and logged at `ERROR`:
that is a configuration mistake, not a transient failure.

#### Single-model fallback (legacy)

With `models` empty, the role falls back to `llm_provider` + `<provider>_model`,
so existing configs keep working unchanged.

| Field | Default |
|---|---|
| `openrouter_model` | `"deepseek/deepseek-v4-flash"` |
| `openai_model` | `"gpt-5"` |
| `groq_model` | `"openai/gpt-oss-20b"` |

### Attention

What wakes the mind versus what Bea merely notices. Without this, every
perception costs a model call — with the game connected, one every ten seconds.

```json
"attention": {
  "enabled": true,
  "cooldown_seconds": 20,
  "interject_threshold": 0.45,
  "quiet_hours": [3, 9],
  "trigger_words": ["bea", "beatrice"],
  "hot_names": [],
  "self_ids": [],
  "digest_max_lines": 8
}
```

| Field | Default | Description |
|---|---|---|
| `enabled` | `true` | Off means every perception reasons — expensive, and not human |
| `cooldown_seconds` | `20` | After speaking she lets the room breathe. Being *addressed* overrides it |
| `interject_threshold` | `0.45` | Score needed to speak up unprompted. Lower = chattier |
| `quiet_hours` | `[3, 9]` | She never interjects in this window; being addressed still reaches her |
| `trigger_words` | `["bea", "beatrice"]` | Whole-word match with one-typo tolerance |
| `hot_names` | `[]` | Names that pull her into a conversation she wasn't part of |
| `self_ids` | `[]` | Her own platform ids, so a reply to one of her messages is recognised |
| `digest_max_lines` | `8` | Cap on `[WHILE YOU WERE BUSY]` — peripheral awareness, not a transcript |

Decisions are published as `system` events with `reaction`, `score` and `reason`,
and shown in Brain Activity. Tune the threshold by reading those, not by guessing.

### OBS

| Field | Default | Description |
|---|---|---|
| `obs_avatar_source` | `"BeaPNG"` | OBS source name for the avatar |
| `obs_text_source` | `"AIText"` | OBS source name for the speech bubble text |
| `obs_source_type` | `"image"` | `"image"` for static PNG, `"media"` for video/GIF |
| `obs_host` | `"localhost"` | OBS WebSocket host |
| `obs_port` | `4455` | OBS WebSocket port |
| `obs_password` | `""` | OBS WebSocket password |

### Audio Output

| Field | Default | Description |
|---|---|---|
| `audio_device_id` | `0` | Sounddevice output device ID (see setup guide) |

### TTS

| Field | Default | Description |
|---|---|---|
| `tts_provider` | `"edge"` | TTS engine: `edge`, `kokoro`, `orpheus`, `coqui` (`coqui` is accepted by the CLI parser but has no active implementation — it silently falls back to EdgeTTS) |
| `tts_voice` | `"en-US-AvaNeural"` | Voice name (EdgeTTS format) |
| `tts_pitch` | `"+5Hz"` | Pitch adjustment (EdgeTTS only) |
| `tts_rate` | `"+10%"` | Speed adjustment (EdgeTTS only) |
| `tts_volume` | `"+33%"` | Volume adjustment (EdgeTTS only) |

### Avatar Map

Maps mood names to file paths. Each mood key (`normal`, `angry`, `bored`, `cry`, `ew`, `love`, `shock`) has:
- `idle` — path to the file shown when Bea is not speaking
- `talking` — path to the file shown when Bea is speaking

### Text / Typing Animation

| Field | Default | Description |
|---|---|---|
| `text_line_width` | `40` | Characters per line before wrapping |
| `text_lines` | `4` | Max visible lines in the text bubble |
| `text_font_size` | `75` | Initial font size (px) |
| `text_min_font_size` | `55` | Minimum font size (px) — shrinks if text is long |
| `text_font_step` | `2` | Font size reduction step when shrinking |
| `typing_delay` | `0.03` | Seconds between each typed character |
| `text_min_duration` | `2.0` | Minimum seconds each page of text stays visible |

### STT

| Field | Default |
|---|---|
| `stt_provider` | `"groq"` |
| `stt_model` | `"whisper-large-v3-turbo"` |

### Monologue Skill Config Fields

| Key | Default | Description |
|---|---|---|
| `enabled` | `false` | Toggle the skill |
| `interval_seconds` | `30` | Seconds of global idle time before Bea starts monologuing |
| `chunk_pause_seconds` | `4.0` | Seconds of silence between story chunks before the next chunk is generated |
| `prompt_path` | `"data/prompts/monologue.txt"` | Path to the monologue rules prompt |

### Telegram Skill Config Fields

Runs **in-process** (no subprocess — that is Discord's, and only for voice).

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | UI toggle |
| `owner_id` | `""` | Your Telegram user id, so she knows the owner |
| `allowed_chats` | `[]` | Empty = every chat she is added to; otherwise an allowlist |

The token is read from `TELEGRAM_TOKEN` only, never written to `config.json`,
and masked in `GET /config`.

Incoming messages become scoped conversation turns — one per chat, in parallel
with the live loop — so answering on Telegram never holds up the stage.

### Minecraft Skill Config Fields

| Key | Default | Description |
|---|---|---|
| `server_url` | `"ws://localhost:8080"` | WebSocket URL of the Minecraft mod |
| `auto_speak_thoughts` | `false` | TTS-speak agent thoughts as Bea's commentary |
| `auto_chat_thoughts` | `false` | Also send thoughts as in-game chat messages |
| `system_prompt_path` | `"data/prompts/minecraft.txt"` | Custom system prompt for the Minecraft context |

> The Minecraft agent uses the engine's main `llm_provider` (no dedicated key/model). It drives the mod through native tool calls.

---

## Environment Variables

| Variable | Used by |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter LLM (default provider) |
| `OPENAI_API_KEY` | OpenAI LLM |
| `GROQ_API_KEY` | Groq LLM, Groq STT |
| `ORPHEUS_API_KEY` | Orpheus TTS — API key |
| `ORPHEUS_ENDPOINT` | Orpheus TTS — Baseten endpoint URL (treated as secret: never saved to `config.json`) |
| `DISCORD_TOKEN` | Discord skill bot |
| `TELEGRAM_TOKEN` | Telegram skill bot |
| `BEA_ALLOWED_ORIGINS` | Extra CORS origins for the dashboard (comma-separated) |

---

## CLI Arguments

All arguments mirror `config.json` fields. Most are optional (fall back to config/defaults).

```
uv run bea [OPTIONS]

  --web                    Start the web dashboard (FastAPI + React)
  --host ADDR              Bind address for the dashboard (default: 127.0.0.1)
  --port PORT              Dashboard port (default: 8000)
  --system-file PATH       Path to the persona system prompt
  --llm-provider CHOICE    openrouter | openai | groq
  --openrouter-key KEY
  --openrouter-model MODEL
  --openai-key KEY
  --openai-model MODEL
  --groq-key KEY
  --groq-model MODEL
  --tts-provider CHOICE    edge | kokoro | orpheus | coqui
                           (Note: `coqui` is accepted by the parser but has no
                           active implementation — it silently falls back to EdgeTTS)
  --tts-voice VOICE
  --orpheus-key KEY
  --orpheus-endpoint URL
  --orpheus-voice VOICE
  --kokoro-file PATH
  --kokoro-voices PATH
  --stt-provider CHOICE    groq
  --stt-model MODEL
  --obs-host HOST
  --obs-port PORT
  --obs-password PASS
  --obs-avatar-source NAME
  --obs-source-type CHOICE image | media
  --obs-text-source NAME
  --device-id ID           Audio output device ID
  --typing-delay SECONDS
  --png-dir PATH
```

---

## Hot Reload

After saving new settings via `POST /config` (web API), the brain calls `reload_configuration()` which propagates changes to all modules and skills without restarting.

> **Security note (`GET /config`):** The `GET /config` endpoint returns the full in-memory `BrainConfig`, including all secret API key fields (`openrouter_key`, `openai_key`, `groq_key`, `orpheus_endpoint`, etc.), with **no redaction**. This is asymmetric with `save_to_file()`, which strips secrets before writing to disk. Do not expose the web API over a public network without authentication. See [Web API → `GET /config`](web/api.md) for details.

---

## Config Loading Side Effects

### `obs_image_source` migration

During `load_from_file()`, if `config.json` contains the old field name `obs_image_source` (used in earlier versions), it is automatically renamed to `obs_avatar_source`. This migration is silent — no message is printed and the old key is removed from the in-memory dict before processing.

### Network exposure

No endpoint is authenticated, so the dashboard binds to `127.0.0.1` by default:
anyone who can reach the port has full control of Bea, and `GET /config` used to
return the raw API keys. Exposing it on the LAN is a deliberate opt-in via
`--host 0.0.0.0`, and is logged as a warning.

CORS carries an explicit allowlist (`localhost:8000`, `localhost:5173` and their
`127.0.0.1` forms) instead of a wildcard — with `*`, any page open in the browser
could read the brain's state and drive it. Extra origins go in
`BEA_ALLOWED_ORIGINS` (comma-separated).

`GET /config` returns `BrainConfig.public_dict()`: top-level secrets are removed,
nested tokens are masked as `********`. Posting a masked value back is ignored,
so saving from the UI never overwrites a real token with asterisks.

### `save_to_file()` — nested secret stripping

`save_to_file()` removes all top-level secret keys listed in `SECRET_KEYS` (`openrouter_key`, `openai_key`, `groq_key`, `orpheus_key`, `orpheus_endpoint`) from the saved JSON, so secrets are never persisted to `config.json`.

> **Exception:** Changing `tts_provider` requires a restart because the TTS object is instantiated at boot.

[Web API →](web/api.md)

---

## Startup Behaviour: Skills Are Force-Disabled

> **Important:** Every skill except `memory` is **force-disabled at startup**, regardless of its `enabled` value in `config.json`.

This is intentional — it prevents unintended side effects (Discord joining a channel, Minecraft connecting to a server) on cold starts. Skills must be explicitly enabled at runtime via:
- The **Skills page** in the web dashboard (toggle switch), or
- `POST /skills/{name}/toggle?enable=true` via the API.

The `memory` skill is the only one that starts automatically if `"enabled": true` in config.

> **Dataclass default note:** The `BrainConfig` Python dataclass sets `minecraft.enabled = True` internally. This is overridden to `False` by the force-disable logic in `load_from_file()` before any skill can start. The effective default a user sees at runtime is always `false` for minecraft, matching the `config.json` reference above.

> **Write → overwrite cycle:** `toggle_skill()` (called by `POST /skills/{name}/toggle`) writes `"enabled": true` to `config.json` via `save_to_file()`. However, because `load_from_file()` force-disables all non-memory skills on every cold start, a skill that was enabled at runtime and persisted to disk via the toggle will be back to `false` after the next restart. Skills must be re-enabled explicitly each session (or via the web dashboard Skills page). This is intentional safety behaviour, not a bug.
