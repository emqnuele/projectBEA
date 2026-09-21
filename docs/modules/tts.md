# TTS Modules

← [Back to README](../../README.md) | [Architecture](../architecture.md)

---

## Overview

The TTS layer is defined by `TTSInterface`. All engines generate a NumPy audio array + sample rate, which the brain plays via `sounddevice`. The active engine is selected with `tts_provider` in config.

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

The brain always calls `generate_audio()` and handles playback itself via `sounddevice.play()`. `speak()` is also an abstract method — implementations must provide it (even if only as a thin wrapper around `generate_audio()`). The Kokoro wrapper includes a working `speak()` for direct use; the brain itself does not call it.

> **Important for custom TTS engines:** if you omit `speak()` from your implementation, Python will raise `TypeError` at instantiation time because it is declared `@abstractmethod` in `TTSInterface`. This allows interrupt/resume functionality (the audio buffer is tracked at the brain level).

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

> **Constructor note:** `EdgeTTSWrapper.__init__` also accepts an `output_file` parameter (default: `"temp_tts.mp3"`). This parameter is vestigial — `generate_audio()` ignores it and always uses a unique UUID-based filename to prevent collisions during concurrent calls. It is safe to omit. The class-level default for `voice` is `"en-US-JennyNeural"`; at runtime the value from `BrainConfig.tts_voice` (`"en-US-AvaNeural"`) is always passed explicitly.

> **Default mismatch note (EdgeTTS):** The class-level constructor defaults for `pitch`, `rate`, and `volume` are `"+0Hz"`, `"+0%"`, `"+0%"` respectively — these differ from the `BrainConfig` defaults of `"+5Hz"`, `"+10%"`, `"+33%"`. The brain always passes the config values explicitly, so the class defaults only matter if `EdgeTTSWrapper` is instantiated directly without arguments (e.g. in tests or standalone usage).

> **Dead method note:** `EdgeTTSWrapper` contains a vestigial `generate_audio(self, text: str, filename: str) -> None` definition (the original helper that wrote to a fixed filename). Python silently shadows it with the second `generate_audio(self, text: str) -> tuple[np.ndarray, int]` definition, which is the one that actually executes. The first definition is unreachable and has no effect at runtime.

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

The wrapper POSTs to your endpoint with `stream: true`, collects raw PCM bytes (24 kHz, 16-bit mono), decodes them to a NumPy array, and returns them to the brain for playback.

**Voice examples:** `zoe`, `tara`, `leo`, `leah`

> **Default mismatch note (Orpheus):** The `OrpheusTTSWrapper` class constructor defaults to `voice="tara"`. The `BrainConfig` dataclass default for `orpheus_voice` is `"zoe"`. At runtime the brain always passes `config.orpheus_voice` explicitly, so the effective default seen by users is `"zoe"`. The class default only matters for direct instantiation without arguments.

---

## Hot Reload

`reload_config()` updates `voice` in place for EdgeTTS (also `pitch`, `rate`, `volume`). For Kokoro it updates `voice`, `speed`, and `lang`. For Orpheus, it also updates the API key, endpoint URL, and voice. Changing `tts_provider` itself requires a restart (the object type changes).

---

## Adding a New TTS Engine

1. Create `src/modules/tts/my_tts.py` and extend `TTSInterface`.
2. Implement `async generate_audio(text) -> (np.ndarray, int)` and `reload_config()`.
3. In `main.py`, add the instantiation branch.
4. Add the provider name to `--tts-provider` choices.
