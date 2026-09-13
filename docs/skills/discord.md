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
│      POST /discord/audio       voice heard in the call   │
│      POST /voice/transcript    overheard speech          │
│      POST /interrupt           barge-in                  │
│      WS   /voice/ws            her voice out, push       │
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
`VOICE` perception, and the request ends there. Her voice travels the other way,
over the `WS /voice/ws` push channel, whenever she decides to speak — so she can
answer, but she can also start, and every sentence of a turn reaches the room
rather than only the first.

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
├── classes/BrainLink.js   the push channel: her voice in, reports out
├── classes/PcmGain.js     volume ramps, and how much was really played
├── handlers/messages.js   mentions, replies, DMs -> POST /discord/chat
├── commands/              !hello, !join, !leave, !wl
├── whitelist.js           who may talk to her
└── utils/embed.js
```

**Express routes** (`api/server.js`): `GET /health`, `POST /send`,
`POST /reply`, `POST /typing`, `POST /react`, `POST /dm`, `POST /summon`,
`GET /voice/channels`, `POST /voice/join`, `POST /voice/leave`.

**Voice in:** per-user Opus stream → `prism-media` decoder → PCM → WAV →
`POST /discord/audio` → transcription → a perception. The request ends there.

**Voice out:** the mind → TTS → 48 kHz stereo PCM → `play` frames on
`WS /voice/ws` → `PassThrough` → `PcmGain` → `AudioPlayer`. Playback starts at
the first chunk, and the gain stage reports how many milliseconds actually
reached the room.

**Barge-in, in two stages.** People do two different things with the same
energy. After `duck_threshold_ms` of someone talking over her she drops to a
quarter volume without giving up the floor; if they stop there — a "sì sì", a
laugh — she comes back up and finishes the sentence. Only after
`interrupt_threshold_ms` does she fade out over 200ms and the bot call
`POST /interrupt`.

The bot then reports `played_ms`, and the next perception frame tells her where
she actually stopped:

```
[YOU WERE CUT OFF] You got as far as "allora la cosa che volevo" and stopped
there. Nobody heard the rest, so do not talk as if they did.
```

Without that line her history holds the whole sentence and she goes on
referring to a second half nobody heard — which reads as a bot far more than
any amount of latency does.

**Filling a silence.** A call that goes quiet is not a call that has nothing
left in it, and a bot that only ever answers is obviously a bot. The reflex
(`src/core/floor/`) watches the room on a clock of seconds and, after
`silence_seconds` (± `silence_jitter_seconds`, so it does not sound like the
timer it is), puts one perception on the bus marked `addressed: silence`.

It is a *door*, not a line: the mind decides whether there is anything worth
saying, and `stay_silent` remains a perfectly good answer. The reflex has no
memory, no persona and no words of its own — its output is an enum. Turn
`fill_silences` off and Bea is the same person with worse timing.

`unprompted_per_minute` is the number that sets her character: one is present
and discreet, three is the loudest person in the room.

**Whitelist:** in text, `access_mode` decides whether an unlisted person reaches
her at all. In voice she hears everyone in the channel — if you are in the room
she can hear you — but an unlisted voice arrives with its salience damped, the
same way an unlisted message does. Admin commands (`!wl add|remove|list`) are
restricted to `ADMIN_ID` and unauthorised calls are silently ignored.

---

## Configuration

```json
"discord": {
  "enabled": false,
  "token": "",
  "api_port": 3030,
  "brain_api_url": "http://127.0.0.1:8000",
  "admin_id": "",
  "duck_threshold_ms": 400,
  "interrupt_threshold_ms": 3000
}
```

| Key | Description |
|---|---|
| `token` | Bot token. Lives in `.env` as `DISCORD_TOKEN`; typing it in the dashboard writes it there, never into `config.json` |
| `api_port` | Port for the bot's Express API; passed to the subprocess as `PORT` |
| `brain_api_url` | Where the bot calls back into the brain |
| `admin_id` | Discord user id allowed to run `!wl` |
| `duck_threshold_ms` | How long someone talks over her before she drops her volume |
| `fill_silences` | Whether she may speak into a quiet call unasked |
| `silence_seconds` | How long the call stays quiet before the door opens |
| `silence_jitter_seconds` | Random spread on that wait |
| `silence_min_gap_seconds` | How long before she may fill another silence |
| `unprompted_per_minute` | Hard limit on speaking up unasked |
| `interrupt_threshold_ms` | How long someone must speak to interrupt her |

---

## Setup

1. Create a bot at [discord.com/developers](https://discord.com/developers/applications).
2. Enable **Message Content Intent**, **Server Members Intent**, and voice permissions.
3. Put `DISCORD_TOKEN` in `.env`.
4. `cd src/core/skills/voice/bot && npm install`
5. Toggle the skill on in the dashboard.

[Setup Guide →](../setup.md)
