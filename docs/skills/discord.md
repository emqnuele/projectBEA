# Discord Skill

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What it does

Discord is Bea's voice and one of her text platforms. She can sit in a voice
call and talk, read and answer text channels, DM people, react, and decide on
her own to join a call or pull someone into one.

It is the only skill that needs a **second runtime**: Discord voice requires
`@discordjs/voice`, so a Node.js bot runs as a subprocess. Telegram and Twitch
are in-process precisely because they are text only.

---

## The three pieces

```
src/core/skills/voice/
├── surface.py     VoiceSurface — the skill: senses, tools, prompt rules
├── transport.py   DiscordTransport — owns the node subprocess + its HTTP API
└── bot/           the Node.js bot (Discord.js)
```

`VoiceSurface` extends [`PlatformSkill`](overview.md#two-shapes-of-skill), so
building an `Author` and sending text is all it owes; perception building,
humanized delivery and the scoped conversation tools come from the base.

---

## How the two processes talk

Both directions are HTTP over localhost.

```
┌──────────────────────────────────────────────────────────┐
│  Python — the brain                                      │
│                                                          │
│  VoiceSurface        senses ──► PerceptionBus            │
│      │                                                   │
│      └─ DiscordTransport ──► POST localhost:3030/...     │
│                              (send, reply, react, dm,    │
│                               typing, summon, voice/*)   │
│                                                          │
│  FastAPI endpoints the bot calls back into:              │
│      POST /discord/chat        text message              │
│      POST /discord/audio       voice, expects audio back │
│      POST /voice/transcript    overheard speech          │
│      POST /interrupt           barge-in                  │
└──────────────────────────────────────────────────────────┘
```

`BRAIN_API_URL`, `PORT`, `DISCORD_TOKEN`, `ADMIN_ID` and
`INTERRUPT_THRESHOLD_MS` are passed to the subprocess as environment variables
by `DiscordTransport.start()`. The token is never written to `config.json` by
the dashboard — `GET /config` masks it.

If the bot process dies, `_watch_transport()` notices within two seconds and
marks the capability inactive.

---

## Text and voice take different paths

**Voice** is the stage. A transcript arrives at `POST /discord/audio`, becomes a
`VOICE` perception, and the caller waits on a **correlation** for Bea's rendered
speech, which is handed straight back to the bot as base64 WAV.

**Text** is not the stage. A message arrives at `POST /discord/chat`, becomes a
`CHAT` perception carrying `conversation_key = "discord:<channel_id>"`, and the
endpoint returns `{"status": "perceived"}` immediately. The message is routed to
a [scoped conversation turn](../architecture.md#one-mind-two-clocks) that runs
beside the live loop: one turn at a time per channel, several channels at once.

A scoped turn has no `speak` tool, so a written message is answered in writing —
by construction rather than by a rule in the prompt.

**Overheard speech** (`POST /voice/transcript`) is a third path: it deposits a
perception and returns without waiting. The attention gate decides whether it
was worth reacting to.

---

## What she can do from the live loop

| Tool | Effect |
|---|---|
| `discord_send_message(channel_id, text)` | write in a channel unprompted |
| `discord_reply(channel_id, message_id, text)` | reply, quoting the original |
| `discord_react(channel_id, message_id, emoji)` | react with one emoji |
| `discord_send_dm(user_id, text)` | private message |
| `discord_list_voice_channels()` | who is in which call right now |
| `discord_join_voice(channel_id)` | go hang out |
| `discord_leave_voice()` | leave |
| `discord_summon(user_id, channel_id, text)` | DM someone an invite link — a bot cannot ring |

Every one goes through `DiscordTransport`, which returns `{"ok": bool, ...}` so
a failure becomes a clean observation Bea can react to rather than an exception.

Text written with any of these is delivered by the **humanizer**: one line per
message, with a typing indicator and a delay proportional to length.

---

## The bot

```
src/core/skills/voice/bot/
├── index.js               client setup, command loading
├── config.js              env-driven config
├── api/server.js          the Express API the brain calls
├── classes/VoiceManager.js voice connection, opus decode, playback, barge-in
├── handlers/messages.js   mentions, replies, DMs -> POST /discord/chat
├── commands/              !hello, !join, !leave, !wl
├── whitelist.js           who may talk to her
└── utils/embed.js
```

**Express routes** (`api/server.js`): `GET /health`, `POST /send`,
`POST /reply`, `POST /typing`, `POST /react`, `POST /dm`, `POST /summon`,
`GET /voice/channels`, `POST /voice/join`, `POST /voice/leave`.

**Voice pipeline:** per-user Opus stream → `prism-media` decoder → PCM → WAV →
`POST /discord/audio` → transcription → the mind → rendered speech → base64 back
→ `AudioPlayer`.

**Barge-in:** if a whitelisted user speaks for longer than
`interrupt_threshold_ms` while Bea is playing audio, the player stops and the
bot calls `POST /interrupt`.

**Whitelist:** only users in `whitelist.json` can trigger her. Admin commands
(`!wl add|remove|list`) are restricted to `ADMIN_ID` and unauthorised calls are
silently ignored.

---

## Configuration

```json
"discord": {
  "enabled": false,
  "token": "",
  "api_port": 3030,
  "brain_api_url": "http://127.0.0.1:8000",
  "admin_id": "",
  "interrupt_threshold_ms": 3000
}
```

| Key | Description |
|---|---|
| `token` | Bot token. Prefer the `DISCORD_TOKEN` env var — env always wins |
| `api_port` | Port for the bot's Express API; passed to the subprocess as `PORT` |
| `brain_api_url` | Where the bot calls back into the brain |
| `admin_id` | Discord user id allowed to run `!wl` |
| `interrupt_threshold_ms` | How long someone must speak to interrupt her |

---

## Setup

1. Create a bot at [discord.com/developers](https://discord.com/developers/applications).
2. Enable **Message Content Intent**, **Server Members Intent**, and voice permissions.
3. Put `DISCORD_TOKEN` in `.env`.
4. `cd src/core/skills/voice/bot && npm install`
5. Toggle the skill on in the dashboard.

[Setup Guide →](../setup.md)
