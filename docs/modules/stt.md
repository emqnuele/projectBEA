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
├── faster_whisper_stt.py  Whisper on this machine
├── groq_stt.py            Groq Whisper
└── openrouter_stt.py      OpenRouter Whisper
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

`language` falls back to `config.language`, resolved through
[`src/core/language.py`](../languages.md) before it reaches any provider: `jp`,
`it-IT` and `Italiano` all mean the same thing on all three, and `auto` becomes
a missing field rather than a literal.

A pin is only worth setting when the language is known in advance. A wrong one
is worse than none: whisper transcribes *into* the language it was told, so
Italian pinned to `ja` comes back as Japanese and Italian pinned to `en` comes
back as English. No error is raised, so `build_stt()` logs the effective
language at startup (`src/modules/STT/factory.py`):

```
STT backend: faster_whisper, listening in Italian (it)
STT backend: faster_whisper, listening in whatever language it hears
```

The default is `auto`. Turns shorter than `MIN_DETECT_SECONDS` reuse the last
reliable detection — see [Languages](../languages.md#short-turns).

---

## Local Whisper (`faster_whisper_stt.py`)

Whisper through [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
running on the machine she runs on. No key, no account, no per-minute bill, and
the audio never leaves the room — which is the whole reason to prefer it for a
Discord call with people who did not agree to be sent anywhere.

- **Config:** `stt_provider: "faster_whisper"`, `stt_model` (default `small`)
- **Key:** none

| Field | Default | What it does |
|---|---|---|
| `faster_whisper_device` | `"auto"` | `auto`, `cpu` or `cuda`. Auto takes the GPU when there is one |
| `faster_whisper_compute_type` | `"auto"` | Auto is `int8` on a CPU and `float16` on a GPU. `int8_float16` and `float32` also work |
| `faster_whisper_download_root` | `"data/models/whisper"` | Where the weights are cached. Gitignored |
| `faster_whisper_vad` | `true` | Drops silence before transcribing. Whisper invents words for silence, so leave it on |

The weights are downloaded on first use, not at install time:

| `stt_model` | On disk | Notes |
|---|---|---|
| `tiny` | ~75 MB | Instant, and it will mishear you |
| `base` | ~145 MB | Usable on an old laptop |
| `small` | ~480 MB | The default, and the balance most people want |
| `large-v3-turbo` | ~1.6 GB | Best, and it wants a GPU |

Any faster-whisper model on Hugging Face works too — a repo id with a slash in
it (`Systran/faster-distil-whisper-large-v3`) is passed through untouched.

The weights come from a public repo: no account, no key. `uv run bea --setup`
offers to download them at the end rather than leaving the wait to her first
sentence, and a refusal — a shared IP against Hugging Face's anonymous rate
limit — is logged with what would fix it, `HF_TOKEN` in `.env`.

**Degenerate decodes.** faster-whisper retries a decode that trips
`compression_ratio_threshold` at increasing temperatures, so this provider
passes a ladder — `TEMPERATURES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)`
(`src/modules/STT/faster_whisper_stt.py`). A single `0.0` would leave the
retry loop with nowhere to go. On Groq/OpenRouter, `temperature=0.0` already
requests the server-side equivalent.

**What it normalises, so the same config.json works on every provider:**

- `stt_model`. The hosted spelling `whisper-large-v3-turbo`, or
  `openai/whisper-large-v3-turbo`, becomes `large-v3-turbo` — switching
  `stt_provider` does not also mean editing the model.
- `language`. Resolved by `core/language.py` for every provider alike, then
  checked here against the languages this build of whisper actually has. One it
  does not have falls back to auto-detection with a warning, rather than raising
  and taking the transcript down to an empty string.

> Nothing else about her becomes local by choosing this. The mind is still a
> hosted model, and it is still sent what she heard.

---

## When the device will not run

A GPU ctranslate2 can see is not one it can use: on Windows the CUDA Toolkit
DLLs do not come with the pip wheels, so the model loads and every
transcription fails. Instead of staying deaf, she probes the device once at
startup with a silent second — if it cannot hear, she rebuilds on `cpu/int8`
before anyone speaks and says so loudly in the log, with what to install for
your OS. If a device breaks mid-call, the current turn is retried on CPU
rather than dropped.

`/status` reports the honest state (`stt.device`, `stt.degraded`,
`stt.last_error`), and the doctor's ears check names the fix.

---

## Groq (`groq_stt.py`)

Groq's Whisper endpoint. Fast enough for near-realtime.

- **Config:** `stt_provider: "groq"`, `stt_model` (default `whisper-large-v3-turbo`)
- **Key:** `GROQ_API_KEY` env → `config.json` → `None`

The connection to Groq is kept for `KEEPALIVE_SECONDS` (90) between turns. The
SDK's own default is five seconds, shorter than most pauses in a call, and a
new connection is a handshake in front of every transcription.

---

## OpenRouter (`openrouter_stt.py`)

The same Whisper models through OpenRouter, useful when you already have a key
there and would rather not add a Groq account.

- **Config:** `stt_provider: "openrouter"`, `stt_model`
- **Key:** `OPENROUTER_API_KEY`

Model ids are namespaced here, so a bare `whisper-large-v3-turbo` is rewritten
to `openai/whisper-large-v3-turbo` on both load and hot reload — an id copied
from the Groq config keeps working.

Requests go through one `requests.Session`, so the connection is kept between
turns. A request that finds the kept connection closed by the far end is sent
once more; a timeout is not.

---

## The Discord path

The bot decodes Opus to PCM in Node (`prism-media`), resamples 48 kHz stereo
to 16 kHz mono (`Pcm.js`) and posts **WAV files**. Python never handles raw
Opus. Turn segmentation happens in the bot — see
[Discord](../skills/discord.md#voice-input-turn-segmentation).

Each turn is transcribed and deposited on the perception bus as its own
`VOICE` perception, unless dropped by the echo guard (see
[Discord](../skills/discord.md#echo-suppression)). The [bus](../architecture.md#the-consciousness-loop)
coalesces a burst into a single batch, and the attention gate decides what
deserves a reasoning cycle — so two people talking at once become one batch, one
turn, one answer.

---

## Hot reload

`reload_config()` updates the model and re-creates the client if the key
changed. Switching `stt_provider` itself needs a restart — the object type
changes.

Local Whisper compares the whole set — model, device, precision, cache — and
rebuilds only when one of them actually moved. Loading it is seconds and
possibly a download, and an unrelated save from the dashboard must not pay for
that.

[Discord Skill →](../skills/discord.md)
