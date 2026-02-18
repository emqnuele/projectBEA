# STT Module

← [Back to README](../../README.md) | [Architecture](../architecture.md)

---

## Overview

The STT (Speech-to-Text) module transcribes audio files to text. It is used in two places:

1. **Web API** — `POST /audio` accepts a WAV file upload from the web dashboard.
2. **Discord Voice** — `POST /discord/audio` receives real-time Opus audio from the Discord bot.

```
src/modules/STT/
└── groq_stt.py    Groq Whisper transcription
```

---

## Interface Contract

```python
class STTInterface(ABC):
    def transcribe(audio_path: str, language: str = "en") -> str
    def reload_config(config: BrainConfig) -> None
```

Returns the transcribed text string, or an empty string on failure.

> **Important:** `reload_config(config)` is an `@abstractmethod` — any custom STT implementation that omits it will raise `TypeError` at instantiation time.

---

## Groq STT (`groq_stt.py`)

**API:** Groq Audio Transcriptions (Whisper)  
**Config keys:** `stt_provider`, `stt_model`  
**Env var:** `GROQ_API_KEY`

Uses Groq's ultra-fast Whisper inference endpoint. The default model `whisper-large-v3-turbo` offers near-realtime transcription with high accuracy.

**Language:** Reads `config.language` (e.g. `"en"`, `"it"`) and passes it to the Whisper API for better accuracy on non-English speech.

```python
stt = GroqSTT(config)
text = stt.transcribe("path/to/audio.wav")
# → "Hello, how are you?"
```

**Key priority:** `GROQ_API_KEY` env var → `config.json` fallback → `None`.

---

## Audio Flow (Discord)

The Discord bot’s `VoiceManager.js` streams live Discord Opus audio, decodes it with `prism-media` (all in Node.js), and sends chunked **WAV files** to `POST /discord/audio`. The Python side never handles raw Opus: it only ever receives a decoded WAV file. Python transcribes each chunk, aggregates transcript buffers across users in the same channel within a 300 ms collection window, and generates a single response after a configurable silence threshold.

[Discord Skill →](../skills/discord.md)
