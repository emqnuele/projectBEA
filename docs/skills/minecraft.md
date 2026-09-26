# Minecraft Skill

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What it does

Bea plays Minecraft on a server alongside other people. She reads the game
chat and answers it, recognises the players across sessions, reacts to being
hit or killed, and plays: chops, mines, crafts, builds, fights, explores.

It is one more skill of the one mind, like telegram or the voice call. Turned
on, it adds the game's senses to her perceptions, the game's tools to her
toolset and the game's rules to her context. Nobody plays for her: when she
calls `find_block`, she is the one chopping the tree.

```
src/core/skills/minecraft/
├── surface.py   MinecraftSurface — the senses, her tools, what she is doing now
├── client.py    WebSocket bridge to the mod
├── state.py     the state packet, rendered as a few readable lines
├── tools.py     the game tools
├── building.py  plan_build, templates and build scripts, worked out before the mod
├── blueprint.py a build's arguments, expanded to cells and costed
├── buildscript.py  a build drawn by a short, sandboxed script
├── crafting.py  what it takes to make an item, from what she carries
├── recipebook.py crafting_plan, and the plan behind a failed craft
└── places.py    places she remembers, per world

data/prompts/minecraft.md    how she plays: acting and talking, people, the survival guide
data/minecraft/blueprints/   ready-made buildings (mindcraft's, MIT)
data/minecraft/recipes/      the crafting and smelting recipes, one file per Minecraft version
```

---

## One mind, her own hands

```
┌─ the mind (Consciousness) ─────────────────────────────┐
│ her one model, her one window, every skill's senses    │
│ speak · send_message · … · find_block · craft_item · … │
└───────────┬──────────────────────────────▲─────────────┘
            │ an action, started           │ [find_block] result: SUCCESS: …
┌───────────▼──────────────────────────────┴─────────────┐
│ the action runs in the background; she keeps talking   │
└───────────┬────────────────────────────────────────────┘
            │  WebSocket ws://127.0.0.1:8080
┌───────────▼────────────────────────────────────────────┐
│ Minecraft + the BeaCraft mod: reflexes, paths, skills  │
└────────────────────────────────────────────────────────┘
```

The fast loop of playing lives in the mod: eating, fighting back, landing a
fall and fleeing are reflexes that answer in ticks, and every action is a whole
job (`find_block("log", count=16)` walks, chops and picks up until she carries
sixteen more). What is left is deciding the next thing, which is what she does
on every turn anyway.

**An action that takes time runs beside her.** A game tool marked long-running
comes straight back with "started", and the consciousness runs it in the
background; its outcome arrives as an `ACTION` perception from `game:mc`,
`[find_block] result: SUCCESS: collected 16/16 oak_log in 117 s`, which the gate
always lets through. Meanwhile she is free to talk, read the chat and answer
people.

**One pair of hands.** A new action replaces the one still going. Several asked
for in the same step are done in that order, one after the other, and reported
together once they are over; the first one that fails stops the rest, and the
report names what was not done. A turn is a loop, as for every skill: tools,
their answers, more tools, until she speaks or stays silent — so she acts first
and talks after. Once she has spoken, a step that only started actions ends the
turn: "started" is nothing new to read.

**Talking about it is not doing it.** A spoken turn is over, which is right for
a message and wrong for a game: *"let me start punching some birch logs"* ended
the turn with nothing in her hands. So when a turn about the
game (anything from `game:mc` or `chat:mc`) is ending while no action of hers is
running and none was started in it, the skill's `left_undone` tells her so and
the turn gets one more step: the action now, or `stay_silent` if she really
chooses to stand there. Once per turn; every other skill leaves its turns alone.

**Quick things answer at once**, beside whatever she is doing: `scan`,
`crafting_plan`, `plan_build`, `list_templates`, `look_at`, `look_at_player`,
`mc_chat`, `check_death_log`, `stop_moving`, `remember_place`.

**Everything is about her.** The prompt, every perception and every tool
description say *you*: "You have been at find_block(block=log, count=16) for
40s", "On reflex: defending against Zombie". A player who reads about a body
working for her talks to it instead of playing.

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
| the answer to an action of hers | `ACTION`, always addressed |
| a reflex: fighting back, respawning | `GAME`, *On reflex: …* |
| a reflex: eating, getting unstuck, a clutch | nothing wakes her; it sits in her live state for a minute |
| following someone ends on its own | `GAME`, *You stopped follow player: …* (not when she stopped it) |
| a build's progress | into her live state: *last you heard: building: 10 placed, 38 to go* |

The game itself lives in `live_state()` rather than in a perception: it is
*where she is*, always true, not an event that should make her think. It opens
with what her hands are on (`- you are doing: find_block(block=log, count=16),
40s so far`) or `- you are not doing anything right now`, then what the game did
on its own in the last minute, then the state `state.py` renders — health,
position, what she is holding and wearing, what is craftable, what is nearby,
what she is standing on, who is around — and the places she remembers.

Every block the mod names arrives with the coordinates and distance it was seen
at, nearest first, because `mine_block`, `place_block` and `use_block` all
require an exact coordinate and a model that is shown a tally can only invent
one. The list is capped per kind, so a row of torches cannot spend the budget
and hide the ore behind it. The bulk census, the block underfoot and the block
overhead come from the mod as well: standing on air is how she learns she is
falling.

That close view reaches four blocks. Further out, the mod scans a cube of 20
blocks around her every two seconds (a few milliseconds of the game's frame)
and reports each useful kind once: logs by wood, leaves, stone, cobblestone,
deepslate, every ore, sand, gravel, clay, water and lava sources, crafting
tables, furnaces, chests, barrels, beds and ripe crops, with how many there are,
the nearest, and the nearest she can reach without digging. `state.py` turns it
into one line, ores first, eight kinds at most. A `world` block adds the time of
day, whether it is dark outside, the weather, the light at her feet (hostiles
spawn where the block light is 0), the biome and the dimension; the state says
"night" when monsters are about. Beyond twenty blocks she asks: `scan(block,
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
`mc_chat` counts as an answer to someone: it reaches an audience.

Using both in one turn is usually right: the funny thing out loud, the useful
thing in chat.

---

## Two silences worth breaking

The heartbeat is marked `noise`, so an idle server costs nothing. Two
perceptions ask something of her instead; the surface emits at most one per
tick, and which one depends on whether her hands are busy.

**Standing around.** With no action running for `idle_nudge_seconds` (30 by
default), she is told how long she has been standing there, with the open
objectives of the [stream plan](plan.md) when there are any, and that it is her
game. With an empty plan she is told too: a player in a field is still a player.

**Deep in something long.** While an action runs, at most every
`commentary_seconds` (20 by default), she is told what she is at, for how long,
the last progress it reported and what she carries — **only when something
changed** since she last heard about it: new progress, or a different
inventory. Time passing is not news, and a nudge with nothing new in it comes
back as filler. It asks for words if there are any and says staying quiet is
fine.

**And on demand** — `POST /minecraft/ask`, the *Ask her what she is doing*
button, puts the same kind of perception on the bus at once, standing still or
not.

Both declare themselves addressed, so the gate always lets them through, and
both take `0` to turn off. Neither is free: each is a turn on her own model.

---

## Tools

All of them are hers while the skill is on and the mod is connected:

`scan`, `mine_block`, `attack_entity`, `move_to`, `move_away`, `go_to_surface`,
`stop_moving`, `look_at`, `place_block`, `build`, `find_block`, `pillar_up`,
`mine_down`, `bridge`, `craft_item`, `use_block`, `smelt_item`, `store_item`,
`retrieve_item`, `view_container`, `equip_item`, `discard_item`, `eat_food`,
`check_death_log`, `goto_player`, `follow_player`, `look_at_player`,
`give_item`, `mc_chat`, `pickup_items` — plus the ones worked out in the brain:
`crafting_plan`, `remember_place`, `go_to_place`, `plan_build`,
`list_templates`, `build_template` and `build_script` (the last only with
`build_scripts` on). `mc_chat` is the mod's `chat`: beside telegram and discord,
a tool called just `chat` would not say where it goes. The mod's
`request_screenshot` and `select_slot` are left out on purpose: nothing of hers
reads an image yet, and `equip_item` takes anything into her hand. The contract
test fails when the mod offers an action she neither has nor leaves out by name.

Every description says what the tool does and what it answers when it fails.
`use_block` walks into reach, clicks the face turned towards her and says what
changed; a screen it opens is closed again. `mine_down` stops before lava, fire,
water or a drop deeper than three. `follow_player` answers as soon as she is on
her way; the following goes on until her next action or `stop_moving`, and its
end reaches her when she lost them.

**Mining counts what the server keeps.** The client shows a broken block at
once, as a prediction; `mine_block` counts it only once the server has answered
for it. Water or lava flowing into the hole, or sand falling into it, is still a
broken block; a block the server puts back three times is protected ground
(`FAILURE_PROTECTED`). `find_block` counts what the blocks drop (stone gives
cobblestone, grass gives dirt, iron ore raw iron), never a piece of a name; it
stops with `FAILURE_NO_DROPS` after six blocks in a row that gave none of it
(leaves without shears) and with `FAILURE_INVENTORY_FULL` when nothing more
would be picked up.

**She mines only what she can see.** The mod casts the same ray a player's
crosshair would: leaves, dirt or grass between her and the block are broken
first, and a block she must not break in the way (a protected one, glass,
bedrock) sends her to a side she can see it from. Clearing a path, a pillar or
a build cell breaks only the cell asked for.

**Places** are kept per world, under the address the mod puts in `world.server`,
in `data/minecraft/places.json`: `remember_place(name)` stores where she stands,
`go_to_place(name)` walks there with `move_to`, a place in another dimension is
refused, and her live state lists them. Where she died is stored for her as
`last_death` when the death event arrives. A save takes its text on the event
loop, where the places change, and writes it in a thread to a file of its own
before moving it into place; an older save never lands over a newer one.

Every tool awaits the mod's answer to it, so what reaches her is what actually
happened: `RESULT: sentence`, followed by the last lines of the action's own log
when it sent one. How long the brain waits depends on the action
(`ACTION_TIMEOUTS` in `tools.py`), and is always longer than the mod's own
budget for it (announced in the handshake), so the mod gives up first and says
why.

---

## Building

A whole structure is one `build`: the mod clears the cells that must be empty,
places the rest bottom-up starting from what already holds them up, walks where
it needs to, and answers with every cell still wrong and every block it ran out
of. She never places a house block by block. Three ways lead to it:

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

A build spans at most 256 blocks along any axis: more is nearly always an
absolute coordinate among relative ones, and the answer asks exactly that.

**Two expansions, one meaning.** `blueprint.py` expands the arguments in the
brain, to cost a build before it starts (`plan_build`); BeaCraft's `Blueprint`
expands them again to build. Both are held to the same vectors in
`tests/fixtures/minecraft_blueprints/`, which the mod's tests read from a copy;
each side's tests also check the copy is byte for byte the other's when the two
checkouts sit side by side. A malformed argument (a flattened `layers`, an op
that is not an object, a `hollow` that is not true or false, a coordinate that
is not a whole number) is refused with the same sentence on both sides; `null`
for an optional argument means it was left out.

**What gets cleared.** Cells meant to be `air` are emptied; with `clear: true`,
blocks in the way of a different block are broken too. Doors, trapdoors, gates,
beds, chests, barrels, furnaces, crafting tables, glass, torches and lanterns
(the protected blocks) are never broken by a build: they are left where they
are and named in the answer.

**What it cannot reach from the ground.** After its two passes, a cell no
standing spot reaches gets a pillar: she walks to a column beside it, outside
the build where she can, towers up on spare blocks (never the ones the cells
left still need), places everything the top reaches, and digs the pillar back
down, picking its blocks up again.

**How long.** A cell takes 0.6 to 0.9 s, walking included (measured), and the
mod gives one build 600 s. `plan_build` and a script's preview say when a build
is longer than that; when the time runs out the answer says so, and the same
build sent again carries on, since cells already right are skipped.

**A cell counts once the server keeps it.** The client shows a placed block the
moment it is clicked; the check waits for the server's answer to that click, so
a block a claim, spawn protection or an anticheat refuses is reported as not
placed however much ping there is.

**Templates** are mindcraft's `dirt_shelter`, `small_wood_house` and
`small_stone_house`, in their own format (`blocks[y][z][x]`, generic names like
`planks`, a negative `offset` for a floor sunk into the ground), with their
licence in `_source`. `build_template` resolves the generic names from what she
carries (the wood she has most of, the wool colour for the bed), gives the door
the facing a player standing outside would give it, and asks the mod to clear
whatever stands in the way.

**Scripts** only draw. She writes a few lines against `set`, `fill`,
`walls`, `line`, `circle`, `get` and `note`; the script is checked against a
whitelist of syntax (no imports, no attributes, no names starting with `_`),
then run in a separate interpreter (`python -I -S`) with no builtins beyond
arithmetic, a 3-second limit and a 512 MB memory watch, and all that comes back
is a list of cells, turned into `layers` + `palette` row by row from the cells
there are (a script whose cells span more than 256 blocks is refused before
anything is laid out). The interpreter starts with an empty environment: nothing
of the brain's, its API keys least of all, is visible to it. `confirm=false`
returns the box it fills and what it costs; nothing is built until the same
script comes back with `confirm=true`. The mod never sees code.

**While it builds** the mod sends `{"type": "progress", "done", "total",
"message"}` every ten cells; it becomes the progress of what she is doing, which is what
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
aims, so she stops as soon as she is that close. A door she opened is shut
behind her once she is two blocks past it and the path does not go back through
it; one still open and out of reach when the walk ends is said to be left open.
A long search is worked on 1,500 nodes a tick, so no frame of the stream waits
on it; a short one is answered in the tick it is asked for.

A walk that stops gaining ground steps aside once and plans again before it gives
up, and the answer's log says so. `move_away(distance)` puts that many blocks
between her and where she stands, trying up to three directions. `go_to_surface`
walks out to open ground when there is a way, else digs a staircase up, one step
forward and one up, in a direction with no lava or water behind what it opens;
it is done when the sky is over her head and the ground ahead is no higher than
her feet.

Baritone is an optional dependency the player adds as a separate mod
([MeteorDevelopment/baritone](https://github.com/MeteorDevelopment/baritone)):
with it she walks its routes, in `full` parkour included; without it everything
works the same on her own A*. `baritoneMode` in the mod's config (or `/beacraft
baritone` in game) picks how: `full` plans and walks, `plan` plans while her
own skills walk, `off` keeps the built-in A*. The protected blocks, door
opening, `range` and the step aside are hers in every mode, whichever planner
drew the route. Baritone's settings are global, so hers hold only while one of
her routes is being planned or walked, and each goes back to what it was: the
player using Baritone by hand on the same client finds it as they left it. A
chat line starting with its command prefix is refused, so it never ends up in
its command handler instead of the game.

---

## What the game does on its own

The mod acts without being asked when waiting would hurt her, and says so with a
`reflex` event every time:

- **eat** at food 14 or less when idle, or when hurt and hungry at once; only
  food worth eating (no rotten flesh, spider eyes, raw chicken…).
- **defend** against a monster that hits her. A fight that ends with it alive
  and out of reach (on a pillar, across lava: no blow landed in 10 s, or two
  walks to it came up short) leaves that attacker alone for 30 s, and the queue
  of attackers never takes her hands from a request; the next blow does. A player
  is someone, not a mob: she fights back only after three hits in ten seconds.
- **flee** at under 6 health with nothing to fight with.
- **clutch**: a fall of more than three blocks with a water bucket in the hotbar
  is landed in water, and the water taken back. The clutch owns her hands until
  she lands: a request meanwhile is answered `FAILURE_BUSY`, and `stop_moving`
  stops everything else.
- **respawn** after a death; while she is dead a request is answered
  `FAILURE_DEAD`.

A glance (`look_at`) waits while a skill is aiming a click (placing, mining,
fighting, landing a fall): the server orients a door, a stair or a bed by the
last look it received.

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
Every answer ends with what the chest holds now. `view_container` is an action
of its own, not one of the side tasks that run beside one: it walks, and opening
any screen releases every key she is holding, which would end a walk.

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

Her point of view is the stream, so what she does on purpose looks like a person doing
it. Turns ease in and out (a quarter turn takes about three quarters of a
second) and she looks at a block, a face or a chest before she acts on it.
Screens are worked at the pace of a hand: a look when the screen opens, a click
every 0.2–0.4 s, a moment on the result before it closes (`humanPace` in
`config/beacraft.json`, on by default). While nothing needs her aim exact, it
drifts slowly, under a degree, a few seconds per swing (`aimSway`, 0.8 by
default, 0 for none); never while she breaks or places a block, bridges,
pillars, fights or falls, or has a screen open.
Eating, fighting, clutching and fleeing are reflexes and never wait for any of
this.

### Protocol

The mod announces itself on connect: `protocol`, `mod_version`, `mc_version`,
the `actions` it has, which of them are `concurrent`, and the `budgets`: how
many seconds each action may run before the mod stops it and answers
`FAILURE_TIMEOUT` with what it was doing (0 for none, as with `follow_player`).
The brain waits at least five seconds longer than that budget. It speaks
protocol 2.

**Brain → mod:**

```json
{ "id": "r41-3fa2c1", "action": "mine_block", "parameters": { "x": 100, "y": 64, "z": 100 } }
```

**Mod → brain.** Dispatch is on `type` first, then `status`:

| Field | Value | Meaning |
|---|---|---|
| `type` | `chat`, `player_event`, `combat`, `death_event` | a sense; handed to the surface |
| `type` | `reflex` | the game acted on its own: `reflex` is `eat`, `defend`, `flee`, `clutch`, `unstuck` or `respawn`, `event` is `started`/`finished`, `interrupted_id` names the request it cut short |
| `type` | `activity` | something answered when it started (`follow_player`) has ended: `id` of that request, `result`, `message` |
| `status` | `FINISHED` | the answer to request `id`: `result` (`SUCCESS`, `FAILURE_<CODE>`, `INTERRUPTED`), `message`, optional `log`, `details`, and `reason` when interrupted |
| — | `type: game_state` | a game-state snapshot, once a second |

```json
{"status": "FINISHED", "id": "r41-3fa2c1", "action": "move_to", "result": "INTERRUPTED",
 "message": "interrupted (self_defence: Zombie)", "reason": "self_defence: Zombie"}
{"type": "reflex", "reflex": "defend", "event": "started",
 "message": "defending against Zombie after taking 2.0 damage", "interrupted_id": "r41-3fa2c1"}
```

Every request is answered exactly once, with its own `id`, however it ends:
finished, replaced by a newer request, stopped by `stop_moving`, cut short by a
reflex, by death, or by the agent disconnecting, and also when the skill itself
fails with an exception (`FAILURE_EXCEPTION`): a skill that throws gives the
action back instead of taking the game down with it. The brain's ids carry a mark
of their own (`r41-3fa2c1`), since the mod answers every connection; a request
that could not be sent fails at once instead of waiting out its timeout. An answer is matched to its
caller by `id` only; one nobody is waiting for any more (the caller timed out, or
she replaced the action mid-swing) is discarded. What the mod does without
being asked never has a `status`, so it can never answer for anything: the
surface keeps it in her live state for a minute, and a fight or a death wakes
her.

A jar that speaks protocol 1 still plays: the brain logs an error that it is
outdated, matches its answers in order, reads its explanation from `details`,
and does not wait for the four actions it never answers. The packets the tests
hold the client to are recorded from a live mod
(`tests/fixtures/minecraft_packets/`).

### The contract

`tests/fixtures/minecraft_contract.json`: for every action,
the parameters that mod skill actually looks at, and the ones `ActionManager`
fills in itself, plus which actions run beside another. `tools/mc_contract.py`
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
  "idle_nudge_seconds": 30,
  "commentary_seconds": 20,
  "build_scripts": true,
  "system_prompt_path": "data/prompts/minecraft.md"
}
```

| Key | Description |
|---|---|
| `server_url` | WebSocket URL of the BeaCraft mod |
| `idle_nudge_seconds` | How long she may stand around doing nothing before she is told. `0` disables it |
| `commentary_seconds` | The shortest gap between two words asked of her while a long action runs, and only when something in it changed. `0` disables it |
| `build_scripts` | Whether she may draw a build with a script (`build_script`). Off, the tool is not offered; templates and ops still work |
| `system_prompt_path` | How she plays: acting and talking at once, the people around her, the survival guide |

She plays with her own model: the game is one more thing the `mind` pool
reasons about.

## From the dashboard

Minecraft's settings page carries a live panel: the action in her hands, how
long it has been going, the progress it last reported and the last one she
finished. It reads the same things her own frame does, so the two can never
show different games.

| Endpoint | What it does |
|---|---|
| `GET /minecraft/now` | what she is doing, for how long, its progress and the last thing she finished |
| `POST /minecraft/stop` | put her hands down (the mod's `stop_moving`); the stopped action reaches her as interrupted |
| `POST /minecraft/ask` | ask her to say what she is up to, off the clock |
