# Dream — sleep, self-lore, consolidation

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What it does

Three things that belong together because they are all about Bea knowing
herself:

- **self-lore** — what she has learned about *herself*, always in her prompt
- **hot facts** — a few "right now" things that decay on their own
- **the dreamer** — the offline pass that turns raw sessions into durable memory

```
src/core/skills/dream/
├── surface.py   DreamSkill — context, the morning pass, the nightly job
└── dreamer.py   Dreamer — the consolidation itself
```

Self-lore is separate from her **soul** (`data/prompts/soul.md`), which never
moves. The soul is who she is; self-lore is what she has picked up since.

---

## Always in context

| Hook | What it adds |
|---|---|
| `context_section` | `## ABOUT YOU` — up to 15 self-facts, capped so a growing lore never takes over |
| `live_state()` | `[HOT FACTS]` — up to 6 live hot facts |

`[RIGHT NOW]` belongs to the clock alone (`ClockSkill`): the day, the time and
the configured zone. Hot facts used to reuse the same header, so every briefing
carried two of them.

Hot facts have a TTL and prune themselves: an expired row is simply not
selected, so there is no sweeper job.

---

## The morning pass

Runs once at startup, after `clear_source("morning_pass")` so it never
accumulates. It derives volatile facts she would otherwise have no way to know:

- how many days until her birthday (from the structured `self_profile`)
- how long it has been since the last session
- a line or two from yesterday

---

## The nightly dream

```python
while self.active:
    await asyncio.sleep(300)
    if now.hour != hour or last_dreamed_on == now.date():
        continue
    await self.run_dream()
```

The **hour is checked** rather than a timer being set, so restarting the process
neither skips a night nor doubles one.

Two dates are kept in `settings`. `dream.last_night` is the nightly guard and is
only written by the nightly job, so a nap after midnight does not stand in for
the night. `dream.last_dream` is written by every successful pass, nightly or
not; the dashboard shows the later of the two.

For every un-dreamed session the dreamer asks the background model to extract a
title, self-facts, per-person facts and hot facts, then writes them into the
live stores. Processed sessions are marked (`sessions.dreamed`), so re-dreaming
is a no-op.

A reply that carries none of the expected keys — an error, an empty object, or
some other JSON the parser found in the reply — is not a consolidation. The
session stays un-dreamed and the next pass tries it again; after
`MAX_DREAM_ATTEMPTS` (3) unusable replies (`sessions.dream_attempts`) it is
marked done and logged as an error, so a session that always fails does not
cost a call every night.

**Self-facts** are what is now true about her own life — something that
happened to her, a decision, something she learned about her own world — and
never her character, which is the soul's. The pass is shown the self-facts she
already has (the newest `MAX_KNOWN_SELF_FACTS`) above the transcript, so a night
does not write the same thing again in new words.

**People** are resolved against the stream, which records which account said
each line. A name that exactly one account spoke under in that session resolves
to that account's card (`card_for_identity`): the card the live prompt reads.
A name nobody spoke under — someone talked about — goes through the name path
(`record_person`), which only mints a card at the usual thresholds.

**The diary** is a phase of the pass. Every session the dreamer read with
something said in it gets its page from the [memory](memory.md) skill, awaited
before she wakes (`MemorySkill.write_pages`). Pages that already exist are
skipped.

It runs on the **`background`** pool, never the mind's: a dream pass is dozens
of calls in a row and must not take the mind's model — or its rate limit —
hostage.

> Waiting for the nightly dreamer would leave a regular a stranger all evening,
> which is why the [profiler](memory.md) also builds person cards during the
> day, on a message count. Per-conversation continuity needs no such pass:
> the dreamer keeps one recap per conversation key, and the morning reads
> those back.

---

## Sleeping

| Tool | Effect |
|---|---|
| `go_to_sleep(reason)` | she stops reacting, the avatar switches to `sleeping`, the dreamer runs, then she wakes |

While asleep the consciousness loop still drains the bus and frees any waiting
HTTP caller — it just does not think about any of it.

The dashboard's Activity page can trigger the same pass (`POST /dream/run`) and
wake her (`POST /dream/wake`).

---

## Configuration

```json
"dream": {
  "enabled": true,
  "hour": 4
}
```

| Key | Default | Description |
|---|---|---|
| `hour` | `4` | Local hour at which the nightly consolidation runs |

The dreamer needs the [social](social.md) skill, a background model and the
history manager. If any is missing it logs a warning and stays unwired rather
than failing at startup.
