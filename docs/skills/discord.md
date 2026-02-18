# Discord Skill

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What It Does

The Discord Skill connects Bea to a Discord server. She can:
- **Listen in a voice channel** — receive live speech from whitelisted users
- **Transcribe and respond** — speech is transcribed via Groq Whisper and sent to the brain
- **Speak back** — the TTS audio is streamed back into the voice channel in real time
- **Interrupt/barge-in** — if a user speaks while Bea is talking, she detects it and stops

The skill works as two coordinated processes:
1. **Python skill** (`discord_skill.py`) — manages the Node.js subprocess lifecycle
2. **Node.js bot** (`src/modules/skills/discord/bot/`) — handles Discord.js voice connection and audio I/O

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Python (AIVtuberBrain)                                      │
│                                                              │
│  DiscordSkill (Python)                                       │
│      ├─ starts Node.js process via subprocess.Popen          │
│      └─ monitors process health via poll()                   │
│                                                              │
│  FastAPI endpoints:                                          │
│      POST /discord/chat    ← text messages from bot          │
│      POST /discord/audio   ← voice audio chunks from bot     │
└──────────────────┬───────────────────────────────────────────┘
                   │ HTTP (localhost:8000)
┌──────────────────▼───────────────────────────────────────────┐
│  Node.js Discord Bot (index.js)                              │
│                                                              │
│  VoiceManager.js                                             │
│      ├─ joinVoiceChannel() — connects to voice               │
│      ├─ opusDecoder → WAV chunks → POST /discord/audio       │
│      ├─ receives base64 audio response                       │
│      └─ createAudioPlayer() → plays back Bea's speech        │
│                                                              │
│  Express API (port 3030)                                     │
│      POST /send            ← Python can push text to Discord │
└──────────────────────────────────────────────────────────────┘
```

---

## Python Side: `DiscordSkill`

**File:** `src/modules/skills/discord/discord_skill.py`

### `initialize()`
- No-op implementation — performs no setup work at registration time. All initialization (token validation, process spawn) happens lazily inside `start()`.

### `start()`
- Reads `DISCORD_TOKEN` from config or env var.
- Checks that `node_modules` is installed in the bot directory.
- Spawns the Node.js process via `subprocess.Popen(["node", "index.js"])`.
- Forwards stdout/stderr directly to the Python console.

### `stop()`
- Kills the process with `bot_process.kill()` + `taskkill /F /T /PID` (Windows).

### `update()`
- Polls the process on every SkillManager tick — if it exited unexpectedly, marks the skill as inactive.

### `send_message(channel_id, content)` → `bool`
- Async helper that pushes a text message to a Discord channel via the bot's internal Express API (`POST /send` on `localhost:{api_port}`).
- Returns `True` on success, `False` if the bot is offline or the request fails.
- Used when Python-side code needs to post a message directly to Discord (e.g. for notifications or replies from non-voice endpoints).

---

## Node.js Bot

**Directory:** `src/modules/skills/discord/bot/`

```
bot/
├── index.js              Entry point — Discord.js client setup, command loading
├── package.json          npm dependencies
├── whitelist.json        Allowed user IDs (auto-created if missing)
├── classes/
│   └── VoiceManager.js   Core voice logic
├── commands/
│   ├── admin/            Admin-only slash commands
│   ├── general/          General slash commands
│   └── voice/            Voice channel commands (join, leave, etc.)
└── utils/
    └── embed.js          Discord embed helpers
```

### `VoiceManager.js`

The heart of the voice integration:

| Feature | Implementation |
|---|---|
| Join channel | `joinVoiceChannel()` from `@discordjs/voice` |
| Audio receive | Opus stream per user → `prism-media` decoder → PCM |
| VAD / interruption | Frame counter threshold: if a user has spoken for `INTERRUPT_THRESHOLD_MS` ms while Bea is playing audio, stop the player and send `/interrupt` to the Python API |
| Send audio | PCM buffer written to WAV → `FormData` → `POST /discord/audio` |
| Play response | Response base64 audio → `Readable` stream → `AudioPlayer` |

### Whitelist System

Only users in `whitelist.json` can trigger voice responses. Admin commands manage the list via Discord prefix commands (see below).

---

## Bot Commands

The bot uses the `!` prefix for all commands. Commands are loaded dynamically from the `commands/` directory, split by category.

### Access Control

| Category | Who can use it |
|---|---|
| `admin` | Owner only (hardcoded `ADMIN_ID` in `index.js`) |
| `general` / `voice` | Whitelisted users only |

Unauthorised calls are **silently ignored** — no error is shown.

---

### General Commands

#### `!hello`
**Access:** Whitelisted  
Bea greets the user with an embed message showing her avatar.

```
!hello
→ Embed: "Hi there, <username>! I am Bea."
```

---

### Voice Commands

#### `!join`
**Access:** Whitelisted  
Bea joins the voice channel the user is currently in.

```
!join
→ Bea connects to your current voice channel and starts listening.
```

> The user **must be in a voice channel** for this to work. If not, an error embed is returned.

#### `!leave`
**Access:** Whitelisted  
Bea disconnects from the current voice channel.

```
!leave
→ Bea disconnects and stops listening.
```

---

### Admin Commands

All admin commands are restricted to the hardcoded `ADMIN_ID` in `index.js`. They manage the `whitelist.json` file.

#### `!wl add <userId>`
Add a user to the whitelist. You can mention the user (`@username`) or paste their ID directly.

```
!wl add @username
!wl add 123456789012345678
→ User added to whitelist.
```

#### `!wl remove <userId>`
Remove a user from the whitelist.

```
!wl remove 123456789012345678
→ User removed from whitelist.
```

#### `!wl list`
Show all currently whitelisted users as a Discord embed.

```
!wl list
→ Embed: 📜 Whitelisted Users
         - @username (123456789012345678)
         - ...
```

---

### Text Chat (Mention / Reply / DM)

Beyond prefix commands, the bot also listens for **conversational messages** from whitelisted users:

| Trigger | Example |
|---|---|
| Mention Bea in a server | `@Bea how are you?` |
| Reply to one of Bea's messages | Reply to any message Bea sent |
| Send a DM to the bot | Direct message — always accepted |

When triggered, the bot:
1. Sends a `typing...` indicator
2. Strips Bea's mention from the text
3. Resolves the best display name (guild nickname → global display name → username)
4. POSTs to `POST /discord/chat` on the Python brain
5. Replies inline with Bea's text response

> Note: text-chat replies do **not** trigger OBS animation or TTS. Only `/discord/audio` voice interactions produce visual output.

---

## Audio Pipeline Detail

```
Discord Opus stream (per user)
    │
    ▼ prism-media OpusDecoder (Node.js)
PCM raw (16-bit, 48kHz, 2ch)
    │
    ▼ accumulated into buffer
    │  (silence detected → flush)
    ▼
WAV file (temp)
    │
    ▼ POST /discord/audio (multipart: file + username + flush_buffer)
    │                                                    [Python]
    ▼ STT.transcribe(wav) → transcript
    │
    ▼ Buffer aggregation window (300 ms)
    │   All speakers whose audio arrives within BUFFER_WINDOW of each other
    │   are merged into a single LLM context. The LLM is called only once.
    │
    ▼ generate_response(combined_text) → (mood, message)
    │
    ▼ TTS.generate_audio(message) → numpy array → WAV bytes → base64
    │
    ▼ _perform_visual_only_task(mood, message, duration)
    │   └─ Animates OBS avatar + text bubble WITHOUT local audio
    │      (audio plays in Discord; OBS shows talking pose)
    │
    ▼ JSON response to Node.js:
    │   {
    │     "status": "success" | "resume",
    │     "text": "Bea's response text",
    │     "transcript": "combined transcript log",
    │     "audio_base64": "<base64-encoded WAV bytes>"
    │   }
    ▼
Node.js: decode base64 → Readable stream → AudioPlayer.play()
Discord voice channel output
```

> For simultaneous speakers, only the **first** caller in the buffer receives the audio. All others receive `"(Merged)"` as the text response and empty audio bytes.

> **All-backchannel flush:** If every input within the 300 ms aggregation window is detected as a backchannel (e.g. all users said "ok", "yeah"), the buffer is short-circuited: no LLM call is made, no TTS is generated, and all futures are resolved immediately with `status: "resume"` and empty audio. The engine resumes any in-progress `resume_buffer` speech autonomously without involving the LLM.

---

## Text Chat Mode

Non-voice messages in the target channel are forwarded to `POST /discord/chat`:

```json
{ "username": "emanu", "message": "hello bea", "channelId": "..." }
```

The endpoint prepends the username as a prefix before calling the brain, so the conversation history entry becomes `[emanu] hello bea`. The brain generates a text response and the bot posts it back to the channel.

> **No OBS animation for text-chat:** Unlike `POST /chat`, the `/discord/chat` endpoint does not schedule `perform_output_task()`. OBS avatar animation and text-bubble overlay are **not** triggered for Discord text-channel messages — only voice interactions (via `/discord/audio`) produce visual output.

---

## Configuration

```json
"discord": {
  "enabled": false,
  "token": "",
  "target_channel": "",
  "api_port": 3030,
  "interrupt_threshold_ms": 3000
}
```

| Key | Description |
|---|---|
| `enabled` | Toggle the skill at runtime |
| `token` | Discord bot token (or set `DISCORD_TOKEN` env var) |
| `target_channel` | Name of the voice channel Bea should monitor |
| `api_port` | Port for the bot's internal Express API (default: `3030`). Must match `PORT` env var passed to the Node.js process. |
| `interrupt_threshold_ms` | How long a user must speak before interrupting Bea |

---

## Setup

1. Create a Discord application and bot at [discord.com/developers](https://discord.com/developers/applications).
2. Enable: **Message Content Intent**, **Server Members Intent**, **Voice** permissions.
3. Set `DISCORD_TOKEN` in `.env`.
4. Run `npm install` in `src/modules/skills/discord/bot/`.
5. Enable the skill in `config.json`.

[Setup Guide →](../setup.md)
