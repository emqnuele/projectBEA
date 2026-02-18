# Minecraft Skill — Autonomous Agent

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What It Does

The Minecraft Skill connects Bea to a Minecraft server via a WebSocket mod and runs a fully autonomous LLM agent that:
- Reads game state (inventory, health, nearby entities, surroundings)
- Plans actions using an LLM with tool-calling
- Executes actions (mine blocks, move, attack, craft, look around)
- Requests screenshots for visual context
- Posts chat messages in-game and speaks its thoughts via TTS
- Follows a survival plan and maintains persistent goals

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Python (AIVtuberBrain)                                  │
│                                                          │
│  MinecraftSkill (skill wrapper)                          │
│      ├─ initializes Agent in background thread           │
│      └─ bridges Agent.on_thought → brain.perform_output  │
│                                                          │
│  mc_agent/                                               │
│      └─ Agent (state machine + LLM tool-calling loop)    │
│          ├─ MinecraftClient (WebSocket ↔ MC mod)         │
│          └─ OpenAIClient (LLM with tools)                │
└──────────────────────────────────────────────────────────┘
                       ↕ WebSocket (ws://localhost:8080)
┌──────────────────────────────────────────────────────────┐
│  Minecraft Server                                        │
│  with custom mod/plugin exposing game state + actions    │
└──────────────────────────────────────────────────────────┘
```

---

## The Custom Mod: BeaCraft

The Python agent cannot connect to a vanilla Minecraft server — it requires **BeaCraft**, a custom Fabric mod developed alongside ProjectBEA that exposes game state and accepts commands over a WebSocket server running on the same machine as the Minecraft client.

### Download

| Source | Link |
|---|---|
| **Modrinth** | [modrinth.com/project/projectbea](https://modrinth.com/project/projectbea/) |
| **GitHub Releases** | [Latest Release](https://github.com/emqnuele/projectbea/releases/latest) — download `beacraft-1.0.0.jar` |

### Installation

1. Install [Fabric Loader](https://fabricmc.net/use/installer/) for your Minecraft version.
2. Download `beacraft-1.0.0.jar` from Modrinth or GitHub Releases.
3. Drop it into your `.minecraft/mods/` folder.
4. Launch Minecraft — the mod starts a WebSocket server on `ws://localhost:8080` automatically.
5. Ensure `server_url` in `config.json` matches (default is `ws://localhost:8080`).

### What the Mod Does

BeaCraft exposes two interfaces over WebSocket:

**State broadcast (Mod → Agent)**  
Periodically (or on change) the mod pushes a full game state packet:
```json
{
  "player": {
    "health": 20.0,
    "hunger": 18,
    "position": {"x": 100, "y": 64, "z": 200},
    "inventory": [...],
    "surroundings": [...]
  },
  "is_busy": false,
  "current_action": null
}
```

**Event packets (Mod → Agent)**

| `status` field | Meaning |
|---|---|
| `"IDLE"` / `"FINISHED"` | Previous action completed. `result` is `"SUCCESS"` or `"FAILURE"`. |
| `"INTERRUPTED"` | Action was interrupted (e.g., player took damage, fell). Includes `event.reason`. |
| `"ENGAGED_AUTO_ACTION"` | Mod autonomously performed an action (e.g., dodge). Agent transitions to `BUSY` and waits for `FINISHED`. |

**Command packets (Agent → Mod)**  
All commands follow the same envelope:
```json
{
  "action": "mine_block",
  "parameters": {
    "x": 100,
    "y": 64,
    "z": 100
  }
}
```

The `action` field matches the tool names in the LLM tool schema (see [Available Tools](#available-tools-llm-callable) below). The mod executes the action, then sends back a `FINISHED` packet when done.

---

## File Structure

```
src/modules/skills/minecraft/
├── mc_agent/
│   ├── core/
│   │   ├── agent.py           Main agent loop + tool dispatch
│   │   ├── config.py          Agent config (MC_SERVER_URL, model, etc.)
│   │   └── state_machine.py   AgentState enum + transitions
│   ├── interfaces/
│   │   ├── minecraft_ws.py    WebSocket client to the MC mod
│   │   └── openai_client.py   OpenAI tool-calling client
│   └── utils/
│       └── logger.py
└── main.py                    Standalone entry point (dev/testing)
```

The `MinecraftSkill` wrapper lives at `src/modules/skills/implementations/minecraft_skill.py`.

---

## Agent State Machine

```
IDLE
  │ new game state received
  ▼
THINKING
  │ LLM processes state + history → selects tool call
  ▼
EXECUTING
  │ tool dispatched to MC mod via WebSocket
  ▼
WAITING_FOR_RESULT
  │ MC mod sends back result event
  ▼
IDLE (loop)
```

---

## Available Tools (LLM-callable)

| Tool | Description |
|---|---|
| `mine_block(x, y, z)` | Navigate to and mine a block at coordinates |
| `move_to(x, y, z)` | Move to specific coordinates |
| `stop_moving()` | Cancel current movement |
| `attack_entity(target)` | Attack entity by ID |
| `look_at(x, y, z)` | Rotate camera to face coordinates |
| `find_block(block_type)` | Search for nearest block of given type |
| `place_block(x, y, z, face)` | Place a held block |
| `craft_item(recipe_key)` | Craft an item |
| `equip_item(item_name, destination)` | Equip item to hand/armor slot |
| `open_inventory()` | Open inventory for inspection |
| `chat_message(text)` | Send a message in Minecraft chat |
| `request_screenshot()` | Capture current view for visual context |
| `get_surroundings()` | Get nearby blocks and entities |

---

## Initial Survival Plan

The agent is initialized with a structured survival checklist:

```
- [ ] GET WOOD: Mine 4-5 logs using find_block('log')
- [ ] CRAFT BASICS (1): Planks → Crafting Table
- [ ] CRAFT BASICS (2): Planks → Sticks
- [ ] CRAFT BASICS (3): Wooden Pickaxe
- [ ] GET STONE: Mine 3 Stone/Cobble
- [ ] UPGRADE: Craft Stone Pickaxe
- [ ] GATHER: Coal (Torches) & Iron
- [ ] FOOD: Hunt animals if Hunger < 15
```

The LLM updates this checklist as tasks are completed.

---

## Thought Broadcasting

When the agent has a thought or narrates its actions, the callback fires:

```python
def _on_agent_thought(self, thought: str):
    if skill_config["auto_speak_thoughts"]:
        asyncio.run_coroutine_threadsafe(
            self._speak_thought(thought), 
            self.loop  # main asyncio loop
        )
```

`_speak_thought()` checks if the brain is busy and either speaks the thought via TTS + OBS or logs it silently to history.

---

## Thread Safety

The Minecraft Agent runs in a **background thread** (blocking WebSocket + LLM calls). Thoughts are bridged to the **main asyncio loop** via `asyncio.run_coroutine_threadsafe()`. This is the standard pattern for integrating blocking I/O with asyncio.

---

## Configuration

```json
"minecraft": {
  "enabled": false,
  "server_url": "ws://localhost:8080",
  "max_history_events": 20,
  "debug_mode": true,
  "auto_chat_thoughts": false,
  "auto_speak_thoughts": false,
  "mc_openai_model": "gpt-4o-mini",
  "system_prompt_path": "data/prompts/minecraft.txt"
}
```

| Key | Description |
|---|---|
| `server_url` | WebSocket URL of the Minecraft mod server |
| `max_history_events` | How many past game events the agent keeps in context |
| `auto_speak_thoughts` | TTS-speak agent thoughts as Bea's commentary |
| `auto_chat_thoughts` | Also send thoughts as in-game chat messages |
| `mc_openai_model` | The model used by the agent (separate from the main LLM) |
| `system_prompt_path` | Custom system prompt for the Minecraft context |

---

## Agent Logging Bridge

A custom `BridgeHandler` (Python logging `Handler`) is attached to the `Agent` and `MinecraftWS` loggers. Every log message from the agent is forwarded to the `EventManager` as an `EventCategory.SKILL` event, making it visible in the Brain Activity page of the web dashboard.

---

## Standalone Mode

The agent can also be run directly without ProjectBEA:

```bash
cd src/modules/skills/minecraft
python main.py
```

This is useful for testing the agent independently of the VTuber engine.
