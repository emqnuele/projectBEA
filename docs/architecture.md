# Architecture

← [Back to README](../README.md)

---

## Overview

ProjectBEA is built around a central orchestrator — `AIVtuberBrain` — that coordinates a set of independently pluggable modules (LLM, TTS, STT, OBS) and a self-contained skill system. The design goal is that every component can be swapped without changing the core logic.

---

## Component Diagram

```
                        ┌────────────────────────────────────────────┐
                        │             main.py  (Entry Point)         │
                        │  - Parses CLI arguments                    │
                        │  - Instantiates modules from config        │
                        │  - Creates and starts AIVtuberBrain        │
                        └───────────────────┬────────────────────────┘
                                            │
                        ┌───────────────────▼────────────────────────┐
                        │             AIVtuberBrain                  │
                        │  src/core/brain.py                         │
                        │                                            │
                        │  ┌─────────┐  ┌─────────┐  ┌──────────┐    │
                        │  │  LLM    │  │  TTS    │  │  STT     │    │
                        │  │Interface│  │Interface│  │Interface │    │
                        │  └─────────┘  └─────────┘  └──────────┘    │
                        │  ┌──────────────────────────────────────┐  │
                        │  │           OBSInterface               │  │
                        │  └──────────────────────────────────────┘  │
                        │  ┌──────────────────────────────────────┐  │
                        │  │           SkillManager               │  │
                        │  │  ┌────────┐ ┌─────────┐ ┌────────┐   │  │
                        │  │  │ Memory │ │ Discord │ │  MC    │   │  │
                        │  │  └────────┘ └─────────┘ └────────┘   │  │
                        │  │  ┌────────────┐                      │  │
                        │  │  │ Monologue  │                      │  │
                        │  │  └────────────┘                      │  │
                        │  └──────────────────────────────────────┘  │
                        │  ┌──────────────────────────────────────┐  │
                        │  │  HistoryManager  │  EventManager     │  │
                        │  └──────────────────────────────────────┘  │
                        └────────────────────┬───────────────────────┘
                                             │
               ┌─────────────────────────────▼───────────────────────────┐
               │                  Web Layer (optional)                   │
               │   FastAPI (src/web/app.py)  +  React (src/web/frontend) │
               └─────────────────────────────────────────────────────────┘
```

---

## Core: `AIVtuberBrain`

**File:** `src/core/brain.py`

The brain is the single object that holds references to every module and coordinates all interactions. Key responsibilities:

| Responsibility | Description |
|---|---|
| **`initialize()`** | Loads avatar resources from `avatar_map` into `png_map`, loads the system prompt, connects OBS, creates a new session, calls `SkillManager.initialize()` to register and init skills — does **not** start them |
| **`start_skills()`** | Starts the background `SkillManager` loop; must be called after `initialize()`. This is the step that makes enabled skills go live. |
| **`generate_response(text, system_prompt=None)`** | Accepts text input and an optional `system_prompt` override → injects date + memory context → calls LLM → saves to history → emits `EventCategory.OUTPUT`. If `system_prompt` is `None`, uses `self.system_prompt`. Returns `("neutral", "[RESUMED]")` without calling the LLM when the input is a backchannel and a `resume_buffer` is active. |
| **`generate_audio_response()`** | Accepts an audio file → transcribes via STT (or calls `llm.chat_audio()` if no transcript) → runs the full LLM + history pipeline inline. Returns a 3-tuple `(mood, message, transcript)`; on backchannel detection also returns `("neutral", "[RESUMED]", transcript)`. **Does not emit `EventCategory.OUTPUT` for the LLM turn.** When called via `POST /audio`, the endpoint schedules `perform_output_task()` separately, which does emit a TTS `OUTPUT` event — so audio responses are visible in the Brain Activity feed when using the web API. |
| **`perform_output_task()`** | Given `(mood, message)`: first cancels any in-flight typing/speech tasks, then calls `set_text("", ...)` to clear the previous text bubble, then sets OBS avatar to talking pose. Starts `type_text()` as an async task immediately; then **awaits** `TTS.generate_audio()` — because `await` yields the event loop, the typing task executes concurrently with TTS generation. Then starts `_play_audio()` as a second task and gathers both. Typing animation, TTS generation, and audio playback all overlap; none of these three phases is strictly sequential. |
| **`interrupt()`** | Cancels in-flight speech and typing tasks. Stores remaining audio in `resume_buffer` **only if the trailing fragment is longer than 0.5 s** — shorter tails are silently discarded (`resume_buffer` is set to `None`). |
| **`reload_configuration()`** | Hot-reloads LLM, TTS, OBS, and STT modules and all skills after a config change |
| **`run_loop()`** | Interactive CLI input loop (`You >` prompt). Supports `audio:<path>` prefix to send an audio file. Runs until user types `exit` or `quit`. |
| **`shutdown()`** | Called in the `finally` block of `main.py`. Before `shutdown()` is invoked, `main.py` explicitly calls `await brain.skill_manager.stop()`, which cancels the skill loop and awaits all active skills' `stop()` coroutines. Only then is `brain.shutdown()` called to disconnect OBS. |

> **Deprecated wrappers:** `process_text_input(text)` and `process_audio_input(audio_path)` still exist on `AIVtuberBrain` for backward compatibility. They combine `generate_response()` / `generate_audio_response()` with `perform_output_task()` in a single call. New code should use the two-step API directly.

### Barge-in & Resume Buffer

When a user interrupts Bea mid-speech, the brain:
1. Calculates how many audio samples were already played.
2. Stores the remaining audio in `resume_buffer` — **only if the remaining fragment is longer than 0.5 s**; shorter tails are discarded.
3. If the user's next input is detected as a backchannel, speech resumes from where it was cut.

**Backchannel detection (`_is_backchannel`):** A fixed vocabulary of single- and multi-word phrases is matched: `"ok"`, `"yeah"`, `"continue"`, `"vai avanti"`, `"go on"`, `"procedi"`, `"continua"`, and others. Any input **longer than 30 characters** is unconditionally rejected as a backchannel, regardless of content.

> **Backchannel return value:** When `generate_response()` detects a backchannel with an active `resume_buffer`, it calls `_resume_speech()` and returns the sentinel tuple `("neutral", "[RESUMED]")` — **no LLM call is made**. Callers (e.g. web API `POST /chat`, Discord flush) will receive `mood="neutral"` and `content="[RESUMED]"` in the response. The frontend should treat `[RESUMED]` as a no-op display-wise.

---

## Data Flow

### Text Input Path

```
User text
    │
    ▼
generate_response()
    ├─ inject date + memory context into system prompt
    ├─ call LLM.chat(user_text, system_prompt, history)
    │       └─ returns (mood: str, message: str, metadata: dict)
    ├─ save to HistoryManager
    └─ emit EventCategory.OUTPUT event
    │
    ▼
perform_output_task(mood, message)
    ├─ cancel in-flight typing and speech tasks (if any)
    ├─ OBS: set_text("", ...) → clears any previous text bubble
    ├─ OBS: switch avatar to talking pose for this mood
    ├─ [task] OBS.type_text(message) → starts async typing animation
    ├─ [concurrent] TTS.generate_audio(message) → numpy array  (await yields; typing task runs concurrently)
    ├─ [task] _play_audio(numpy array) → sounddevice playback
    └─ gather(typing_task, speech_task) → wait for both to finish
    ├─ OBS: switch avatar back to idle
    └─ OBS: clear text bubble
```

### Audio Input Path

```
Audio file (WAV/MP3)
    │
    ▼
generate_audio_response()
    ├─ STT.transcribe(audio_path) → transcript text
    │       (if transcript is a backchannel → _resume_speech(); return ("neutral", "[RESUMED]", transcript))
    ├─ save user transcript to HistoryManager (same as generate_response)
    ├─ inject date + memory context (same as generate_response)
    ├─ if transcript available: LLM.chat(transcript, system_prompt, history)
    │   else:                   LLM.chat_audio(audio_path, system_prompt, history)
    ├─ save assistant message to HistoryManager
    └─ return (mood, message, transcript)  ← always a 3-tuple
```

> **Note:** `generate_audio_response()` runs the full pipeline inline — it does **not** call `generate_response()` internally. The two methods share the same logic but are maintained separately. One behavioral difference: `generate_audio_response()` does **not** emit `EventCategory.OUTPUT` for the LLM response turn. However, when invoked via `POST /audio`, the endpoint separately schedules `perform_output_task()`, which does emit a TTS `OUTPUT` event — so audio responses **are** visible in the Brain Activity feed when using the web API. They are invisible only if `generate_audio_response()` is called directly without a subsequent `perform_output_task()`.

### Discord Voice Path

```
Discord voice data (Opus stream)
    │  [VoiceManager.js — Node.js bot — prism-media OpusDecoder → PCM → WAV]
    ▼
POST /discord/audio  (multipart — WAV + username + flush_buffer)
    │
    ▼
brain.process_discord_interaction()
    ├─ STT.transcribe() → transcript
    ├─ buffer aggregation: all callers within 300 ms window (BUFFER_WINDOW)
    │       are merged into one LLM context to handle simultaneous speakers
    ├─ generate_response(combined_text)
    ├─ TTS.generate_audio() → numpy array → WAV bytes → base64 → JSON response
    └─ _perform_visual_only_task(mood, message, duration)
            └─ animates OBS avatar + text bubble WITHOUT local audio playback
               (audio plays in Discord channel instead)
    │
    ▼
VoiceManager: decode base64 → Readable stream → AudioPlayer
```

> Opus decoding happens entirely in Node.js. The Python side only ever receives a WAV file.

---

## Configuration System

**File:** `src/core/config.py`

`BrainConfig` is a Python `@dataclass` that:
- Sets sensible defaults for every field.
- On `__post_init__`, automatically loads `config.json` from the project root.
- Has a `save_to_file()` method used by the web API for persistent config updates.

Config priority differs by field type (highest → lowest):

| Field type | Priority order |
|---|---|
| Non-secret fields (`language`, `llm_provider`, `obs_host`, …) | CLI arg → `config.json` → dataclass default *(env vars not read)* |
| Secret fields (`*_key`, `orpheus_endpoint`) | CLI arg → environment variable → `config.json` fallback → `None` |

> Environment variables are **only read for secret fields**. For those fields they unconditionally win over `config.json` — if the env var is non-empty, the `config.json` value is ignored even if it is non-empty.

[Configuration Reference →](configuration.md)

---

## Event System

**File:** `src/core/events.py`

The `EventManager` is a simple in-process pub/sub bus. Events are published by any part of the brain and stored in a circular buffer of up to 200 events.

| Category | Published by |
|---|---|
| `system` | Brain lifecycle events |
| `input` | User text/audio received |
| `output` | LLM response, TTS playback |
| `thought` | Internal reasoning (Minecraft agent) |
| `skill` | Skill state changes |
| `tool` | Tool calls (Minecraft agent tools) |
| `error` | Errors |

The web frontend polls `GET /events` to display the real-time brain activity feed.

---

## Interface Layer

**File:** `src/interfaces/base_interfaces.py`

All pluggable components implement one of these abstract base classes:

```python
class LLMInterface(ABC):
    def chat(user_input, system_prompt, history) -> (mood, message, metadata)
    def chat_audio(audio_path, system_prompt, history) -> (mood, message, metadata)
    def generate_json(user_input, system_prompt, history) -> dict
    def reload_config(config) -> None

class TTSInterface(ABC):
    async def generate_audio(text) -> (np.ndarray, sample_rate)
    async def speak(text, output_device_id) -> None   # abstract; brain does not call this directly
    def reload_config(config) -> None

class STTInterface(ABC):
    def transcribe(audio_path, language: str = "en") -> str
    def reload_config(config) -> None

class OBSInterface(ABC):
    def connect() / disconnect()
    def set_image(path) / set_media(path)
    async def type_text(text, source_name, **kwargs) -> int
    def set_text(text, source_name, font_size) -> None
    def reload_config(config) -> None
```

---

## Logging

**File:** `src/utils/logger.py`

All modules use a shared structured logger built on Python's `logging` module with [`rich`](https://github.com/Textualize/rich) for colored console output.

```python
from src.utils.logger import get_logger

logger = get_logger("bea.mymodule")
logger.info("started")
logger.warning("something off")
logger.error(f"failed: {e}")
logger.debug("verbose detail")
```

`get_logger(name)` returns a cached `logging.Logger` instance. Each name maps to one logger — calling `get_logger("bea.brain")` twice returns the same object.

**Log level** defaults to `INFO`. To see `DEBUG` output (e.g. OBS pagination, TTS playback details) set the env var before launch:

```bash
LOG_LEVEL=DEBUG python main.py --web
```

The logger sets `propagate = False` on every instance to prevent duplicate output from uvicorn's root logger.

---

## Session & History

**File:** `src/utils/history_manager.py`

Every conversation is a "session" stored as a JSON file under `data/conversations/`.

```json
{
  "session_id": "session_1700000000",
  "start_time": "2025-01-01T12:00:00",
  "last_updated": "2025-01-01T12:30:00",
  "messages": [
    {"role": "user", "content": "Hi!", "timestamp": "..."},
    {"role": "assistant", "content": "...", "mood": "normal", "timestamp": "..."}
  ]
}
```

When a new session is started, the previous session is asynchronously processed by the Memory Skill's `DiaryGenerator` to produce a ChromaDB memory entry.

---

## Related Docs

- [Configuration →](configuration.md)
- [Skills Overview →](skills/overview.md)
- [Memory Skill (RAG) →](skills/memory.md)
- [Web API →](web/api.md)
