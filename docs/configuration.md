# Configuration Reference

← [Back to README](../README.md) | [Setup](setup.md)

---

## Where a value comes from

Three sources, merged at startup:

| Field type | Priority, highest first |
|---|---|
| **secrets** (`*_key`, `orpheus_endpoint`, skill tokens) | CLI arg → environment variable → `config.json` → `None` |
| **everything else** | CLI arg → `config.json` → dataclass default |

Secrets are the important row. **The environment always wins**: if the variable
is set and non-empty, the `config.json` value is skipped entirely. A value in
`config.json` is only ever a fallback for a variable that is not set.

Secrets are also never written back: `save_to_file()` strips every key in
`SECRET_KEYS` and every nested skill token before writing, and `GET /config`
returns them dropped or masked as `********`. Posting the mask back is ignored,
so editing an unrelated field in the dashboard cannot overwrite a real token
with asterisks.

`config.json` is gitignored. Copy `config.example.json` and edit that.

---

## config.json — full reference

This is `config.example.json` verbatim; it matches the dataclass defaults in
`src/core/config.py` field for field.

```json
{
    "language": "en",
    "soul_path": "data/prompts/soul.md",
    "system_prompt_path": "data/prompts/chat.md",
    "operating_prompt_path": "data/prompts/operating.md",
    "llm_provider": "openrouter",
    "openrouter_model": "deepseek/deepseek-v4-flash",
    "openai_model": "gpt-5",
    "groq_model": "openai/gpt-oss-20b",
    "obs_text_source": "AIText",
    "obs_avatar_source": "BeaPNG",
    "obs_source_type": "image",
    "obs_host": "localhost",
    "obs_port": 4455,
    "obs_password": "",
    "audio_device_id": 0,
    "tts_provider": "edge",
    "tts_voice": "it-IT-IsabellaNeural",
    "tts_pitch": "+13Hz",
    "tts_rate": "+12%",
    "tts_volume": "+33%",
    "orpheus_endpoint": "",
    "orpheus_voice": "zoe",
    "kokoro_model": "kokoro-v0_19.onnx",
    "kokoro_voices_file": "voices.bin",
    "kokoro_voice": "af_bella",
    "kokoro_speed": 1,
    "kokoro_lang": "en-us",
    "avatar_map": {
        "normal": {
            "idle": "",
            "talking": ""
        },
        "angry": {
            "idle": "",
            "talking": ""
        },
        "bored": {
            "idle": "",
            "talking": ""
        },
        "cry": {
            "idle": "",
            "talking": ""
        },
        "ew": {
            "idle": "",
            "talking": ""
        },
        "love": {
            "idle": "",
            "talking": ""
        },
        "shock": {
            "idle": "",
            "talking": ""
        }
    },
    "png_dir": "data/pngs",
    "text_line_width": 40,
    "text_lines": 4,
    "text_font_size": 75,
    "text_min_font_size": 55,
    "text_font_step": 2,
    "typing_delay": 0.03,
    "text_min_duration": 2,
    "skills": {
        "monologue": {
            "enabled": false,
            "prompt_path": "data/prompts/monologue.md"
        },
        "memory": {
            "enabled": true,
            "db_path": "data/bea.db",
            "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "embedding_cache_dir": "data/embeddings_cache",
            "min_similarity": 0.35
        },
        "social_memory": {
            "enabled": true
        },
        "dream": {
            "enabled": true,
            "hour": 4
        },
        "minecraft": {
            "enabled": false,
            "server_url": "ws://127.0.0.1:8080",
            "idle_nudge_seconds": 90,
            "system_prompt_path": "data/prompts/minecraft.md",
            "body_prompt_path": "data/prompts/minecraft_body.md"
        },
        "discord": {
            "enabled": false,
            "api_port": 3030,
            "brain_api_url": "http://127.0.0.1:8000",
            "admin_id": "",
            "interrupt_threshold_ms": 3000
        },
        "telegram": {
            "enabled": false,
            "owner_id": "",
            "allowed_chats": []
        },
        "twitch": {
            "enabled": false,
            "channel": "",
            "nick": ""
        },
        "donations": {
            "enabled": false
        }
    },
    "stt_provider": "groq",
    "stt_model": "whisper-large-v3-turbo",
    "consciousness": {
        "enabled": true,
        "idle_after": 240.0,
        "window": 0.3,
        "burst_steps": 6,
        "history_limit": 30,
        "correlation_timeout": 90.0,
        "conversation_history": 16,
        "conversation_steps": 3,
        "max_coalesced_runs": 3
    },
    "models": {
        "mind": [
            "openrouter:deepseek/deepseek-v4-flash",
            "groq:openai/gpt-oss-120b"
        ],
        "background": [
            "openrouter:google/gemma-4-31b-it:free",
            "groq:openai/gpt-oss-20b"
        ]
    },
    "attention": {
        "enabled": true,
        "cooldown_seconds": 20,
        "interject_threshold": 0.45,
        "quiet_hours": [
            3,
            9
        ],
        "trigger_words": [
            "bea",
            "beatrice"
        ],
        "hot_names": [],
        "self_ids": [],
        "digest_max_lines": 8
    },
    "rhythm": {
        "enabled": true,
        "tick_seconds": 900,
        "spontaneous_enabled": true,
        "spontaneous_probability": 0.15,
        "spontaneous_min_silence": 3600,
        "spontaneous_min_activity": 3
    }
}
```

---

## Core

| Key | Default | Description |
|---|---|---|
| `language` | `"en"` | Passed to the STT for transcription accuracy |
| `soul_path` | `data/prompts/soul.md` | Who she is. Prepended to every context, never edited by the engine |
| `operating_prompt_path` | `data/prompts/operating.md` | How she exists: the `speak` tool, the moods, what she notices |
| `system_prompt_path` | `data/prompts/chat.md` | Deprecated. Only used if the operating manual is missing |
| `llm_provider` | `"openrouter"` | Only used when `models` has no pool for a role |

---

## models — the role pools

```json
"models": {
  "mind":       ["openrouter:deepseek/deepseek-v4-flash", "groq:openai/gpt-oss-120b"],
  "background": ["openrouter:google/gemma-4-31b-it:free", "groq:openai/gpt-oss-20b"]
}
```

A spec is `"provider:model"`, split on the **first** `:` so OpenRouter ids keep
their `/` and their `:free` suffix. Within a pool, calls round-robin to spread
rate limits and fall back down the list on failure.

| Role | Used by | Requirement |
|---|---|---|
| `mind` | the consciousness, scoped conversation turns | **must support tool calling** |
| `background` | diary, dreamer, profiler, summaries, the Minecraft body | anything |

An empty pool falls back to `llm_provider` + `<provider>_model`, so a
pre-pool config keeps working. If a role ends up with no usable client the
engine refuses to start and says which key is missing.

[LLM modules →](modules/llm.md)

---

## consciousness

| Key | Default | Description |
|---|---|---|
| `enabled` | `true` | Off means no mind at all: nothing perceives, nothing answers |
| `idle_after` | `240.0` | Seconds of silence before an IDLE perception. Only applies while the `monologue` skill is on |
| `window` | `0.3` | How long the bus coalesces a burst into one batch |
| `burst_steps` | `6` | Max reasoning steps in one turn |
| `history_limit` | `30` | Rolling context size, in messages |
| `correlation_timeout` | `90.0` | How long an HTTP caller waits for her reply before giving up |
| `conversation_history` | `16` | Past messages of a channel included in a scoped turn |
| `conversation_steps` | `3` | Max steps in a scoped turn — a reply is not an expedition |
| `max_coalesced_runs` | `3` | Cap on re-runs when messages keep arriving mid-turn |

---

## attention

What wakes the mind, and what she merely notices. [How it works →](architecture.md#attention)

| Key | Default | Description |
|---|---|---|
| `enabled` | `true` | Off means every perception costs a full reasoning cycle |
| `cooldown_seconds` | `20` | She just spoke: let the room breathe. Being addressed bypasses it |
| `interject_threshold` | `0.45` | Score needed to speak up unprompted. ±0.1 of noise is added before comparing |
| `quiet_hours` | `[3, 9]` | She never interjects in this window. Being addressed still gets through |
| `trigger_words` | `["bea", "beatrice"]` | Her names. Whole-word, one typo tolerated. Shared by every platform |
| `hot_names` | `[]` | Other names that pull her into a conversation |
| `self_ids` | `[]` | Her own platform ids, so a reply to her is recognised as addressed |
| `digest_max_lines` | `8` | Cap on the `[WHILE YOU WERE BUSY]` block |

---

## rhythm

A day rather than an event loop.

| Key | Default | Description |
|---|---|---|
| `enabled` | `true` | Runs the slow clock at all |
| `tick_seconds` | `900` | How often the spontaneous check runs |
| `spontaneous_enabled` | `true` | Whether she may open a conversation herself |
| `spontaneous_probability` | `0.15` | Even when eligible, usually she does not |
| `spontaneous_min_silence` | `3600` | She spoke there recently: more is noise, not presence |
| `spontaneous_min_activity` | `3` | Below this the room is dead and she would be talking to nobody |

---

## OBS

| Key | Default | Description |
|---|---|---|
| `obs_host` / `obs_port` | `localhost` / `4455` | obs-websocket 5.x |
| `obs_password` | `""` | Empty if authentication is disabled |
| `obs_avatar_source` | `"BeaPNG"` | Source name for the avatar |
| `obs_source_type` | `"image"` | `image` for PNG, `media` for MP4/GIF/WebM |
| `obs_text_source` | `"AIText"` | Source name for the speech bubble |

If OBS is not running the connection fails with a warning and everything else
continues. [OBS module →](modules/obs.md)

---

## Audio and TTS

| Key | Default | Description |
|---|---|---|
| `audio_device_id` | `0` | Output device index. `python -c "import sounddevice; print(sounddevice.query_devices())"` |
| `tts_provider` | `"edge"` | `edge`, `kokoro` or `orpheus`. **Changing it needs a restart** |
| `tts_voice` / `tts_pitch` / `tts_rate` / `tts_volume` | `en-US-AvaNeural`, `+5Hz`, `+10%`, `+33%` | EdgeTTS |
| `orpheus_voice` | `"zoe"` | Orpheus. Key and endpoint come from the environment |
| `kokoro_model` / `kokoro_voices_file` | `kokoro-v0_19.onnx`, `voices.bin` | Downloaded on first run if missing |
| `kokoro_voice` / `kokoro_speed` / `kokoro_lang` | `af_bella`, `1.0`, `en-us` | Kokoro |

[TTS modules →](modules/tts.md)

---

## STT

| Key | Default | Description |
|---|---|---|
| `stt_provider` | `"groq"` | `groq` or `openrouter`. Anything else disables speech input |
| `stt_model` | `"whisper-large-v3-turbo"` | Rewritten to `openai/whisper-large-v3-turbo` on OpenRouter |

[STT module →](modules/stt.md)

---

## Avatar and the text bubble

`avatar_map` holds one `{idle, talking}` pair per mood: `normal`, `angry`,
`bored`, `cry`, `ew`, `love`, `shock`. Leave a path empty to fall back to
`normal`. `png_dir` (`data/pngs`) is where they live.

| Key | Default | Description |
|---|---|---|
| `text_line_width` | `40` | Characters per line before wrapping |
| `text_lines` | `4` | Visible lines before paginating |
| `text_font_size` | `75` | Starting font size |
| `text_min_font_size` | `55` | Floor when long text is shrunk to fit |
| `text_font_step` | `2` | Shrink step |
| `typing_delay` | `0.03` | Seconds per character |
| `text_min_duration` | `2.0` | Minimum seconds a page stays up |

---

## Skills

Every block lives under `skills.<key>` and carries `enabled`. **The dashboard is
the single source of truth** — Bea can never arm a capability herself.

| Skill | Keys | Page |
|---|---|---|
| `memory` | `db_path`, `embedding_model`, `embedding_cache_dir`, `min_similarity` | [memory](skills/memory.md) |
| `social_memory` | `enabled` only | [social](skills/social.md) |
| `dream` | `hour` | [dream](skills/dream.md) |
| `monologue` | `prompt_path` — the timer is `consciousness.idle_after` | [monologue](skills/monologue.md) |
| `minecraft` | `server_url`, `idle_nudge_seconds`, `system_prompt_path`, `body_prompt_path` | [minecraft](skills/minecraft.md) |
| `discord` | `api_port`, `brain_api_url`, `admin_id`, `interrupt_threshold_ms`, `token` | [discord](skills/discord.md) |
| `telegram` | `owner_id`, `allowed_chats`, `token` | [telegram](skills/telegram.md) |
| `twitch` | `channel`, `nick`, `oauth_token` | [twitch](skills/twitch.md) |
| `donations` | `secret` | [donations](skills/donations.md) |

Trigger words are **not** per-platform: they come from `attention.trigger_words`
everywhere.

---

## Environment variables

| Variable | Used for |
|---|---|
| `OPENROUTER_API_KEY` / `OPENAI_API_KEY` / `GROQ_API_KEY` | LLM providers, and STT for Groq / OpenRouter |
| `ORPHEUS_API_KEY` / `ORPHEUS_ENDPOINT` | Orpheus TTS |
| `DISCORD_TOKEN` | The Discord bot |
| `DISCORD_ADMIN_ID` | Fallback for `skills.discord.admin_id` |
| `TELEGRAM_TOKEN` | The Telegram bot |
| `TWITCH_OAUTH_TOKEN` | Writing in Twitch chat. Reading needs nothing |
| `DONATION_SECRET` | Shared secret on the donation webhook |
| `BEA_ALLOWED_ORIGINS` | Extra CORS origins, comma-separated |
| `LOG_LEVEL` | `DEBUG` for verbose output |

---

## CLI arguments

Every one is an override for this launch only; nothing is written to disk.

```bash
uv run bea --web --llm-provider openrouter --tts-provider kokoro --device-id 22
```

| Argument | Notes |
|---|---|
| `--web` | Serve the dashboard instead of the terminal loop |
| `--host` / `--port` | Default `127.0.0.1:8000`. See below before changing the host |
| `--llm-provider` | `openrouter`, `openai`, `groq`. Only affects the legacy single-model path |
| `--openrouter-key` / `--openrouter-model` | and the same pair for `--openai-*` and `--groq-*` |
| `--stt-provider` / `--stt-model` | `groq` or `openrouter` |
| `--tts-provider` / `--tts-voice` | `edge`, `kokoro`, `orpheus` |
| `--orpheus-key` / `--orpheus-endpoint` / `--orpheus-voice` | |
| `--kokoro-file` / `--kokoro-voices` | |
| `--obs-host` / `--obs-port` / `--obs-password` | |
| `--obs-avatar-source` / `--obs-source-type` / `--obs-text-source` | |
| `--device-id` | Audio output device index |
| `--typing-delay` | Seconds per character in the OBS bubble |
| `--system-file` / `--png-dir` | Prompt file and avatar directory |

> `--tts-provider coqui` is still accepted by the parser but has no
> implementation; it falls through to EdgeTTS.

---

## Hot reload

`POST /config` writes the file and then calls `reload_configuration()`, which
re-reads the soul and the operating manual, drops the model-registry cache, and
reloads the TTS, STT and OBS clients in place.

Two things still need a restart, and the dashboard says so when you save:
`tts_provider` and `stt_provider` — the object type changes.

---

## Startup behaviour

Skills start according to their saved `enabled` value, so a skill left on
connects again on the next launch.

`load_from_file()` renames the legacy key `obs_image_source` to
`obs_avatar_source` silently. Delete the old key from your `config.json` to
avoid ambiguity.

**Network exposure.** The API has no authentication, so the server binds to
`127.0.0.1` unless `--host` says otherwise. Binding to `0.0.0.0` hands anyone on
the network the ability to read the config, drive the brain and post donations.
Put it behind something that authenticates, and set `DONATION_SECRET`.

[Web API →](web/api.md)
