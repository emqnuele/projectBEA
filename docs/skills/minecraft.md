# Minecraft Skill — Autonomous Agent

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What It Does

The Minecraft Skill connects Bea to a Minecraft server via a WebSocket mod and
runs a fully autonomous agent on the shared agent harness that:
- Reads game state (inventory, health, nearby entities, surroundings)
- Decides actions using the engine's main LLM with **native tool calling**
- Executes actions (mine, move, attack, craft, place, look, ...) and reacts to
  the real observation the mod returns
- Posts chat messages in-game and speaks its thoughts via TTS
- Reacts to interrupt events (took damage, fell, ...)

It uses the same `LLMClient` + `AgentRunner` + `ToolRegistry` as the rest of the
app — there is no separate agent framework, no JSON-mode protocol, and no
dedicated LLM key.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  AIVtuberBrain                                           │
│                                                          │
│  MinecraftSkill  (src/.../implementations/minecraft_skill)│
│      ├─ injects the brain's LLMClient                    │
│      └─ hooks: on_thought → Bea speaks via TTS/OBS       │
│                                                          │
│  MinecraftAgent (agent.py)                               │
│      └─ continuous loop: perceive → AgentRunner burst    │
│          ├─ ToolRegistry (tools.py) — mod actions        │
│          └─ MinecraftClient (mc_client.py) — environment │
└──────────────────────────────────────────────────────────┘
                       ↕ WebSocket (ws://localhost:8080)
┌──────────────────────────────────────────────────────────┐
│  Minecraft + BeaCraft mod (game state + actions)         │
└──────────────────────────────────────────────────────────┘
```

Each cycle the agent perceives the latest game state, runs a bounded reasoning
burst (`AgentRunner`), and paces until the next interrupt or idle tick. Tool
handlers send a command and **await** the mod's completion event, returning the
result as the observation the model reasons on next.

---

## The Custom Mod: BeaCraft

The agent requires **BeaCraft**, a custom Fabric mod that exposes game state and
accepts commands over a WebSocket server on the Minecraft client machine.

### Download

| Source | Link |
|---|---|
| **Modrinth** | [modrinth.com/project/projectbea](https://modrinth.com/project/projectbea/) |
| **GitHub Releases** | [Latest Release](https://github.com/emqnuele/projectbea/releases/latest) — `beacraft-1.0.0.jar` |

### Installation

1. Install [Fabric Loader](https://fabricmc.net/use/installer/) for your Minecraft version.
2. Download `beacraft-1.0.0.jar` and drop it into `.minecraft/mods/`.
3. Launch Minecraft — the mod starts a WebSocket server on `ws://localhost:8080`.
4. Ensure `server_url` in `config.json` matches (default `ws://localhost:8080`).

### Protocol

**State broadcast (Mod → Agent)** — a full game-state packet:
```json
{ "player": { "health": 20.0, "hunger": 18, "position": {...}, "inventory": [...], "surroundings": [...] }, "is_busy": false }
```

**Event packets (Mod → Agent)**

| `status` | Meaning |
|---|---|
| `"IDLE"` / `"FINISHED"` | Action completed. `result` is `"SUCCESS"`/`"FAILURE"`. Resolves the awaited tool call. |
| `"INTERRUPTED"` | Action interrupted (damage, fall, ...). `reason` is surfaced to the agent as an event/observation. |

**Command packets (Agent → Mod)** — emitted by tool handlers:
```json
{ "action": "mine_block", "parameters": { "x": 100, "y": 64, "z": 100 } }
```

The `action` matches a tool name in the registry. The mod runs it and replies
with a completion event.

---

## File Structure

```
src/modules/skills/minecraft/
├── agent.py        MinecraftAgent — continuous perceive/act loop
├── tools.py        Tool schemas + handlers (build_minecraft_tools)
└── mc_client.py    WebSocket client = the agent's environment
```

The skill wrapper is `src/modules/skills/implementations/minecraft_skill.py`.
The shared loop/LLM/tool primitives live in `src/core/agent/`.

---

## Available Tools

`mine_block`, `move_to`, `stop_moving`, `attack_entity`, `look_at`,
`find_block`, `place_block`, `select_slot`, `pillar_up`, `mine_down`, `bridge`,
`craft_item`, `use_block`, `smelt_item`, `store_item`, `retrieve_item`,
`equip_item`, `discard_item`, `eat_food`, `check_death_log`,
`request_screenshot`, `chat`.

Instant actions (`chat`, `request_screenshot`, `check_death_log`, `stop_moving`)
return immediately; all others await the mod's completion event.

---

## Thought Broadcasting

The agent's natural-language thoughts arrive via the `AgentRunner`'s
`on_thought` hook. If `auto_speak_thoughts` is set, the skill speaks them
through Bea's TTS/OBS pipeline (skipping when she's already talking); if
`auto_chat_thoughts` is set, they are also sent to in-game chat.

---

## Thread Safety

`MinecraftClient` runs the blocking WebSocket on a background thread but hands
every packet to the asyncio loop via `call_soon_threadsafe`, so all agent state
lives on one thread and tool handlers can simply `await` completion — no locks.

---

## Configuration

```json
"minecraft": {
  "enabled": false,
  "server_url": "ws://localhost:8080",
  "auto_chat_thoughts": false,
  "auto_speak_thoughts": false,
  "system_prompt_path": "data/prompts/minecraft.txt"
}
```

| Key | Description |
|---|---|
| `server_url` | WebSocket URL of the BeaCraft mod |
| `auto_speak_thoughts` | TTS-speak agent thoughts as Bea's commentary |
| `auto_chat_thoughts` | Also send thoughts as in-game chat messages |
| `system_prompt_path` | Custom system prompt for the Minecraft context |

The agent uses the engine's main `llm_provider`/model — no separate key.
