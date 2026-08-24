# STT Module

← [Back to README](../../README.md) | [Architecture](../architecture.md)

---

## Overview

Transcribes an audio file to text. It is used in three places, all of them
entrypoints where audio arrives already decoded as WAV:

| Caller | Endpoint | What happens next |
|---|---|---|
| dashboard mic | `POST /audio` | a `VOICE` perception, and the caller waits for her reply |
| Discord voice | `POST /discord/audio` | same, but the reply comes back as WAV bytes for the bot |
| overheard speech | `POST /voice/transcript` | a perception, no waiting — the gate decides |

```
src/modules/STT/
├── groq_stt.py        Groq Whisper
└── openrouter_stt.py  OpenRouter Whisper
```

The provider is chosen by `stt_provider` in config and instantiated in
`src/cli.py`. It is optional: with `stt_provider` set to anything else, `stt` is
`None` and the audio paths degrade rather than crash.

---

## Interface

```python
class STTInterface(ABC):
    def transcribe(audio_path: str, language: str = "en") -> str
    def reload_config(config: BrainConfig) -> None
```

Returns the transcript, or an empty string on failure. Both methods are
`@abstractmethod` — omitting either raises `TypeError` at instantiation.

`language` falls back to `config.language`, which measurably improves accuracy
on non-English speech.

---

## Groq (`groq_stt.py`)

Groq's Whisper endpoint. Fast enough for near-realtime.

- **Config:** `stt_provider: "groq"`, `stt_model` (default `whisper-large-v3-turbo`)
- **Key:** `GROQ_API_KEY` env → `config.json` → `None`

---

## OpenRouter (`openrouter_stt.py`)

The same Whisper models through OpenRouter, useful when you already have a key
there and would rather not add a Groq account.

- **Config:** `stt_provider: "openrouter"`, `stt_model`
- **Key:** `OPENROUTER_API_KEY`

Model ids are namespaced here, so a bare `whisper-large-v3-turbo` is rewritten
to `openai/whisper-large-v3-turbo` on both load and hot reload — an id copied
from the Groq config keeps working.

---

## The Discord path

The bot decodes Opus to PCM in Node (`prism-media`) and posts **WAV files**.
Python never handles raw Opus.

Each chunk is transcribed and deposited on the perception bus as its own
`VOICE` perception. The [bus](../architecture.md#the-consciousness-loop)
coalesces a burst into a single batch, and the attention gate decides what
deserves a reasoning cycle — so two people talking at once become one batch, one
turn, one answer.

---

## Hot reload

`reload_config()` updates the model and re-creates the client if the key
changed. Switching `stt_provider` itself needs a restart — the object type
changes.

[Discord Skill →](../skills/discord.md)
