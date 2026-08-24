# Minecraft Skill

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What it does

Bea has a body on a Minecraft server. She plays alongside other people: she
reads game chat, answers it, recognises the players across sessions, reacts to
being hit or killed, and pursues goals she sets for herself.

She does not pilot the body block by block. She gives it an **intention** and it
goes and does it while she carries on talking.

```
src/core/skills/minecraft/
├── surface.py   MinecraftSurface — the senses, and 7 tools for the mind
├── agent.py     GameAgent — the body, pursuing one goal at a time
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
│ sees: game state as ~5 lines, milestones, player chat  │
└────────────────────┬───────────────────────────────────┘
                     │  play_minecraft("get a stone pickaxe")
┌────────────────────▼───────────────────────────────────┐
│ the body — GameAgent, background model                 │
│ 26 tools + the survival guide + the notebook           │
│ think → act → observe, up to 24 steps per goal         │
│ reports back: milestones, and one line at the end      │
└────────────────────┬───────────────────────────────────┘
                     │  WebSocket ws://127.0.0.1:8080
┌────────────────────▼───────────────────────────────────┐
│ Minecraft + the BeaCraft mod                           │
└────────────────────────────────────────────────────────┘
```

The body runs on the **`background`** pool. Working out that a pickaxe needs
sticks is not what her good model is for, and it must not compete with the part
of her that talks to people.

`play_minecraft` is `long_running`, so it starts a task and returns immediately:
she keeps talking while the body works. One goal at a time — a new one replaces
the old.

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
| a body milestone | `GAME` — only for tools whose outcome is a real step forward |

The game state itself lives in `live_state()` rather than in a perception: it is
*where she is*, always true, not an event that should make her think. `state.py`
renders it as about five lines — health, position, what she is holding, what is
craftable, what is nearby, who is around — instead of the raw packet, which runs
to hundreds of lidar entries underground.

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

## Starting something on her own

The heartbeat is marked `noise`, so an idle server costs nothing. What gets her
moving is the [stream plan](plan.md): objectives the owner writes on the
dashboard.

When the body is standing still and an objective is still open, the surface puts
one perception on the bus saying so, at most once every `idle_nudge_seconds`. It
declares itself addressed, so the gate always lets it through, and she answers
it by handing the body a goal.

With an empty plan there is no nudge, and she reacts to whatever happens without
setting out to do anything.

---

## The body's loop

```python
GameAgent.pursue(goal)
    ├─ system: the survival guide + "GOAL FROM BEA: <goal>"
    ├─ user:   the goal, the rendered state, the notebook
    └─ AgentRunner, max 24 steps
            ├─ tool call → mod command → await completion → observation
            └─ every observation passes through _observe()
                    └─ worth interrupting her for? almost never
```

**The notebook** (`notebook.py`) is the body's working memory: one freeform blob
the model rewrites in full via `update_notebook`. It is re-injected every cycle
so a plan survives history trimming, and it is never spoken.

**Milestones** are the only thing that reaches the mind mid-goal. Movement and
looking are means, not results; `craft_item`, `mine_block`, `place_block`,
`smelt_item`, `find_block`, `equip_item`, `store_item`, `retrieve_item`,
`attack_entity` and `give_item` produce one when they succeed or fail badly. An
interrupt or a death always does.

A goal that has not landed in 24 steps is stuck, and saying so is more useful
than grinding on.

---

## Tools

**The mind's seven:**

| Tool | Effect |
|---|---|
| `play_minecraft(goal)` | hand the body something to achieve |
| `mc_chat(message)` | type in game chat |
| `mc_stop()` | put the body down |
| `mc_goto_player(name)` | walk over to someone |
| `mc_follow_player(name)` | tag along until she stops |
| `mc_look_at_player(name)` | make it obvious she noticed |
| `mc_give_item(name, item, count)` | walk over and drop it at their feet |

**The body's twenty-six:** `mine_block`, `attack_entity`, `move_to`,
`stop_moving`, `request_screenshot`, `look_at`, `place_block`, `select_slot`,
`find_block`, `pillar_up`, `mine_down`, `bridge`, `craft_item`, `use_block`,
`smelt_item`, `store_item`, `retrieve_item`, `equip_item`, `discard_item`,
`eat_food`, `check_death_log`, `goto_player`, `follow_player`, `look_at_player`,
`give_item`, `chat` — plus `update_notebook`.

`chat`, `stop_moving`, `request_screenshot` and `check_death_log` are instant
and return at once. Every other tool awaits the mod's completion event, so the
observation the model reasons on is what actually happened.

---

## The mod

**BeaCraft** is a client-side Fabric mod (1.21.1, Java 21). It drives the local
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

> The mod binds on the LAN without authentication. Keep it on a trusted
> network, or bind it to loopback.

### Protocol

**Mod → brain.** Dispatch is on `type` first, then `status`:

| Field | Value | Meaning |
|---|---|---|
| `type` | `chat`, `player_event`, `combat`, `death_event` | a sense; handed to the surface |
| `status` | `FINISHED` / `IDLE` | an action completed; `result` is `SUCCESS`/`FAILURE` |
| `status` | `INTERRUPTED` | something cut the action short; `reason` says what |
| `status` | `ENGAGED_AUTO_ACTION` | the mod defended itself; she is told she is fighting |
| — | contains `player` | a game-state snapshot |

A `death_event` also resolves whatever action was in flight, so nothing waits
out the 60-second timeout for something that is never coming.

**Brain → mod:**

```json
{ "action": "mine_block", "parameters": { "x": 100, "y": 64, "z": 100 } }
```

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
  "system_prompt_path": "data/prompts/minecraft.md",
  "body_prompt_path": "data/prompts/minecraft_body.md"
}
```

| Key | Description |
|---|---|
| `server_url` | WebSocket URL of the BeaCraft mod |
| `idle_nudge_seconds` | How long the body may stand still with an open objective before it tells her. `0` disables it |
| `system_prompt_path` | What the **mind** knows about having a body |
| `body_prompt_path` | The survival guide and crafting chains, for the **body** |

Two prompts, because they are for two different readers: recipe trees belong to
the body, not in her head.

The body uses the `background` model pool; the mind uses `mind`. Neither takes a
Minecraft-specific key.
