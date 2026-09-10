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
    "mood": "neutral",
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
Receives a voice chunk from the bot's VoiceManager, transcribes it and deposits
a `VOICE` perception. It returns immediately: her voice reaches the call over
`/voice/ws`, whenever she decides to speak, which is what lets her open her
mouth without having been asked a question first.

**Request:** `multipart/form-data`
- `file` — WAV audio file
- `username` — Discord username
- `user_id` — stable Discord user id (optional, but it is the identity)
- `whitelisted` — whether the bot already knows this voice; a stranger arrives
  quieter instead of not arriving at all
- `listeners` — how many humans are in the call. At one, everything said is said
  to her and the attention gate stops rolling dice

**Response:** `{"status": "perceived", "transcript": "..."}`

The perception bus coalesces a burst of chunks into a single batch, so two
people talking at once produce one turn and one answer.

---

#### `WS /voice/ws`
The push channel: her voice out, playback reports back. The bot connects on
start-up and reconnects on its own, so a brain restart does not leave her mute.
It carries her actual voice over TCP, so it presents the same per-process
`API_TOKEN` as the bot's command API, as an `Authorization: Bearer` header.

**Brain → bot.** Audio is one self-contained binary frame,
`[uint32 header length][header json][pcm]`, where the payload is 48 kHz stereo
signed-16 little-endian — exactly what Discord plays, so the bot never has to
decode or resample. Control messages are JSON text:

| type | payload | effect |
|---|---|---|
| `play` | `utterance_id, seq, last` + pcm | queue and start playing at the first chunk |
| `stop` | `utterance_id, ramp_ms` | fade out and stop; answers with `played_ms` |
| `duck` | `utterance_id, gain, ramp_ms` | turn her down without stopping her |
| `cancel` | `utterance_id` | stop accepting more; what is queued plays out |

**Bot → brain**, JSON text:

| type | payload | meaning |
|---|---|---|
| `joined` | `channel_id, listeners` | she is in a call — being dragged in counts |
| `members` | `listeners` | someone came or went |
| `left` | — | she is out of the call |
| `playback` | `utterance_id, played_ms, state` | how much of it the room actually got |

> `played_ms` is the point of the whole exchange. Without it she believes she
> said a whole sentence the room only half heard, and refers to it later.

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
  { "role": "assistant", "content": "...", "mood": "neutral", "timestamp": "..." }
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

### The stage

What the OBS browser source reads, and what the dashboard asks about the avatar.
None of it is authenticated, so none of it ever carries a secret.

#### `GET /stage`
The page to point an OBS **Browser Source** at. `404` with "run `make frontend`"
when the frontend has not been built.

#### `GET /stage/stream`
Server-sent events for the browser source. **One snapshot first**, then patches:

```
data: {"type": "snapshot", "mood": "angry", "state": "talking", "caption": "..."}
data: {"type": "patch", "envelope": [0.02, 0.31, ...], "envelope_fps": 30}
```

Deliberately no backlog. OBS reloads a browser source whenever it is toggled,
and replaying what already happened would have her act out the last minute of
the stream again.

#### `GET /stage/config`
What the page needs to draw her: the two backends, the shot, the lip sync rate
and the caption's typography. Never a key, a token or a password.

#### `GET /stage/model`
The configured `.vrm`. `404` when none is set, or when it is set and missing —
the message names the path.

#### `GET /stage/clips` · `GET /stage/clips/{name}`
The behaviours installed, by name, and one `.vrma` each. A name that would walk
out of the clips folder is a `404`.

#### `GET /stage/preview`
**Query:** `mood`, `state` (`idle` by default). One avatar image, for the
preview in the dashboard. Only paths that appear in `avatar_map` are served —
anything else is a `404`, so the endpoint cannot be used to read the disk.

#### `POST /test/vts`
Whether she can reach VTube Studio. Returns the standard
`{ ok, message, detail }`, and reports a refused connection rather than raising.

#### `GET /vts/model`
The expressions and hotkeys of the model VTube Studio currently has loaded, so
the dashboard can offer them as a list instead of a text box.

---

## Frontend Static Serving

Two entry points are built from `src/web/frontend`: `index.html` (the dashboard)
and `stage.html` (the OBS browser source). They are separate bundles — the stage
does not carry React, the router or the dashboard, and three.js is loaded only
when the 3D backend is chosen.

`dist/assets/` is mounted as a `StaticFiles` route at `/assets`. Everything else
falls through to a catch-all `GET /{full_path}`, which serves a **real file** if
one exists under `dist/` (the favicon, `stage.html`) and otherwise returns
`dist/index.html` so the SPA can route it.

[Frontend Documentation →](frontend.md)
