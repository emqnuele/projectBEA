# Discord Skill

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What it does

Discord is Bea's voice and one of her text platforms. She can sit in a voice
call and talk, read and answer text channels, DM people, react, and decide on
her own to join a call or pull someone into one.

It is the only skill that needs a **second runtime**: Discord voice requires
`@discordjs/voice`, so a Node.js bot runs as a subprocess. Telegram and Twitch
are in-process precisely because they are text only. Discord encrypts voice
end to end (DAVE) and enforces it on voice channels, so the bot joins with
`daveEncryption: true` via `@snazzah/davey` — without it the bot shows up in
the channel but stays deaf and mute.

---

## The three pieces

```
src/core/skills/voice/
├── surface.py     VoiceSurface — the skill: senses, tools, prompt rules
├── transport.py   DiscordTransport — owns the node subprocess + its HTTP API
└── bot/           the Node.js bot (Discord.js)
```

`VoiceSurface` extends [`PlatformSkill`](overview.md#two-shapes-of-skill), so
building an `Author` and sending text is all it owes; perception building and
humanized delivery come from the base.

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

`BRAIN_API_URL`, `PORT`, `DISCORD_TOKEN`, `ADMIN_ID`, `DUCK_THRESHOLD_MS` and
`INTERRUPT_THRESHOLD_MS` are passed to the subprocess as environment variables
by `DiscordTransport.start()` (`src/core/skills/voice/transport.py`). The token is never written to `config.json` by
the dashboard — `GET /config` masks it.

If the bot process dies, `_watch_transport()` notices within two seconds and
brings it back after `restart_backoff`; a bot that never stays up for
`healthy_after` seconds is refusing to run rather than crashing, so after
`max_failed_starts` the surface says why once and goes inactive.

`start()` checks that `api_port` is free before spawning anything. The bot binds
that port only after it has logged into discord, so a port already in use — a
previous bot that outlived its brain, or a second copy of her — used to reach
the owner as a node stack trace, three restarts and a line blaming the token.

---

## Text and voice take different paths

**Voice** is the stage. A transcript arrives at `POST /discord/audio`, becomes a
`VOICE` perception, and the request ends there. Her voice travels the other way,
over the `WS /voice/ws` push channel, whenever she decides to speak — so she can
answer, but she can also start, and every sentence of a turn reaches the room
rather than only the first.

**Text** is not the stage. A message arrives at `POST /discord/chat`, becomes a
`CHAT` perception carrying `conversation_key = "discord:<channel_id>"`, and the
endpoint returns `{"status": "perceived"}` immediately. The message is read in
the one frame of the single loop and answered in writing via
`send_message(platform="discord", …)` or `react` — never out loud, because a
written channel has no `speak` tool.

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
| `discord_leave_voice()` | leave — armed only while she is actually in a call |
| `discord_summon(user_id, channel_id, text)` | DM someone an invite link — a bot cannot ring |

Every one goes through `DiscordTransport`, which returns `{"ok": bool, ...}` so
a failure becomes a clean observation Bea can react to rather than an exception.

Text written with any of these is delivered by the **humanizer**: one line per
message, with a typing indicator and a delay proportional to length. The mind
hands the answer over and carries on — the pauses are what make it read like
somebody typing, and they are not the loop's to sit through.

`discord_leave_voice` is in the schema only while `voice_channel` is set, and
the prompt only offers it then. That is one set of facts, not two: the toolbox
is assembled from the live skills on every read, so being dragged into a call
by somebody else arms the door exactly as joining one herself does.

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

**Who is in the call travels the other way.** `voiceStateUpdate` makes the bot
push `{type: "joined", channel_id, listeners}` on the socket, so the brain is
told rather than asking: `auto_leave_seconds` is checked every two seconds and
`GET /voice/channels` is not called at all on that path. With the socket down
the clock is held instead of run — walking out of a call full of people is
worse than sitting in an empty one a little longer.

Being dragged to another channel updates the tracked `channelId` and
re-announces; being kicked destroys the voice connection and reports `left`.
A dropped connection waits `DISCONNECT_TIMEOUT_MS` (5s) for the library to
move it back to `Signalling`/`Connecting` on its own — a transient blip keeps
the call — and only a connection still stuck in `Disconnected` afterwards is
destroyed and reported `left`, so Discord never keeps her sitting in a call
the brain thinks she left.

**Voice in:** per-user Opus stream → `prism-media` decoder → 48 kHz stereo PCM →
VAD gate + turn buffer → 16 kHz mono WAV → `POST /discord/audio` (or
`POST /voice/transcript`) → transcription → a perception. The request ends there.

### Voice input: turn segmentation

Discord exposes per-client transmit streams, not utterances. Segmentation is
implemented in `src/core/skills/voice/bot/classes/` as pure functions
(audio + clock in, decisions out). One `SpeechBuffer` + one `VoiceActivity` +
one downsampler per speaker.

**`VoiceActivity.js`** — frame classifier, 20 ms frames (`FRAME_MS`).

| Parameter | Default | Meaning |
|---|---|---|
| `SPEECH_LOW_HZ` / `SPEECH_HIGH_HZ` | `200` / `3400` | two-pole band-pass; `MIN_FOCUS` is the surviving-energy ratio |
| `MIN_FOCUS` | `0.32` | minimum in-band energy ratio to count as voice |
| `ENTER_OVER_FLOOR` / `EXIT_OVER_FLOOR` | `2.2` / `1.35` | relative level vs. per-speaker noise floor (hysteresis) |
| `ENTER_MARGIN` / `EXIT_MARGIN` | `200` / `100` | absolute level guards (digital-silence floor = 0) |
| `ONSET_MS` | `60` | sustained voice before `started` |
| `HANGOVER_MS` | `500` | sustained silence before `ended` |
| `MAX_VOICE_MS` | `15000` | continuous run released as non-voice (music/noise); floor set to run minimum |

Floor adaptation: learned from non-voiced frames only (`FLOOR_FALL = 0.25`
down, `FLOOR_RISE = 0.02` up); while speaking, only unvoiced frames above the
floor can raise it. `silence(ms)` (no packets received) advances the hangover
only, without touching the floor.

**`SpeechBuffer.js`** — per-speaker turn accumulator.

| Parameter | Default | Meaning |
|---|---|---|
| `PREROLL_MS` | `400` | pre-voice audio prepended at `started` |
| `MIN_SPEECH_MS` | `250` | minimum voiced audio, else `take()` returns `null` |
| `MAX_TURN_MS` | `30000` | turn cut and sent as-is |
| `duckMs` / `interruptMs` | from `duck_threshold_ms` / `interrupt_threshold_ms` | barge-in thresholds (overlap, see below) |

Turns are emitted after `HANGOVER_MS` of silence regardless of socket
boundaries. `take()` returns `{pcm, ms, voicedMs, overheard, interrupted}`.

A sweep looks at every speaker once a frame (`TICK_MS = 20`), so the end of a
turn is noticed within twenty milliseconds of the hangover. Packets arrive a
frame apart while somebody transmits, and a sweep landing between two of them
is not a silence: `gap()` only counts one once nothing has arrived for
`GAP_MS` (three frames), and then counts the whole of it, once.

**`Pcm.js`** — 48 kHz stereo → 16 kHz mono.

63-tap Hamming-windowed sinc low-pass, `CUTOFF_HZ = 6600`, applied before
3:1 decimation. Stateful per speaker; use one `createDownsampler()` instance
per stream so packet boundaries do not introduce discontinuities.

**Voice out:** the mind → TTS → 48 kHz stereo PCM → `play` frames on
`WS /voice/ws` → `PassThrough` → `PcmGain` → `AudioPlayer`. Playback starts at
the first chunk, and the gain stage reports how many milliseconds actually
reached the room. A line ends when the brain sends its last frame: the player
rides out up to `MAX_GAP_MS` (3 s) of waiting for the next sentence as
silence, rather than ending the utterance after its own default of a tenth of
a second.

**Barge-in, in two stages.** After `duck_threshold_ms` of overlapping speech
she ducks to 0.25 gain; after `interrupt_threshold_ms` she fades out over
200 ms and the bot calls `POST /interrupt`.

Both thresholds measure **overlap**: voiced milliseconds where both sides are
speaking, accumulated from `SpeechBuffer` `voicedMs` frames. The counter resets
when she stops, and unvoiced hold time (`HANGOVER_MS`) is excluded. Rationale:
she often starts answering mid-sentence, so total turn length would trigger on
the first frame.

The bot then reports `played_ms`, and the next perception frame tells her where
she actually stopped:

```
[YOU WERE CUT OFF] You got as far as "allora la cosa che volevo" and stopped
there. Nobody heard the rest, so do not talk as if they did.
```

Without that line her history holds the whole sentence and she goes on
referring to a second half nobody heard — which reads as a bot far more than
any amount of latency does.

### Echo suppression

Speakers recycle her output into a microphone input. The audio is already lost
at that point, so filtering is text-side in `src/core/skills/voice/echo.py`,
consumed by `VoiceSurface.perceive` (returns `None` on echo).

- Reference: `VoiceChannel.recent_texts()` (default `RECENT_SECONDS = 25.0`).
- Comparison: `plain()` + `overlap()` in `src/utils/text_match.py`
  (character-based; survives transcription edge errors and spaceless scripts).
- Thresholds: `MATCH = 0.72` minimum overlap ratio, `MIN_CHARS = 12` minimum
  normalized transcript length (short utterances are never dropped).

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
restricted to `ADMIN_ID`; unauthorised calls get a reply saying so, and a
stranger told they are not whitelisted learns their id and how to get in. The
list is runtime state and lives untracked in `data/discord_whitelist.json`, so
it never reads as local changes to the updater; an old
`src/core/skills/voice/bot/whitelist.json` is picked up once and migrated.

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
  "interrupt_threshold_ms": 4000
}
```

| Key | Description |
|---|---|
| `token` | Bot token. Lives in `.env` as `DISCORD_TOKEN`; typing it in the dashboard writes it there, never into `config.json` |
| `api_port` | Port for the bot's Express API; passed to the subprocess as `PORT` |
| `brain_api_url` | Where the bot calls back into the brain. An untouched value follows `--host`/`--port` (with `0.0.0.0` dialled back as `127.0.0.1`); a customized one always wins, and a mismatch with the running engine is logged at startup |
| `admin_id` | Discord user id allowed to run `!wl` |
| `duck_threshold_ms` | Overlapping voiced speech before ducking to 0.25 gain (default `400`) |
| `fill_silences` | Whether she may speak into a quiet call unasked |
| `silence_seconds` | How long the call stays quiet before the door opens |
| `silence_jitter_seconds` | Random spread on that wait |
| `silence_min_gap_seconds` | How long before she may fill another silence |
| `unprompted_per_minute` | Hard limit on speaking up unasked |
| `interrupt_threshold_ms` | Overlapping voiced speech before `POST /interrupt` (default `4000`). Overlap, not turn length — see [Barge-in](#the-bot) |

---

## Setup

1. Create a bot at [discord.com/developers](https://discord.com/developers/applications).
2. Enable **Message Content Intent**, **Server Members Intent**, and voice permissions.
3. Put `DISCORD_TOKEN` in `.env`.
4. `cd src/core/skills/voice/bot && npm install`
5. Toggle the skill on in the dashboard.

[Setup Guide →](../setup.md)
