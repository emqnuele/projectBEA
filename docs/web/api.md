# Web API Reference

← [Back to README](../../README.md) | [Frontend →](frontend.md)

---

## Overview

The FastAPI server (`src/web/app.py`) is started when `--web` is passed to `main.py`. It runs on `http://0.0.0.0:8000` and serves both the REST API and the compiled React frontend as static files.

Base URL: `http://localhost:8000`

---

## Endpoints

### Status & Config

#### `GET /status`
Returns the current brain state.

**Response:**
```json
{
  "is_speaking": false,
  "active_skills": ["memory", "discord"]
}
```

---

#### `GET /config`
Returns the full current config as a JSON object (all `BrainConfig` fields).

> **Security note:** The response includes **all** `BrainConfig` fields, including secret API key fields (`gemini_key`, `openai_key`, `groq_key`, `orpheus_key`, `orpheus_endpoint`, etc.). No secret-stripping is applied to this endpoint (unlike `save_to_file()`). Do not expose this endpoint over a public network without authentication.

---

#### `POST /config`
Updates one or more config fields and hot-reloads the engine.

**Request:**
```json
{
  "config": {
    "tts_voice": "en-US-AvaNeural",
    "typing_delay": 0.05
  }
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Configuration updated.",
  "restart_required": false
}
```

> `restart_required: true` is returned when `tts_provider` changes, since the TTS object must be re-instantiated.

---

### Chat

#### `POST /chat`
Sends a text message to the brain and gets a response. Output (TTS + OBS) is triggered as a background task.

**Request:**
```json
{ "message": "Hello Bea!" }
```

> **Validation:** `message` must be between 1 and 4000 characters and must not be empty or whitespace-only. Leading/trailing whitespace is stripped automatically. A malformed request returns `422 Unprocessable Entity` with field-level error details.

**Response:**
```json
{
  "status": "success",
  "response": {
    "role": "assistant",
    "content": "Oh, you finally showed up.",
    "mood": "bored"
  }
}
```

---

#### `POST /audio`
Sends an audio file (WAV) for STT transcription and response.

**Request:** `multipart/form-data`, field `file` = WAV file

**Response:**
```json
{
  "status": "success",
  "response": {
    "role": "assistant",
    "content": "...",
    "mood": "normal",
    "user_transcript": "the transcribed text"
  }
}
```

---

#### `POST /interrupt`
Immediately stops current speech and typing.

**Response:**
```json
{ "status": "success", "message": "Interrupted" }
```

---

### Discord Endpoints

#### `POST /discord/chat`
Receives a text message from the Discord bot and generates a text response (no TTS, no OBS animation).

> **Implementation note:** The endpoint prepends the username as a prefix before calling the brain: the message stored in conversation history is `[username] message` (e.g. `[emanu] hello bea`). The `background_tasks` parameter is injected by FastAPI but is currently unused — unlike `POST /chat`, this endpoint does **not** schedule `perform_output_task()`, so no OBS avatar animation or text bubble is triggered for Discord text-chat messages.

**Request:**
```json
{
  "username": "emanu",
  "message": "hello bea",
  "channelId": "123456789"
}
```

> **Validation:** `username` must be at least 1 character. `message` must be between 1 and 4000 characters and not empty/whitespace-only (stripped automatically). Returns `422` on failure.

**Response:**
```json
{
  "status": "success",
  "response": "...",
  "mood": "normal"
}
```

---

#### `POST /discord/audio`
Receives a voice audio chunk from the Discord bot's VoiceManager.

**Request:** `multipart/form-data`
- `file` — WAV audio file
- `username` — Discord username  
- `flush_buffer` — `"true"` if this is the final chunk for this user's utterance *(accepted by the endpoint but currently not acted upon — buffering is driven entirely by the 300 ms server-side aggregation window, not by this flag)*

**Response:**
```json
{
  "status": "success",
  "text": "Bea's text response",
  "transcript": "combined transcript log (all speakers, pipe-delimited for multi-speaker scenarios)",
  "audio_base64": "<base64-encoded WAV bytes>"
}
```

> `status` can be `"success"` or `"resume"` (when Bea resumes interrupted speech). In multi-speaker buffer flushes, only the **first** caller within the 300 ms aggregation window receives audio — all other callers in the same flush receive `status: "success"` with `text: "(Merged)"` and an empty `audio_base64` string.

> **All-backchannel flush:** If every input in the aggregation window is a backchannel phrase, the buffer is short-circuited before the LLM is called. All callers receive `status: "resume"` with an empty `audio_base64` and their individual transcript as `transcript`. No TTS audio is generated in this case.

---

#### `POST /voice/transcript`
Buffer-only endpoint used during barge-in: transcribes a short audio snippet and accumulates it without triggering an LLM response. The buffered text is included as context in Bea's next response.

**Request:** `multipart/form-data`
- `file` — WAV audio file (typically < 3 seconds)
- `username` — Discord username

**Response:**
```json
{ "status": "buffered", "transcript": "ok continue" }
```

---

### Sessions & History

#### `GET /history`
Returns the last 50 messages of the current session.

**Response:** Array of message objects:
```json
[
  { "role": "user", "content": "hi", "timestamp": "..." },
  { "role": "assistant", "content": "...", "mood": "normal", "timestamp": "..." }
]
```

---

#### `GET /sessions`
Lists all saved conversation sessions.

**Response:**
```json
[
  {
    "id": "session_1700000000",
    "timestamp": "2025-01-01T12:00:00",
    "preview": "hi bea...",
    "message_count": 42
  }
]
```

---

#### `POST /sessions`
Creates a new session (and triggers memory processing for the previous one).

**Response:**
```json
{ "status": "success", "session_id": "session_1700000001" }
```

---

#### `POST /sessions/{session_id}/activate`
Loads a past session, restoring its history as the current context.

---

### Memory

#### `POST /memory/save`
Manually triggers diary generation for the current session.

---

### Events (Brain Activity)

#### `GET /events`
Returns the last N events from the `EventManager` buffer.

**Query param:** `?limit=50` (default 50)

**Response:** Array of event objects:
```json
[
  {
    "id": "uuid",
    "timestamp": 1700000000.0,
    "category": "output",
    "source": "llm",
    "message": "Oh you finally showed up.",
    "metadata": { "mood": "bored" }
  }
]
```

Event categories: `system`, `input`, `output`, `thought`, `skill`, `tool`, `error`.

---

### Skills

#### `GET /skills`
Returns a dict of all registered skills and their current state, keyed by skill name:

```json
{
  "memory":    { "enabled": true,  "active": true,  "config": { "chroma_path": "data/memory_db", "..." } },
  "discord":   { "enabled": false, "active": false, "config": { "token": "", "..." } },
  "minecraft": { "enabled": false, "active": false, "config": { "server_url": "ws://localhost:8080", "..." } },
  "monologue": { "enabled": false, "active": false, "config": { "interval_seconds": 30, "..." } }
}
```

Each entry has:
- `enabled` — whether the skill is configured to run
- `active` — whether the skill is currently running
- `config` — the full skill config block from `config.json`

---

#### `POST /skills/{name}/toggle`
Toggles a skill on or off.

**Query parameter:** `?enable=true` or `?enable=false`

```
POST /skills/discord/toggle?enable=true
```

**Response:**
```json
{ "status": "success", "enabled": true }
```

---

### Health

#### `GET /health`
Returns a simple liveness check. Used to verify the server is running.

**Response:**
```json
{ "status": "ok" }
```

---

### Skill Logs (Legacy)

#### `GET /skills/logs`
Filters the event buffer and returns only events in the `skill`, `thought`, and `error` categories, reformatted for backward compatibility.

**Query param:** none (always returns last 100 matching events)

**Response:** Array of log entries:
```json
[
  { "timestamp": 1700000000.0, "skill": "skill:monologue", "message": "Starting new story..." }
]
```

> Prefer `GET /events` for new integrations — this endpoint exists for backward compatibility.

---

## Frontend Static Serving

When the React frontend is built (`npm run build`), only the `dist/assets/` sub-folder is mounted as a `StaticFiles` route at `/assets`. All other requests — including navigation routes like `/dashboard` and the root `/` — are handled by a catch-all `GET /{full_path}` route that returns `dist/index.html` directly.

> **Note:** Files placed in `dist/` outside of `assets/` (e.g. `favicon.ico`, `robots.txt`) are **not** served as static files. Any request for such a file will receive `index.html` instead.

[Frontend Documentation →](frontend.md)
