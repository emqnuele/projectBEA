# TTS Modules

← [Back to README](../../README.md) | [Architecture](../architecture.md)

---

## Overview

The TTS layer is defined by `TTSInterface`. Every engine returns a NumPy audio
array plus a sample rate; **`Expression`** (`src/core/expression/voice.py`) is
what plays it, animates OBS around it and handles barge-in. No skill renders
speech itself — there is exactly one output sink.

The engine is selected with `tts_provider` and built by `factory.py`.

```
src/modules/tts/
├── providers.py           every engine as data: its voices and their languages
├── factory.py             builds the selected one, handed the voice it should use
├── edge_tts_wrapper.py    Microsoft EdgeTTS (free, online)
├── kokoro_tts_wrapper.py  Kokoro ONNX (local, no API)
└── orpheus_tts_wrapper.py Orpheus (API, high quality)
```

**An engine does not decide a language.** `providers.py` holds one row per
engine — its voices, the language of each, and whatever else that engine needs
to be told — and `providers.voice_for(config)` is the single answer to "which
voice will actually be used". The wizard, the dashboard, `make doctor` and the
factory all ask it, so they cannot drift. See [Languages](../languages.md).

---

## Interface Contract

```python
class TTSInterface(ABC):
    pieces_in_flight: int = 1  # pieces of one line the engine may make at once
    async def generate_audio(text: str, prosody=None) -> (np.ndarray, sample_rate: int)
    async def generate_stream(text: str, prosody=None)  # optional, yields (audio, rate)
    def reload_config(config: BrainConfig) -> None
```

`Expression` plays what the engine makes itself, which is what makes
interruption possible — playback is owned by Expression, not by the engine.

Two routes go through the same code:

| Route | What happens |
|---|---|
| `local` | `generate_audio()` per piece, played on this machine's output through `LocalPlayer` (below), with the avatar and caption timed to what reaches the speaker |
| `call` | `generate_stream()` per piece; every part is pushed into the Discord call the moment it exists, so the room hears the start of a sentence while the end of it is still being made |

A line is cut into pieces as it is written (`expression/chunking.py`). An
engine that sets `pieces_in_flight = 2` — the remote ones, where a request is
mostly waiting — starts on the next piece as soon as its words exist, beside
the one before it; the pieces still play in order. A local engine keeps one at
a time, because a second synthesis takes the cores the first one needs.

Parts of one piece are converted to the call's 48 kHz stereo by one
`CallResampler` and lip-synced as one piece, so a streamed sentence sounds and
moves exactly like one made whole.

### Playing on this machine (`expression/player.py`)

One output stream stays open while she talks, in PortAudio's blocking mode, and
one thread of its own (`voice-out`) writes into it. The event loop never calls
PortAudio: opening, writing, reopening and closing all happen on that thread.

- **Kept at most `audio_buffer_ms` ahead** of what the device has taken (100 ms
  by default, and never more than the stream's own buffer). The writer wakes
  once at least 10 ms of room is free and fills all of it in one write, never
  more than the ring holds, so a write never blocks and a writer that woke late
  catches up at once. Every call into PortAudio lets go of the GIL and has to
  win it back, which is why `bootstrap()` sets the interpreter's switch interval
  to 1 ms (unless `BEA_PERF=off`): at the default 5 ms a busy engine kept the
  writer behind the speaker. A hole the room did hear is logged as a warning,
  at most once every 30 s. The stream asks PortAudio for its default latency,
  the quickest to the speaker; `audio_latency_s` trades some of that for a
  bigger buffer.
- **Pieces follow each other in the same stream.** `play()` returns once less
  than a buffer's worth of the piece is left to write, so the next piece is
  queued while this one is still sounding and nothing is ever cut or gapped
  between sentences.
- **Timed by the speaker.** The moment a sample is heard is what is still queued
  in the ring plus the device's own latency (`default_low_output_latency`, as
  PortAudio reports it). The mouth, the caption of a sentence written as it
  goes, a `<mood:…>` or `<do:…>` inside the line, and the end of the line all
  fire at that moment, in the order they were queued. `is_speaking` stays true
  until the end is heard.
- **The stream opens before she speaks**: when a turn somebody waits on starts
  (`Expression.warm_up`, skipped during a call and for her own idle thoughts),
  and again when a line starts, while the model is still thinking and the
  first piece is still being synthesised. A bluetooth output that has been
  quiet takes a few hundred ms to open; this is where that time goes. It opens
  in 24 kHz mono (what every bundled engine makes); a piece in another format
  reopens it once, after the audio already queued has played.
- **A barge-in** drops everything queued and fades out the chunk being written
  over 12 ms. What is still heard is at most `audio_buffer_ms` plus the device's
  latency. It never blocks.
- **The output is chosen by name** (`audio_device`, empty for the system
  default; `audio_device_id` as a position is still read when no name is set).
  PortAudio lists devices only when it starts, so it is restarted each time the
  stream is about to open: a headset plugged in while she runs is found. If the
  chosen output is missing or refuses to open (a bluetooth headset in headset
  mode does), the system default is tried, then any other output, with one
  warning. With no output at all, each piece still takes as long as it lasts,
  so everything timed on her voice keeps its pace.
- **An output that disappears mid-sentence** is reopened once and the sentence
  goes on; a second failure drops the rest of that piece.
- **After `audio_idle_close_s` of silence** (30 s) the device is let go and the
  thread ends; the next line starts both again.

> `speak()` is also declared `@abstractmethod`, so a custom engine must define
> it even though `Expression` never calls it. Omitting it raises `TypeError` at
> instantiation.

---

## Providers

### EdgeTTS (`edge_tts_wrapper.py`)

**Library:** `edge-tts`  
**Cost:** Free (uses Microsoft Edge's TTS API)  
**Config keys:** `tts_voice`, `tts_pitch`, `tts_rate`, `tts_volume`

Gathers the MP3 from the Edge websocket in memory and decodes it with `soundfile` on a worker thread, never on the event loop. `generate_stream()` hands the audio over as it arrives: an MP3 cut at any byte decodes to exactly the start of what the whole file decodes to, so each part is the next stretch of the same samples. Parts are decoded once a third of a second of speech has arrived and then at every doubling, so a sentence costs a handful of decodes.

`edge-tts` always asks the service for 48 kbps MP3 and takes no argument to ask otherwise. The service also serves the same 24 kHz voice at 96 kbps, as fast and with far fewer MP3 artefacts, so the wrapper swaps that one constant in the request `edge-tts` sends and leaves the rest of its protocol alone. If a release of `edge-tts` no longer contains the constant, the library is used as it comes, at 48 kbps, with a warning; a test fails on the installed version when that happens. The first part is measured in speech, not bytes, so the richer format starts her no sooner and no later. Every piece is its own websocket connection, which is why the wrapper sets `pieces_in_flight = 2`.

That prefix invariant is a property of the service, not of this code, so it is checked twice: each longer decode is compared against the shorter one it grew from (a break is logged rather than played as a repeat or a skip), and the nightly `edge-prefix` CI job runs `tools/edge_prefix_check.py` against the real service.

**Voice format:** `"it-IT-IsabellaNeural"`, `"en-US-AvaNeural"`, etc.  
Full voice list: `edge-tts --list-voices`

```python
tts = EdgeTTSWrapper(voice="en-US-AvaNeural", pitch="+5Hz", rate="+10%", volume="+33%")
audio, sr = await tts.generate_audio("Hello!")
```

> The class-level defaults (`en-US-JennyNeural`, `+0Hz`, `+0%`, `+0%`)
> differ from the `BrainConfig` ones — `src/cli.py` always passes the config
> values explicitly, so the class defaults only matter if you instantiate the
> wrapper by hand.

---

### Kokoro ONNX (`kokoro_tts_wrapper.py`)

**Library:** `kokoro-onnx`  
**Cost:** Free (runs entirely locally)  
**Config keys:** `kokoro_model`, `kokoro_voices_file`, `kokoro_voice`, `kokoro_speed` (`kokoro_lang` is derived from the voice)

Runs the Kokoro TTS model locally via ONNX Runtime. No internet connection required after downloading the model files. Best for privacy or offline use.

**Model files:** `kokoro_model` and `kokoro_voices_file` are **downloaded automatically** on first launch if missing, each from the kokoro-onnx release asset of the same basename. The voice pack must be `voices.json`; the pinned library cannot read the `.bin` form, and a path ending in `voices.bin` is read as `voices.json` with a warning.

To use a custom path, update `kokoro_model` and `kokoro_voices_file` in `config.json`.

**Voice examples:** `af_bella`, `af_sarah`, `am_adam`, `bf_emma`

**Languages:** English only — the v0.19 voice pack contains no other. The
multilingual v1.0 pack needs a `kokoro-onnx` release requiring `numpy>=2`, which
conflicts with this project's `numpy<2.0.0` pin.

---

### Orpheus (`orpheus_tts_wrapper.py`)

**Library:** `requests`  
**Cost:** API-based (Baseten — billed per inference)  
**Config keys:** `orpheus_voice`  
**Env vars (secrets — never saved to `config.json`):** `ORPHEUS_API_KEY`, `ORPHEUS_ENDPOINT`

Calls a self-deployed Orpheus model on [Baseten](https://baseten.co). Produces highly expressive, human-like speech — the highest quality TTS option available.

**Setup required:** You must deploy the Orpheus model to your own Baseten workspace before use. See [Setup Guide → Orpheus TTS Setup](../setup.md) for step-by-step instructions.

The wrapper POSTs to your endpoint with `stream: true` and reads raw PCM
(24 kHz, 16-bit mono) straight off the response: `generate_stream()` yields it
in ~150 ms blocks, which reach the call as they arrive. A stream dropped
halfway — a barge-in cancelling the piece — stops reading and closes the
response at once, rather than downloading the rest of a sentence nobody will
hear while the interruption waits on it.

**Voice examples:** `zoe`, `tara`, `leo`, `leah`

> The class default is `tara`; the effective default is `zoe`, from
> `BrainConfig.orpheus_voice`.

---

## Hot Reload

`reload_config()` updates pitch, rate and volume for EdgeTTS; speed for Kokoro;
key and endpoint for Orpheus. All three take their **voice** from
`providers.voice_for(config)` rather than reading a field of their own, and
Kokoro takes its phonemiser language from `factory.kokoro_language(config)`.
Changing `tts_provider` itself needs a restart — the object type changes, and
the dashboard says so when you save.

---

## Adding a New TTS Engine

1. Create `src/modules/tts/my_tts.py` and extend `TTSInterface`.
2. Implement `async generate_audio(text) -> (np.ndarray, int)`, `speak()` and
   `reload_config()`.
3. Add one `VoiceProvider` row to `providers.py`, listing its voices and the
   language each one speaks.
4. Add a two-line builder to `BUILDERS` in `factory.py`. It is handed the
   `Voice` to use — it does not look one up.

That is all. The setup wizard, the dashboard menus, the language warnings and
`make doctor` are all generated from the row; there is no branch to add in any
of them. `test_tts_providers.py` fails if a row has no builder, if a builder has
no row, or if a row names a config field that does not exist.
