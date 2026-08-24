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
| `live_state()` | `[RIGHT NOW]` — up to 6 live hot facts |

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

For every un-dreamed session the dreamer asks the background model to extract a
title, self-facts, per-person facts and hot facts, then writes them into the
live stores. Processed sessions are marked (`sessions.dreamed`), so re-dreaming
is a no-op.

It runs on the **`background`** pool, never the mind's: a dream pass is dozens
of calls in a row and must not take the mind's model — or its rate limit —
hostage.

> Waiting for the nightly dreamer would leave a regular a stranger all evening,
> which is why the [profiler](memory.md) also builds person cards and
> conversation summaries during the day, on a message count.

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
