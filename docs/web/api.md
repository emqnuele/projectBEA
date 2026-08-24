# Web API Reference

← [Back to README](../../README.md) | [Frontend →](frontend.md)

---

## Overview

The FastAPI server (`src/web/app.py`) starts with `uv run bea --web`. It serves
both the REST API and the compiled React frontend from the same origin.

Base URL: `http://localhost:8000`

**There is no authentication.** The server binds to `127.0.0.1` by default;
`--host 0.0.0.0` is an explicit opt-in. CORS carries an allowlist (localhost on
8000 and 5173, plus anything in `BEA_ALLOWED_ORIGINS`) rather than a wildcard,
and `GET /config` drops or masks every secret.

---

## Endpoints

### Status & Config

#### `GET /status`
Returns the current brain state.

**Response:**
```json
{
  "is_speaking": false,
  "is_sleeping": false,
  "active_skills": ["memory", "discord"],
  "session_id": "session_1750000000",
  "uptime": 1832.4
}
```

`uptime` is seconds since the web process started, not since she was created.

---

#### `GET /config`
Returns the full current config as a JSON object (all `BrainConfig` fields).

> **Secrets:** the response is `BrainConfig.public_dict()`. Top-level secret
> fields (`openrouter_key`, `openai_key`, `groq_key`, `orpheus_key`,
> `orpheus_endpoint`) are removed outright, and nested skill secrets
> (`discord.token`, `telegram.token`, `twitch.oauth_token`) come back masked as
> `********` so the UI can show that one is stored. Use `GET /secrets` to learn
> *which* are set. Posting a masked value back is ignored rather than applied.

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
Deposits a `CHAT` perception from the owner and waits for whatever she decides
to say. She may decide to say nothing — the attention gate and her own
`stay_silent` are both real outcomes — in which case `content` comes back empty
after at most `consciousness.correlation_timeout` seconds.

Speech is rendered by the consciousness itself, so the background output task is
a no-op while the brain is alive.

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
Receives a text message from the Discord bot and **returns immediately**.

The message becomes a `CHAT` perception carrying
`conversation_key = "discord:<channelId>"` and is routed to a scoped
conversation turn that runs beside the live loop. Bea answers on her own,
through the Discord tools, whenever she decides to. She may also decide not to.

**Request:**
```json
{
  "username": "emanu",
  "message": "hello bea",
  "channelId": "123456789",
  "userId": "4711",
  "messageId": "987654321",
  "isDm": false
}
```

`userId` is the stable identity behind the roster and the person cards;
`messageId` is what lets her reply to or react to that exact message.

> **Validation:** `username` at least 1 character, `message` 1–4000 and not
> whitespace-only. `422` on failure.

**Response:**
```json
{ "status": "perceived" }
```

---

#### `POST /discord/audio`
Receives a voice chunk from the bot's VoiceManager. This one **does** wait: the
caller is blocked on a correlation until Bea speaks, because the bot needs the
audio back to play it in the call.

**Request:** `multipart/form-data`
- `file` — WAV audio file
- `username` — Discord username
- `user_id` — stable Discord user id (optional, but it is the identity)
- `flush_buffer` — accepted for compatibility, not acted upon

**Response:**
```json
{
  "status": "success",
  "text": "Bea's text response",
  "transcript": "the transcription of this chunk",
  "audio_base64": "<base64-encoded WAV bytes>"
}
```

> `status` is `"success"` when she spoke and `"ignored"` when she did not — the
> attention gate filtered the input, or she chose `stay_silent`. On `"ignored"`,
> `text` and `audio_base64` are empty and the bot plays nothing.

The perception bus coalesces a burst of chunks into a single batch, so two
people talking at once produce one turn and one answer.

---

#### `POST /voice/transcript`
Overheard speech: transcribes a snippet and deposits a `VOICE` perception
without waiting for anything. The attention gate decides whether it was worth
reacting to — she may answer a moment later on her own, or ignore it.

**Request:** `multipart/form-data`
- `file` — WAV audio file (typically < 3 seconds)
- `username` — Discord username
- `user_id` — stable Discord user id (optional)

**Response:**
```json
{ "status": "perceived", "transcript": "ok continue" }
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
    "title": "",
    "preview": "hi bea...",
    "message_count": 42,
    "active": true
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

#### `PATCH /sessions/{session_id}`
Renames a conversation. Body `{ "title": "…" }`. `404` if it does not exist.

#### `DELETE /sessions/{session_id}`
Deletes the transcript from disk. `409` if it is the conversation currently open —
what she already remembers from it is untouched either way.

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

### Stream Plan

What the owner wants Bea to get done on this stream. Every endpoint returns the
whole plan, so the dashboard never has to guess what the server now holds:

```json
{
  "directive": "today you play minecraft on the survival server",
  "objectives": [
    { "id": 1, "text": "build a base", "detail": "", "status": "todo",
      "outcome": "", "position": 1, "created_at": 0.0, "updated_at": 0.0 }
  ]
}
```

`status` is one of `todo`, `doing`, `done`, `dropped`. The `id` is also the
number Bea passes to `objective_done`.

#### `GET /plan`
Returns the current plan.

#### `POST /plan/directive`
Sets the headline. Body: `{ "text": "..." }` (empty clears it).

#### `POST /plan/objectives`
Adds an objective. Body: `{ "text": "...", "detail": "..." }`. Blank text is a
`422`.

#### `PATCH /plan/objectives/{id}`
Updates one objective. Body may carry any of `text`, `detail`, `status`,
`outcome`. An unknown status is a `422`; an unknown id is a `404`.

#### `DELETE /plan/objectives/{id}`
Removes an objective. Unknown id is a `404`.

#### `POST /plan/order`
Reorders the list. Body: `{ "ids": [3, 1, 2] }`.

#### `POST /plan/reset`
Clears the headline and every objective — a new stream from nothing.

---

### Overview

#### `GET /overview`

Everything the home screen needs in one request, so the dashboard does not fan
out to six endpoints on load.

```json
{
  "status": { "is_speaking": false, "is_sleeping": false, "active_skills": [],
              "session_id": "session_1750000000", "uptime": 1832.4 },
  "session": { "id": "session_1750000000", "title": "", "message_count": 12 },
  "plan": { "directive": "…", "total": 4, "closed": 1,
            "counts": { "todo": 2, "doing": 1, "done": 1, "dropped": 0 },
            "objectives": [ … ] },
  "skills": [ { "name": "memory", "enabled": true, "active": true } ],
  "memory": { "people": 3, "roster": 41, "memories": 512,
              "hot_facts": 2, "self_facts": 9, "rag_ready": true },
  "engine": { "llm_provider": "openrouter", "model": "…", "tts_provider": "kokoro",
              "stt_provider": "groq", "language": "en", "obs_connected": false }
}
```

---

### What she remembers

#### `GET /memory/overview`
The `memory` block above, on its own.

#### `GET /memory/people`
Every person card: names, identities, the facts she keeps, her attitude toward
them, and why they were promoted.

#### `GET /memory/roster?limit=60`
Every identity she has ever seen, newest first, with message and session tallies.
Most of these will never earn a card.

#### `GET /memory/self`
Her self-lore (`facts`), her `profile`, and the `hot_facts` that are true right
now and decay on their own.

#### `GET /memory/search?q=…&k=8`
The same semantic recall she runs on herself, returned split:

```json
{ "facts": [ { "text": "…", "who": "emanu", "source": "person",
               "similarity": 0.82, "created_at": 1750000000, "scope_key": "…" } ],
  "hers":  [ … ] }
```

`facts` is what people told her; `hers` is what she said herself. They are kept
apart deliberately — her persona invents on purpose, and her own output must
never come back as though it were true. `400` when the memory skill is off.

---

### Secrets and probes

#### `GET /secrets`
Which secrets are set, never their values:

```json
{ "openrouter_key": true, "openai_key": false, "discord.token": true }
```

#### `POST /test/llm` · `POST /test/tts` · `POST /test/obs`
Each returns `{ "ok": bool, "message": str, "detail": str }`. The LLM probe asks
for one word and reports the round trip, the TTS probe renders a line without
playing it, and the OBS probe reconnects.

#### `GET /audio/devices`
Output devices as `{ id, name, channels }`, so picking one is not guesswork about
an integer. Returns `[]` if `sounddevice` cannot enumerate them.

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
