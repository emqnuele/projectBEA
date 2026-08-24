# TTS Modules

← [Back to README](../../README.md) | [Architecture](../architecture.md)

---

## Overview

The TTS layer is defined by `TTSInterface`. Every engine returns a NumPy audio
array plus a sample rate; **`Expression`** (`src/core/expression/voice.py`) is
what plays it, animates OBS around it and handles barge-in. No skill renders
speech itself — there is exactly one output sink.

The engine is selected with `tts_provider` and instantiated in `src/cli.py`.

```
src/modules/tts/
├── edge_tts_wrapper.py    Microsoft EdgeTTS (free, online)
├── kokoro_tts_wrapper.py  Kokoro ONNX (local, no API)
└── orpheus_tts_wrapper.py Orpheus (API, high quality)
```

---

## Interface Contract

```python
class TTSInterface(ABC):
    async def generate_audio(text: str) -> (np.ndarray, sample_rate: int)
    async def speak(text: str, output_device_id: int) -> None
    def reload_config(config: BrainConfig) -> None
```

`Expression` always calls `generate_audio()` and plays the array itself, which
is what makes interruption and resume possible — the buffer is tracked at the
Expression level, not inside the engine.

Two routes go through the same code:

| Route | What happens |
|---|---|
| `local` | played on the audio device, with the OBS avatar and text bubble animated alongside |
| `remote` | rendered to WAV bytes and returned, for Discord to play in the call |

> `speak()` is also declared `@abstractmethod`, so a custom engine must define
> it even though `Expression` never calls it. Omitting it raises `TypeError` at
> instantiation.

---

## Providers

### EdgeTTS (`edge_tts_wrapper.py`)

**Library:** `edge-tts`  
**Cost:** Free (uses Microsoft Edge's TTS API)  
**Config keys:** `tts_voice`, `tts_pitch`, `tts_rate`, `tts_volume`

Generates audio to a temporary MP3 file, reads it back as a NumPy array via `soundfile`, then deletes the temp file. Each generation uses a unique UUID filename to avoid collisions during concurrent calls.

**Voice format:** `"it-IT-IsabellaNeural"`, `"en-US-AvaNeural"`, etc.  
Full voice list: `edge-tts --list-voices`

```python
tts = EdgeTTSWrapper(voice="en-US-AvaNeural", pitch="+5Hz", rate="+10%", volume="+33%")
audio, sr = await tts.generate_audio("Hello!")
```

> The constructor's `output_file` argument is vestigial: `generate_audio()`
> always writes to a fresh UUID filename so concurrent calls cannot collide.
> Its class-level defaults (`en-US-JennyNeural`, `+0Hz`, `+0%`, `+0%`) also
> differ from the `BrainConfig` ones — `src/cli.py` always passes the config
> values explicitly, so the class defaults only matter if you instantiate the
> wrapper by hand.

---

### Kokoro ONNX (`kokoro_tts_wrapper.py`)

**Library:** `kokoro-onnx`  
**Cost:** Free (runs entirely locally)  
**Config keys:** `kokoro_model`, `kokoro_voices_file`, `kokoro_voice`, `kokoro_speed`, `kokoro_lang`

Runs the Kokoro TTS model locally via ONNX Runtime. No internet connection required after downloading the model files. Best for privacy or offline use.

**Model files:** `kokoro-v0_19.onnx` and `voices.bin` are **downloaded automatically** on first launch if missing (from GitHub Releases, ~125 MB total). No manual download needed.

To use a custom path, update `kokoro_model` and `kokoro_voices_file` in `config.json`.

**Voice examples:** `af_bella`, `af_sarah`, `am_adam`, `bf_emma`

---

### Orpheus (`orpheus_tts_wrapper.py`)

**Library:** `requests`  
**Cost:** API-based (Baseten — billed per inference)  
**Config keys:** `orpheus_voice`  
**Env vars (secrets — never saved to `config.json`):** `ORPHEUS_API_KEY`, `ORPHEUS_ENDPOINT`

Calls a self-deployed Orpheus model on [Baseten](https://baseten.co). Produces highly expressive, human-like speech — the highest quality TTS option available.

**Setup required:** You must deploy the Orpheus model to your own Baseten workspace before use. See [Setup Guide → Orpheus TTS Setup](../setup.md) for step-by-step instructions.

The wrapper POSTs to your endpoint with `stream: true`, collects raw PCM bytes
(24 kHz, 16-bit mono) and decodes them to a NumPy array for `Expression` to
play.

**Voice examples:** `zoe`, `tara`, `leo`, `leah`

> The class default is `tara`; the effective default is `zoe`, from
> `BrainConfig.orpheus_voice`.

---

## Hot Reload

`reload_config()` updates voice, pitch, rate and volume for EdgeTTS; voice,
speed and lang for Kokoro; key, endpoint and voice for Orpheus. Changing
`tts_provider` itself needs a restart — the object type changes, and the
dashboard says so when you save.

---

## Adding a New TTS Engine

1. Create `src/modules/tts/my_tts.py` and extend `TTSInterface`.
2. Implement `async generate_audio(text) -> (np.ndarray, int)`, `speak()` and
   `reload_config()`.
3. Add the instantiation branch in `src/cli.py` (`# tts`).
4. Add the provider name to the `--tts-provider` choices, also in `src/cli.py`.
