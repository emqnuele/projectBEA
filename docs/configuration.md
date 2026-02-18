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

  "llm_provider": "openai",
  "gemini_model": "gemini-3-flash-preview",
  "glm_model": "glm-4.7",
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
      "embedding_model": "text-embedding-3-small"
    },
    "minecraft": {
      "enabled": false,
      "server_url": "ws://localhost:8080",
      "max_history_events": 20,
      "debug_mode": true,
      "auto_chat_thoughts": false,
      "auto_speak_thoughts": false,
      "mc_openai_model": "gpt-4o-mini",
      "mc_openai_key": "",
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
| `llm_provider` | `"openai"` | Active LLM: `gemini`, `openai`, `groq`, `glm` |

### LLM Models

| Field | Default |
|---|---|
| `gemini_model` | `"gemini-3-flash-preview"` |
| `glm_model` | `"glm-4.7"` |
| `openai_model` | `"gpt-5"` |
| `groq_model` | `"openai/gpt-oss-20b"` |

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

### Minecraft Skill Config Fields

| Key | Default | Description |
|---|---|---|
| `server_url` | `"ws://localhost:8080"` | WebSocket URL of the Minecraft mod |
| `max_history_events` | `20` | How many past game events the agent keeps in context |
| `debug_mode` | `true` | Enables verbose agent logging |
| `auto_speak_thoughts` | `false` | TTS-speak agent thoughts as Bea's commentary |
| `auto_chat_thoughts` | `false` | Also send thoughts as in-game chat messages |
| `mc_openai_model` | `"gpt-4o-mini"` | Model used by the Minecraft agent |
| `mc_openai_key` | *(env: `OPENAI_API_KEY`)* | Optional separate OpenAI key for the MC agent. Falls back to the main `OPENAI_API_KEY` if empty. |
| `system_prompt_path` | `"data/prompts/minecraft.txt"` | Custom system prompt for the Minecraft context |

---

## Environment Variables

| Variable | Used by |
|---|---|
| `OPENAI_API_KEY` | OpenAI LLM, Memory skill embedding |
| `GEMINI_API_KEY` | Gemini LLM |
| `GROQ_API_KEY` | Groq LLM, Groq STT |
| `GLM_API_KEY` | GLM LLM |
| `ORPHEUS_API_KEY` | Orpheus TTS — API key |
| `ORPHEUS_ENDPOINT` | Orpheus TTS — Baseten endpoint URL (treated as secret: never saved to `config.json`) |
| `DISCORD_TOKEN` | Discord skill bot |

---

## CLI Arguments

All arguments mirror `config.json` fields. Most are optional (fall back to config/defaults).

```
python main.py [OPTIONS]

  --web                    Start the web dashboard (FastAPI + React)
  --system-file PATH       Path to the persona system prompt
  --llm-provider CHOICE    gemini | openai | groq | glm
  --gemini-key KEY
  --gemini-model MODEL
  --openai-key KEY
  --openai-model MODEL
  --groq-key KEY
  --groq-model MODEL
  --glm-key KEY
  --glm-model MODEL
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

> **Security note (`GET /config`):** The `GET /config` endpoint returns the full in-memory `BrainConfig`, including all secret API key fields (`gemini_key`, `openai_key`, `groq_key`, `orpheus_endpoint`, etc.), with **no redaction**. This is asymmetric with `save_to_file()`, which strips secrets before writing to disk. Do not expose the web API over a public network without authentication. See [Web API → `GET /config`](web/api.md) for details.

---

## Config Loading Side Effects

### `obs_image_source` migration

During `load_from_file()`, if `config.json` contains the old field name `obs_image_source` (used in earlier versions), it is automatically renamed to `obs_avatar_source`. This migration is silent — no message is printed and the old key is removed from the in-memory dict before processing.

### `save_to_file()` — nested secret stripping

`save_to_file()` removes all top-level secret keys (`*_key` fields) from the saved JSON. In addition, it separately strips `skills.minecraft.mc_openai_key` from the nested skills block. Although `mc_openai_key` is listed in `SECRET_KEYS`, the top-level scan operates on the flattened `BrainConfig` fields — it won't find a key that is nested inside `skills.minecraft`. The explicit extra strip covers that gap. The combined effect is that neither top-level nor nested secret keys are ever persisted to `config.json`.

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
