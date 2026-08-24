# Monologue — the passage of time

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What it does

When nothing has happened for a while, Bea says something anyway — a streamer
filling dead air. "Time passed with nothing in it" is a first-class perception,
and she reacts to it the way she reacts to anything else.

**File:** `src/core/skills/idle.py`. It is 24 lines, because almost none of the
work belongs to the skill.

---

## How it actually fires

```
Consciousness.run()
    │
    ├─ idle skill active?   ──► bus.wait_or_idle(idle_after)
    │                             └─ nothing for `idle_after` seconds
    │                                → Perception(kind=IDLE, surface="idle")
    │
    └─ idle skill off?      ──► bus.drain()
                                  └─ blocks forever until something real happens
```

Two consequences worth knowing:

- **The timer is the gate.** The attention gate does not score an IDLE
  perception — the bus only emits one after `idle_after` seconds of true
  silence, so there is nothing left to decide. It only checks quiet hours, and
  drops it if she is meant to be asleep (`gate.py`, `idle:quiet-hours`).
- **With the toggle off she never self-triggers.** The loop blocks on
  `bus.drain()` instead, so nothing but a real input can wake her.

---

## What the skill contributes

Only the prompt rules, and only on a **pure-idle frame**:

```python
sections = [
    s.context_section for s in self.surfaces.active()
    if s.context_section and (s.name != "idle" or is_idle)
]
```

If a real message arrives in the same batch, the monologue rules are not
mounted at all — she answers the person instead of narrating to an empty room.
The rules live in `data/prompts/monologue.md` and say, in short: keep it short,
stay grounded, ask nobody anything, don't repeat yourself, and saying almost
nothing is fine.

The turn ends the way any turn ends — `speak`, or `stay_silent`.

---

## Configuration

The toggle is `skills.monologue.enabled`. The timing knob is **not** in that
block:

```json
"consciousness": {
  "idle_after": 240.0
}
```

| Key | Where | Default | Description |
|---|---|---|---|
| `enabled` | `skills.monologue` | `false` | Whether she may self-trigger at all |
| `prompt_path` | `skills.monologue` | `data/prompts/monologue.md` | The idle rules |
| `idle_after` | `consciousness` | `240.0` | Seconds of silence before an IDLE perception |
