# Social Memory — who people are

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What it does

Everyone Bea has ever seen gets a **tally**. Only the people who made themselves
matter get a **card**. That split is what lets her recognise a regular in a chat
of thousands without the prompt filling up with strangers.

```
src/core/skills/social/
├── social.py   SocialMemory — the per-batch hook and two tools
└── people.py   pure decisions: should_promote, promotion_reason
```

The storage is in [`bea.db`](memory.md): `identities`, `roster`,
`roster_sessions`, `people`, `facts`.

---

## The two tiers

**A tally** (`RosterEntry`) is a row of counters: how many messages, how much
donated, whether there was ever a 1:1, how many distinct sessions. It carries no
generated content, so it costs one INSERT per message and is affordable for
every chatter that ever types.

**A card** (`PersonCard`) is real memory: names across platforms, facts, and how
she feels about them. It is generated, so it is only worth minting for someone
who earned it.

```python
def should_promote(entry) -> bool:
    return (
        entry.donation_total > 0                              # money
        or entry.marked_by_bea                                # she decided to
        or entry.had_1on1                                     # a real 1:1
        or entry.session_count >= REGULAR_SESSION_THRESHOLD   # a regular (3+)
    )
```

`session_count` is `COUNT(*)` over `roster_sessions`, a join table rather than a
counter — "three distinct sessions" is what makes a regular, and a counter that
can double-count would mint cards for one-time visitors.

---

## The per-batch hook

`context_for(batch)` does three things at once, on every batch:

```
for each author in the batch (skipping the owner):
    ├─ meta["tallied"]?  ──► already counted by a high-volume surface, skip
    ├─ roster.record(...)     the sighting
    ├─ _maybe_promote(entry)  mints a card the moment the rule fires
    └─ collect their card

→ "[WHO YOU'RE TALKING TO]\n- **marco** (you: he's alright): builds redstone…"
```

Capped at `MAX_CARDS_INJECTED` people so a crowded room cannot take over the
prompt. Cards are injected rather than looked up, so she recognises whoever is
in front of her without spending a tool call to ask.

The `tallied` flag matters: [Twitch](twitch.md) counts every message itself,
including the ones the attention gate filtered out. Counting again here would
double them.

---

## Tools

| Tool | Effect |
|---|---|
| `remember_person(name, note, attitude)` | her own in-character decision. Always persists — if the platform never gave a stable id, a `named:<name>` identity is synthesized so the card exists anyway |
| `recall_person(name)` | what she knows. Falls back to the raw tally ("seen 12 times across 2 sessions") when there is no card |

`remember_person` is also offered inside a [scoped conversation
turn](../architecture.md#one-mind-two-clocks) — it is the one memory action that
makes sense while she is texting.

---

## Where cards come from

| Source | When |
|---|---|
| promotion | the rule above fires during a batch |
| donation | immediately, on the webhook — money does not wait for a dreamer |
| `remember_person` | she decided to |
| the [profiler](memory.md) | after ~20 of someone's messages, and refreshed rarely |
| the [dreamer](dream.md) | overnight, from the whole session |

Facts are capped per card (`MAX_FACTS_STORED`) and only the most recent are
shown, so a card that keeps growing never eats the prompt.

---

## Configuration

```json
"social_memory": { "enabled": true }
```

No other keys — the thresholds are constants in `store.py` and `people.py`
(`REGULAR_SESSION_THRESHOLD`, `MAX_FACTS_STORED`, `MAX_FACTS_SHOWN`), because
they are design decisions rather than settings.
