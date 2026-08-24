# Stream Plan — what she has to get done today

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What it does

The owner writes what today is supposed to be, from the dashboard. It sits in
Bea's prompt until she has worked through it, and she closes the items herself
as she goes.

```
src/core/memory/plan.py          StreamPlan — the store
src/core/skills/plan/surface.py  StreamPlanSkill — context + three tools
src/web/frontend/src/pages/StreamPlanPage.jsx
```

It is a **core skill** (`skill_name = None`): always on, no toggle. With an
empty plan it contributes no rules, no state and no tools, so a feature nobody
uses costs nothing.

---

## What a plan is

A headline **directive** plus an ordered list of **objectives**:

```
[TODAY'S PLAN — set by your owner, not a suggestion]
today you play minecraft on the survival server
[x] #1 build a base — before dark (you said: it's ugly but it works)
[~] #2 find diamonds
[ ] #3 tour the server and say hi to people
```

`[ ]` todo · `[~]` doing · `[x]` done · `[-]` dropped

It goes in through `live_state()`, so it is in **every** prompt and always
current — it is what she is supposed to be doing, not an event that should make
her think.

**The number shown is the database id, and it is the same number she passes to
`objective_done`.** One identifier, nothing to map, nothing to get wrong.

---

## Tools

| Tool | Effect |
|---|---|
| `objective_started(objective)` | mark the one she is on now |
| `objective_done(objective, how)` | tick it off, with a line in her own words |
| `objective_dropped(objective, why)` | give up on one that genuinely cannot happen |

Each returns how many are left, so she knows where she is without re-reading the
list.

---

## What actually makes her act

Having the plan in her context is not enough on its own: on a quiet stream
nothing arrives to wake her up. The [Minecraft](minecraft.md) surface closes
that loop.

The game heartbeat is marked `noise`, so an idle server costs nothing. When the
body is standing still **and** an objective is still open, the surface emits one
perception instead:

```python
Perception(
    GAME, "game:mc",
    "Your body is standing still in Minecraft, doing nothing, and today's plan "
    "still has: #2 find diamonds. Give it something to do with play_minecraft…",
    meta={"addressed": "idle-body"},
)
```

`meta["addressed"]` is a general primitive: a sense that already knows a
perception is for her says so, and `is_addressed()` returns it verbatim. That is
what makes the nudge survive the attention gate — a nudge filed under "noticed"
is a nudge that never happened, and she would go straight back to waiting to be
spoken to.

It fires at most every `skills.minecraft.idle_nudge_seconds` (90 by default,
`0` disables it), and never when the plan is empty.

---

## Storage

Two tables in [`bea.db`](memory.md):

```sql
objectives (id, text, detail, status, outcome, position, created_at, updated_at)
settings   (key, value)          -- the directive lives here as plan.directive
```

Not a memory — an instruction she is given. It survives restarts, and
`POST /plan/reset` clears it for a new stream.

---

## The dashboard

The **Stream Plan** page reads and writes `/plan`, and re-reads it every five
seconds because Bea closes objectives herself while the stream runs.

The owner can also close, reopen, reorder and delete objectives — you are
watching the stream too, and it is faster than telling her.

See the [API reference](../web/api.md#stream-plan) for the endpoints.

---

## Scope

The plan reaches the **live loop**, not scoped conversation turns: it describes
what she is doing on stage. A directive like "answer everyone in Discord today"
will be visible to her on stage but not inside the Discord turn itself.
