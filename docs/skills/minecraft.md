# Minecraft Skill

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What it does

Bea has a body on a Minecraft server. She plays alongside other people: she
reads game chat, answers it, recognises the players across sessions, reacts to
being hit or killed, and pursues goals she sets for herself.

She does not pilot the body block by block. She gives it an **intention** and it
goes and does it while she carries on talking. The body is a loop that runs for
as long as the skill is on: it idles for free when it has no goal, works when it
has one, and never needs starting again.

```
src/core/skills/minecraft/
├── surface.py   MinecraftSurface — the senses, and 7 tools for the mind
├── agent.py     GameAgent — the body's endless loop
├── goal.py      one intention, and how far the body has got with it
├── context.py   the body's own sliding window
├── client.py    WebSocket bridge to the mod
├── state.py     the state packet, rendered as a few readable lines
├── tools.py     26 game tools, for the body
└── notebook.py  the body's private scratchpad
```

---

## Two minds, two models

```
┌─ the mind ─────────────────────────────────────────────┐
│ mind model · personality, chat, voice                  │
│ 7 tools: play_minecraft, mc_chat, mc_stop,             │
│          mc_goto_player, mc_follow_player,             │
│          mc_look_at_player, mc_give_item               │
│ sees: the game state, milestones, player chat          │
└────────────────────┬───────────────────────────────────┘
                     │  play_minecraft("get a stone pickaxe")
┌────────────────────▼───────────────────────────────────┐
│ the body — GameAgent, one loop that never ends         │
│ 28 tools + the survival guide + the notebook           │
│ think → act → observe, paced, re-reading the world     │
│ reports back: milestones, and how the goal ended       │
└────────────────────┬───────────────────────────────────┘
                     │  WebSocket ws://127.0.0.1:8080
┌────────────────────▼───────────────────────────────────┐
│ Minecraft + the BeaCraft mod                           │
└────────────────────────────────────────────────────────┘
```

The body runs on the **`minecraft`** pool, which falls back to **`mind`** when
nothing is configured for it. Playing well is reasoning — working out that a
pickaxe needs sticks, that the iron is under the lava, that this cave is a dead
end — and a body on a cheap model spends its steps failing at exactly that. Put
something smaller in `models.minecraft` if you would rather trade play for cost.

`play_minecraft` sets the goal and returns immediately. It does not wait for the
goal to finish, because the goal may never finish: it is a direction, not an
errand. One goal at a time — a new one replaces the old the moment she says it.

---

## What reaches her, and what does not

The mod streams a lot. Most of it is filtered before it costs a thought.

| Packet | What she gets |
|---|---|
| state snapshot, nothing happening | `noise` — dropped by the gate. It is already in `live_state()` |
| state snapshot with events | a `GAME` perception |
| `INTERRUPTED` | declared in `meta`, so the gate always lets it through |
| chat from a player | a `CHAT` perception with a real `Author`, on the stage |
| join / leave | a `CHAT` perception |
| combat | `GAME`; a hit **by a player** is a social event, at higher salience |
| death | `GAME` at salience 1.0, with cause, coordinates and what she dropped |
| a body milestone | `GAME` — only for tools whose outcome is a real step forward, and at most one every 8s |
| the goal finished | `GAME`, declared addressed: what it got, and a nudge toward the next thing |
| the goal got stuck | `GAME` at 0.9, declared addressed: nothing moves the body until she answers |
| the body working, every `commentary_seconds` | `GAME`, declared addressed: what it is doing and what it last thought |

The game state itself lives in `live_state()` rather than in a perception: it is
*where she is*, always true, not an event that should make her think. `state.py`
renders it as a handful of lines — health, position, what she is holding and
wearing, what is craftable, what is nearby, what she is standing on, who is
around — instead of the raw packet.

Every block the mod names arrives with the coordinates and distance it was seen
at, nearest first, because `mine_block`, `place_block` and `use_block` all
require an exact coordinate and a model that is shown a tally can only invent
one. The list is capped per kind, so a row of torches cannot spend the budget
and hide the ore behind it. The bulk census, the block underfoot and the block
overhead come from the mod as well: standing on air is how the body learns it
is falling.

---

## The social stack comes free

`_on_chat` builds an `Author` from the player's UUID. Everything above that —
the roster tally, promotion to a [person card](social.md), the facts injected
when they are nearby, `remember_person`, the [attention gate](../architecture.md#attention) —
is keyed on `Author`, so it all works in-game with no Minecraft-specific code.

Standing next to her and talking counts as talking **to** her: a chat line with
`distance <= 6` blocks is addressed, and bypasses her cooldown.

---

## Two audiences

`speak` is her voice — the stream hears it, the players do not. `mc_chat` is
what she types in game — the players read it, the stream sees it scroll past.

Using both in one turn is usually right: the funny thing out loud, the useful
thing in chat.

---

## Speaking without being spoken to

The heartbeat is marked `noise`, so an idle server costs nothing — and it also
means nothing in the game ever makes her open her mouth by itself. Two
perceptions do. The surface emits at most one per tick, and which one depends
on whether the body is busy.

**While the body works** — every `commentary_seconds` (20 by default) she gets
a line saying what the body is doing, how long it has been at it, and the last
thing it thought, and asking her to say something rather than to decide
something. It explicitly tells her *not* to hand out a new goal, because a new
goal replaces the running one.

This is what stops her from going quiet for the length of a mining trip. The
body reasons in prose at every step; `GameAgent` keeps the freshest line in
`last_thought` and the surface reads it when it asks her to talk. Milestones
are still the only thing that interrupts her *out of turn* — commentary waits
for its slot.

**While the body stands still** — the [stream plan](plan.md) is what gets her
moving. With an objective still open, the surface says so at most every
`idle_nudge_seconds` (90 by default), and she answers by handing the body a
goal. With an empty plan there is no nudge at all: she reacts to whatever
happens without setting out to do anything.

This is now only ever about *direction*. The body does not stop because it ran
out of loop, so a silent body is a body with nothing to do — and that is the
one thing she has to supply.

Both declare themselves addressed, so the gate always lets them through, and
both take `0` to turn off.

**And on demand** — `POST /minecraft/ask`, the *What are you doing?* button on
the [Stream Plan](plan.md) page, puts the same commentary perception on the bus
immediately and pushes the next automatic one back. It is the one nudge that
works with the body standing still too, because that is a fair question to ask
of someone standing around. Deliberately the same perception rather than a
second kind of prompt: the button and the clock cannot drift apart.

Neither one is free: each is a turn on her own model. `commentary_seconds` is
the knob that decides how present she is and how much she costs, and it is the
same trade either way.

---

## The body's loop

```python
GameAgent.run()                      # started with the skill, stopped with it
    └─ while alive
         ├─ no goal → wait on an Event (no model call, no cost)
         └─ a goal  → one round:
                ├─ every REFRESH_EVERY steps: fresh GAME STATE + the notebook
                ├─ model call → tool calls → mod commands → observations
                ├─ goal_done / goal_blocked → the goal closes, she is told
                └─ out of steps, or failing the same way → stuck, she is told
```

**It re-reads the world.** The state is re-injected every third step, and the
previous snapshot is dropped rather than kept: state from nine steps ago is not
history, it is a wrong answer to *where am I*. Before this the body was handed
the world once and then played blind, which is why it walked back into lava it
had already climbed out of.

**Its window is bounded.** `context.py` keeps the rules, the goal and the last
`body_context_rounds` rounds, and trims whole rounds rather than messages — a
`tool` message whose `tool_calls` were trimmed away is a malformed conversation
that most providers reject outright.

**The notebook** (`notebook.py`) is the body's working memory: one freeform blob
the model rewrites in full via `update_notebook`. It is the only thing a trim
cannot take, which makes it the body's long-term memory rather than a scratchpad.

**A goal ends when the body says so**, through `goal_done(summary)` or
`goal_blocked(reason)`. It used to end when the model stopped calling tools —
which is also what a model does when it is confused, or answers in prose. Those
are not the same event, and the mind was being told they were. Prose now costs
a round and earns a correction.

**A goal it was asked to prove is checked against the world.** `play_minecraft`
takes an optional `have` — `{"iron_ingot": 5}` — and `goal_done` is refused
while the inventory disagrees, answering with the count it is short of rather
than closing the goal. The body cannot talk its way to `done`; only the state
the mod last sent can get it there. A request matches an item by its kind, so
`log` is satisfied by oak and birch together, while `stone` is not satisfied by
a stone pickaxe. Goals with no `have` close on the body's word, which is the
right behaviour for *build a shelter* and the wrong one for *get five iron*.
`goal_blocked` is never checked: that is the body reporting the world, not
claiming an achievement.

**It gives up rather than grinding.** `steps_per_goal` rounds, or five rounds in
a row where every call failed, and the goal is `stuck`: the body stops and hands
the problem to her. The loop itself keeps running.

**She can borrow it.** `mc_goto_player` and friends suspend the goal, use the
body, and hand it back with a line saying it was taken away. Turning to look at
someone who said hello no longer costs her the house she was building.

**Milestones** are the only thing that *interrupts* the mind mid-goal — the
commentary nudge waits its turn instead. Movement and looking are means, not
results; `craft_item`, `mine_block`, `place_block`, `smelt_item`, `find_block`,
`equip_item`, `store_item`, `retrieve_item`, `attack_entity` and `give_item`
produce one when they succeed or fail badly. An interrupt or a death always
does. The same line twice is never sent twice, and two never arrive within
8 seconds of each other.

---

## Tools

**The mind's seven:**

| Tool | Effect |
|---|---|
| `play_minecraft(goal, have)` | hand the body something to achieve, and what it has to be holding for that to count |
| `mc_chat(message)` | type in game chat |
| `mc_stop()` | put the body down |
| `mc_goto_player(name)` | walk over to someone |
| `mc_follow_player(name)` | tag along until she stops |
| `mc_look_at_player(name)` | make it obvious she noticed |
| `mc_give_item(name, item, count)` | walk over and drop it at their feet |

**The body's own two:** `goal_done(summary)` and `goal_blocked(reason)` — the
only two ways a goal ends.

**The body's twenty-six:** `mine_block`, `attack_entity`, `move_to`,
`stop_moving`, `request_screenshot`, `look_at`, `place_block`, `select_slot`,
`find_block`, `pillar_up`, `mine_down`, `bridge`, `craft_item`, `use_block`,
`smelt_item`, `store_item`, `retrieve_item`, `equip_item`, `discard_item`,
`eat_food`, `check_death_log`, `goto_player`, `follow_player`, `look_at_player`,
`give_item`, `chat` — plus `update_notebook`.

Every tool awaits the mod's answer to it, so the observation the model reasons
on is what actually happened: `RESULT: sentence`, followed by the last lines of
the action's own log when it sent one. `chat`, `check_death_log`,
`request_screenshot` and `look_at` run beside whatever the body is doing and are
answered at once; they never stop it. How long the brain waits depends on the
action (`ACTION_TIMEOUTS` in `tools.py`), and is always longer than the mod's own
budget for it, so the mod gives up first and says why.

---

## The mod

**BeaCraft** is a client-side Fabric mod (Minecraft 26.x, Java 25). It drives the local
player by simulating input and sends ordinary packets, so to a server it looks
like a normal client — nothing is required server-side, and it works on vanilla.

| Source | Link |
|---|---|
| Modrinth | [modrinth.com/project/projectbea](https://modrinth.com/project/projectbea/) |
| GitHub | [Latest release](https://github.com/emqnuele/projectbea/releases/latest) |

1. Install [Fabric Loader](https://fabricmc.net/use/installer/).
2. Drop the jar into `.minecraft/mods/`.
3. Launch Minecraft — the mod opens a WebSocket on `ws://localhost:8080`.
4. Make sure `server_url` matches, and toggle the skill on.

> The mod listens on loopback (`127.0.0.1`) unless `host` in
> `config/beacraft.json` says otherwise, and has no authentication: only open it
> to a trusted network.

### Protocol

The mod announces itself on connect: `protocol`, `mod_version`, `mc_version`,
the `actions` it has, and which of them are `concurrent`. The brain speaks
protocol 2.

**Brain → mod:**

```json
{ "id": "r41", "action": "mine_block", "parameters": { "x": 100, "y": 64, "z": 100 } }
```

**Mod → brain.** Dispatch is on `type` first, then `status`:

| Field | Value | Meaning |
|---|---|---|
| `type` | `chat`, `player_event`, `combat`, `death_event` | a sense; handed to the surface |
| `type` | `reflex` | the body acted on its own: `reflex` is `eat`, `defend`, `clutch`, `unstuck` or `respawn`, `event` is `started`/`finished`, `interrupted_id` names the request it cut short |
| `status` | `FINISHED` | the answer to request `id`: `result` (`SUCCESS`, `FAILURE_<CODE>`, `INTERRUPTED`), `message`, optional `log`, `details`, and `reason` when interrupted |
| — | `type: game_state` | a game-state snapshot, once a second |

```json
{"status": "FINISHED", "id": "r41", "action": "move_to", "result": "INTERRUPTED",
 "message": "interrupted (self_defence: Zombie)", "reason": "self_defence: Zombie"}
{"type": "reflex", "reflex": "defend", "event": "started",
 "message": "defending against Zombie after taking 2.0 damage", "interrupted_id": "r41"}
```

Every request is answered exactly once, with its own `id`, however it ends:
finished, replaced by a newer request, stopped by `stop_moving`, cut short by a
reflex, by death, or by the agent disconnecting. An answer is matched to its
caller by `id` only; one nobody is waiting for any more (the caller timed out, or
the body was taken off the goal mid-swing) is discarded. What the body does
without being asked never has a `status`, so it can never answer for anything:
the surface appends it to the body's behaviour log, which the body reads as
"While you were working: …" before its next move, and a fight or a death is also
told to her.

A jar that speaks protocol 1 still plays: the brain logs an error that it is
outdated, matches its answers in order, reads its explanation from `details`,
and does not wait for the four actions it never answers. The packets the tests
hold the client to are recorded from a live mod
(`tests/fixtures/minecraft_packets/`).

### The contract

`tests/fixtures/minecraft_contract.json`: for every action,
the parameters that mod skill actually looks at, and the ones `ActionManager`
fills in itself, plus which actions run beside the body. `tools/mc_contract.py`
regenerates it from a checkout:

```bash
uv run python tools/mc_contract.py --mod ../beacraft
```

`tests/test_minecraft_contract.py` holds the tool schemas against it, and fails
in both directions. A parameter the brain sends and the mod never reads is a
silent no-op — the model believes it asked for something and nothing happened.
A parameter the mod accepts that the brain neither sends nor lists in `OMITTED`
is new capability nobody has decided about, and the test refuses to let it pass
unnoticed. Regenerate the fixture whenever a mod skill gains or loses a
parameter, and review the diff: it is the only place the two repositories are
written down together.

---

## Thread safety

`MinecraftClient` runs the blocking WebSocket on a background thread and hands
every packet to the event loop with `call_soon_threadsafe`. All state lives on
one thread, so tool handlers can simply `await` completion and there are no
locks.

---

## Configuration

```json
"minecraft": {
  "enabled": false,
  "server_url": "ws://127.0.0.1:8080",
  "idle_nudge_seconds": 90,
  "commentary_seconds": 20,
  "steps_per_goal": 40,
  "tick_seconds": 0.4,
  "body_context_rounds": 12,
  "system_prompt_path": "data/prompts/minecraft.md",
  "body_prompt_path": "data/prompts/minecraft_body.md"
}
```

| Key | Description |
|---|---|
| `server_url` | WebSocket URL of the BeaCraft mod |
| `idle_nudge_seconds` | How long the body may stand still with an open objective before it tells her. `0` disables it |
| `commentary_seconds` | How long she may play without saying a word while the body works. `0` disables it |
| `steps_per_goal` | Rounds the body spends on one goal before calling it stuck and handing it back |
| `tick_seconds` | Pause between two rounds. Most pacing is the game itself; this stops a goal of instant tools from spinning |
| `body_context_rounds` | How many of its own rounds the body remembers. Everything older lives in the notebook |
| `system_prompt_path` | What the **mind** knows about having a body |
| `body_prompt_path` | The survival guide and crafting chains, for the **body** |

Two prompts, because they are for two different readers: recipe trees belong to
the body, not in her head.

The body uses the `minecraft` model pool and the mind uses `mind`. Leave
`models.minecraft` empty and the body thinks with her own model, which is the
default and the right one for playing.

```json
"models": {
  "mind": ["openrouter:deepseek/deepseek-v4-flash"],
  "minecraft": []
}
```

## From the dashboard

Minecraft's settings page carries a live panel for the body: the goal, how far
it has got, how long it has been at it, and the line it last thought. It reads
the same three things her own context does, so the two can never show different
bodies.

| Endpoint | What it does |
|---|---|
| `GET /minecraft/body` | the goal, status, steps, elapsed time and last thought |
| `POST /minecraft/goal` | point the body at something, over her head |
| `POST /minecraft/stop` | drop the goal and stand still |
| `POST /minecraft/ask` | ask her to say what she is up to, off the clock |

Setting a goal here is the owner deciding instead of her. She is not told it
came from outside: an arriving goal is indistinguishable from one she set
herself, which is what makes it usable mid-stream.
