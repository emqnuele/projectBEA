# Twitch Skill

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What it does

Reads a Twitch channel's chat and lets Bea talk to it. Chat is not a
conversation she is having — it is the room she is standing in, so she answers
it **out loud**, from the stage, and only types into it when she means to.

```
src/core/skills/twitch/
├── surface.py  TwitchSkill — tally, texture, one tool
└── irc.py      raw IRC over asyncio; the parsing half is pure
```

---

## Volume is the whole problem

At thirty messages a minute, one reasoning cycle per message is unaffordable and
also not what a streamer does — a streamer reads chat as a texture and picks out
the lines that are for them. So the skill splits chat in two:

**Every message is tallied.** One INSERT into the roster, cheap enough for
thousands of chatters, whether or not it ever reaches the mind. That is what
makes a regular a regular, and it happens before the gate sees anything.

**Almost none of them wake her.** Messages are deposited at `salience=0.4`
(0.9 for cheers), so only her name, a hot name, or the gate's presence score
pulls her in. Everything else is filtered out.

**The rest becomes texture.** `pulse()` renders one line — how many messages a
minute chat is doing and what it keeps saying — from an in-memory deque, with no
model call. It is in `live_state()`, so it is in every prompt and costs nothing:

```
TWITCH CHAT (#channel): ~34 msg/min, mostly saying: KEKW, lag, ferrari
```

She is continuously aware of chat without ever deliberating over it.

---

## Cheers are money

A cheer carries `bits`, which the surface converts into `Author.extra["amount"]`.
`is_addressed` treats any author with an amount as a **donation**, which is an
unconditional react — past the cooldown, past quiet hours. It also promotes the
person to a card immediately, so the next thing she says already knows who they
are.

---

## Reading works with no credentials

`irc.py` speaks raw IRC over asyncio — the protocol we need is a dozen lines, so
a client library would only drag in another HTTP stack. Read-only works
**anonymously** (`justinfan<random>`, no password), so you can follow chat with
nothing configured but the channel name.

A token is only needed to write back. Without one, `twitch_say` fails cleanly
and she is a listener.

The connection half reconnects and answers PINGs; the parsing half is pure and
tested against captured lines.

---

## Tools

| Tool | Effect |
|---|---|
| `twitch_say(text)` | type into the channel. Needs `oauth_token` |

There are no scoped conversation tools: `scoped_conversations = False` puts
every Twitch message on the stage.

---

## Configuration

```json
"twitch": {
  "enabled": false,
  "channel": "",
  "nick": "",
  "oauth_token": ""
}
```

| Key | Description |
|---|---|
| `channel` | Channel to join, without the `#` |
| `nick` | Her account name. Leave empty to read anonymously |
| `oauth_token` | Only needed to write. Prefer the `TWITCH_OAUTH_TOKEN` env var |

Trigger words come from `attention.trigger_words`.

---

## Setup

1. To only read: set `channel` and toggle the skill on. Nothing else.
2. To also write: get an OAuth token for the account (`oauth:...`), put it in
   `.env` as `TWITCH_OAUTH_TOKEN`, and set `nick` to that account's name.
