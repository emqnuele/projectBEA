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
├── tools.py     the game tools, for the body
├── building.py  plan_build, templates and build scripts, worked out before the mod
├── blueprint.py a build's arguments, expanded to cells and costed
├── buildscript.py  a build drawn by a short, sandboxed script
├── crafting.py  what it takes to make an item, from what she carries
├── recipebook.py crafting_plan, and the plan behind a failed craft
└── notebook.py  the body's private scratchpad

data/minecraft/blueprints/   ready-made buildings (mindcraft's, MIT)
data/minecraft/recipes/      the crafting and smelting recipes, one file per Minecraft version
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
│ 34 tools + the survival guide + the notebook           │
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

That close view reaches four blocks. Further out, the mod scans a cube of 20
blocks around her every two seconds (a few milliseconds of the game's frame)
and reports each useful kind once: logs by wood, leaves, stone, cobblestone,
deepslate, every ore, sand, gravel, clay, water and lava sources, crafting
tables, furnaces, chests, barrels, beds and ripe crops, with how many there are,
the nearest, and the nearest she can reach without digging. `state.py` turns it
into one line, ores first, eight kinds at most. A `world` block adds the time of
day, whether it is dark outside, the weather, the light at her feet (hostiles
spawn where the block light is 0), the biome and the dimension; the state says
"night" when monsters are about. Beyond twenty blocks the body asks: `scan(block,
radius)` looks up to 64 blocks for one kind, beside whatever she is doing.

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
`equip_item`, `store_item`, `retrieve_item`, `attack_entity`, `give_item`,
`build`, `build_template` and `build_script` produce one when they succeed or fail badly. An interrupt or a death always
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

**The body's game tools:** `scan`, `mine_block`, `attack_entity`, `move_to`,
`move_away`, `go_to_surface`, `stop_moving`, `look_at`, `place_block`, `build`,
`find_block`, `pillar_up`, `mine_down`, `bridge`, `craft_item`, `use_block`,
`smelt_item`, `store_item`, `retrieve_item`, `view_container`, `equip_item`,
`discard_item`, `eat_food`, `check_death_log`, `goto_player`, `follow_player`,
`look_at_player`, `give_item`, `chat`, `pickup_items` — plus the ones worked out
in the brain: `update_notebook`, `crafting_plan`, `remember_place`,
`go_to_place`, `plan_build`, `list_templates`, `build_template` and
`build_script` (the last only with `build_scripts` on). The mod's
`request_screenshot` and `select_slot` are left out on purpose: nothing in the
body reads an image yet, and `equip_item` takes anything into her hand. The
contract test fails when the mod offers an action the body neither has nor
leaves out by name.

Every description says what the tool does and what it answers when it fails.
`use_block` walks into reach, clicks the face turned towards her and says what
changed; a screen it opens is closed again. `mine_down` stops before lava, fire,
water or a drop deeper than three.

**Places** are kept per world, under the address the mod puts in `world.server`,
in `data/minecraft/places.json`: `remember_place(name)` stores where she stands,
`go_to_place(name)` walks there with `move_to`, a place in another dimension is
refused, and the body reads them with every game state as *PLACES YOU REMEMBER*.
Where she died is stored for her as `last_death` when the death event arrives.

Every tool awaits the mod's answer to it, so the observation the model reasons
on is what actually happened: `RESULT: sentence`, followed by the last lines of
the action's own log when it sent one. `chat`, `check_death_log`,
`request_screenshot`, `look_at` and `scan` run beside whatever the body is doing
and are answered at once; they never stop it. How long the brain waits depends on the
action (`ACTION_TIMEOUTS` in `tools.py`), and is always longer than the mod's own
budget for it (announced in the handshake), so the mod gives up first and says
why.

---

## Building

A whole structure is one `build`: the mod clears the cells that must be empty,
places the rest bottom-up starting from what already holds them up, walks where
it needs to, and answers with every cell still wrong and every block it ran out
of. The body never places a house block by block. Three ways lead to it:

| Way | Tool | For |
|---|---|---|
| template | `build_template(name, x, y, z, rotation)` | houses and shelters: no spatial reasoning at all |
| ops / layers | `build(origin, rotation, palette, layers, ops)` | a wall, a floor, a box |
| script | `build_script(code, x, y, z, rotation, confirm)` | towers, stairs, domes: loops and curves |

**The arguments.** `layers` are horizontal slices, bottom first; each is a list
of rows along +z, each row a string of palette characters along +x. A space
leaves a cell as it is; a palette entry `air` means the cell must be empty. `ops`
(`fill`, optionally `hollow`; `walls`; `set`; `roof`) apply after the layers and
overwrite them. `rotation` turns the whole build clockwise seen from above
around `origin`, and turns `facing` and `axis` in block states with it. At most
2000 cells. Block names take vanilla's state syntax: `oak_door[facing=north]`,
`oak_log[axis=x]`, `oak_stairs[facing=east,half=top]`.

**Two expansions, one meaning.** `blueprint.py` expands the arguments in the
brain, to cost a build before it starts (`plan_build`); BeaCraft's `Blueprint`
expands them again to build. Both are held to the same vectors in
`tests/fixtures/minecraft_blueprints/`, which the mod's tests read from a copy.
Change one and the vectors say so.

**Templates** are mindcraft's `dirt_shelter`, `small_wood_house` and
`small_stone_house`, in their own format (`blocks[y][z][x]`, generic names like
`planks`, a negative `offset` for a floor sunk into the ground), with their
licence in `_source`. `build_template` resolves the generic names from what she
carries (the wood she has most of, the wool colour for the bed), gives the door
the facing a player standing outside would give it, and asks the mod to clear
whatever stands in the way.

**Scripts** only draw. The body writes a few lines against `set`, `fill`,
`walls`, `line`, `circle`, `get` and `note`; the script is checked against a
whitelist of syntax (no imports, no attributes, no names starting with `_`),
then run in a separate interpreter (`python -I -S`) with no builtins beyond
arithmetic, a 3-second limit and a 512 MB memory watch, and all that comes back
is a list of cells, turned into `layers` + `palette`. `confirm=false` returns the
box it fills and what it costs; nothing is built until the same script comes back
with `confirm=true`. The mod never sees code.

**While it builds** the mod sends `{"type": "progress", "done", "total",
"message"}` every ten cells; it becomes the body's current thought, which is what
her commentary reads.

---

## Walking

`move_to(x, y, z, range)` plans twice when it may dig: first a way that breaks
nothing, found within 5,000 steps of search (round a wall, through a door she
opens); only when there is none, a way that digs. A path never digs through the
protected blocks, whatever the cost: doors, trapdoors, fence gates, beds, chests,
barrels, shulker boxes, furnaces, crafting tables, glass and panes, torches and
lanterns (`protectedBlocks` in `config/beacraft.json`; ids, `#tags` and
`*suffixes`). A closed wooden door or fence gate on the way is a step of the path:
she opens it when she reaches it, and one she walks into gets opened too. Fences
and walls are 1.5 blocks high, so they are never taken for a step to jump onto.
`range` up to 1.5 only forgives where she stops; a bigger one is where the plan
aims, so she stops as soon as she is that close.

A walk that stops gaining ground steps aside once and plans again before it gives
up, and the answer's log says so. `move_away(distance)` puts that many blocks
between her and where she stands, trying up to three directions. `go_to_surface`
walks out to open ground when there is a way, else digs a staircase up, one step
forward and one up, in a direction with no lava or water behind what it opens;
it is done when the sky is over her head and the ground ahead is no higher than
her feet.

---

## Crafting, smelting and chests

Each of these is one action that does the whole job, the way a player would:
find the block it needs, walk into reach, open it, do the work, close it.

**`craft_item(item, count)`** makes `count` items, not `count` crafts: five
sticks are two crafts and eight sticks. A recipe that fits the 2x2 grid is made
in her inventory. Whether it fits is the recipe's shape, not its number of
ingredients: a slab is three planks in a row, so it needs a table. Anything
bigger goes to the nearest crafting table within 16 blocks, walking there; with
none around she sets down the table she carries, crafts, and picks it back up
(`pickUpPlacedTable` in `config/beacraft.json`, on by default). A shortage is
named with the numbers: *takes 3 planks and 2 stick; you are short of 2 planks
(you have 1)*. The mod crafts only recipes she has unlocked, and says so; the
game unlocks a recipe when she first carries one of its ingredients.

**`crafting_plan(item, count)`** is answered in the brain, at once: every craft
and smelt in order from what she carries, what is missing, which steps need a
table or a furnace, the fuel and the leftovers. It reads
`data/minecraft/recipes/<version>.json`, the one matching the `mc_version` in the
handshake, or the newest older one with a note saying so. A failed `craft_item`
comes back with the plan appended. The planner uses what she carries first,
fills a slot like `#planks` from any planks she has, picks the recipe with the
fewest missing items, never unpacks a storage block she does not carry, and never
smelts an ore (mining it already drops the raw item).

The recipe files are extracted from Mojang's server jar and committed:

```bash
uv run python tools/mc_recipes.py 26.2                  # downloads the jar
uv run python tools/mc_recipes.py path/to/server.jar 26.2
```

**`smelt_item(item, count, fuel)`** uses the nearest furnace within 16 blocks, or
sets down the one she carries. She puts in exactly `count` items and just enough
fuel: one kind of fuel (a furnace holds one), the kind that leaves the least burn
unused, so one raw iron costs a plank rather than a coal; the planner picks the
same way. She waits, taking out what comes out, and stops when it is all done or
nothing has come out for 11 seconds (a smelt takes 10). What she put in and did
not use comes back out. A furnace already smelting something else is left alone
(`FAILURE_FURNACE_BUSY`). At most 10 items per call, which keeps the walk, the
smelting and the pick-up inside the mod's 150 s budget.

**`store_item`, `retrieve_item`** move exactly `count` of exactly the item named
(all of it when `count` is left out) between her and a chest or barrel: the one
at `x, y, z`, or the nearest within 32 blocks. **`view_container`** only looks.
Every answer ends with what the chest holds now. `view_container` is a body
action, not one of the side tasks that run beside the body: it walks, and opening
any screen releases every key the body is holding, which would end a walk.

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
the `actions` it has, which of them are `concurrent`, and the `budgets`: how
many seconds each action may run before the mod stops it and answers
`FAILURE_TIMEOUT` with what it was doing (0 for none, as with `follow_player`).
The brain waits at least five seconds longer than that budget. It speaks
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
  "build_scripts": true,
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
| `build_scripts` | Whether the body may draw a build with a script (`build_script`). Off, the tool is not offered; templates and ops still work |
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
