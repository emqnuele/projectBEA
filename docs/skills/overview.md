# Skills — Plugin System Overview

← [Back to README](../../README.md) | [Architecture](../architecture.md)

---

## What is a Skill?

A Skill is a self-contained background capability that extends Bea's behavior beyond basic chat. Skills are managed by the `SkillManager` and follow a consistent lifecycle. They run asynchronously alongside the main brain loop.

Examples of skills:
- [`Memory`](memory.md) — stores and retrieves long-term memories
- [`Discord`](discord.md) — joins voice calls and speaks
- [`Minecraft`](minecraft.md) — plays Minecraft autonomously
- [`Monologue`](monologue.md) — talks to the audience when idle

---

## File Structure

```
src/modules/skills/
├── base_skill.py          Abstract base class for all skills
├── skill_manager.py       Orchestrator — registers, starts, loops skills
├── memory/                Memory / RAG skill
├── discord/               Discord voice skill
├── minecraft/             Minecraft agent skill
└── implementations/
    ├── monologue.py       Monologue idle skill
    └── minecraft_skill.py MinecraftSkill wrapper
```

---

## `BaseSkill` API

**File:** `src/modules/skills/base_skill.py`

```python
class BaseSkill(ABC):
    # Core attributes
    name: str               # Unique skill identifier
    config: BrainConfig     # Reference to global config
    context: AIVtuberBrain  # Reference to the brain
    is_active: bool         # Whether the skill is currently running
    _execution_lock: asyncio.Lock  # Per-skill asyncio lock (set in __init__)

    # Lifecycle hooks
    def initialize(self)          # Called once at startup
    async def start(self)         # Called when skill is enabled
    async def stop(self)          # Called when skill is disabled
    async def update(self)        # Called every second by the skill loop
    def on_config_reload(self)    # Called on hot reload

    # Helpers
    @property
    def skill_config(self) -> dict   # Returns config.skills[self.name]

    @property
    def enabled(self) -> bool        # Reads skill_config["enabled"]

    def log(self, message: str)      # Routes via SkillManager.log() → EventManager.publish()
                                    # Messages starting with "Thought:" are automatically
                                    # promoted to EventCategory.THOUGHT and the prefix stripped.
```

---

## `SkillManager`

**File:** `src/modules/skills/skill_manager.py`

The `SkillManager` owns the skill loop. It runs as a background asyncio task.

### Initialization flow

```
SkillManager.initialize()
    ├─ _register_skill("monologue", MonologueSkill)
    ├─ _register_skill("minecraft", MinecraftSkill)
    ├─ _register_skill("memory",    MemorySkill)
    └─ _register_skill("discord",   DiscordSkill)
          └─ for each skill: skill.initialize()
```

### Startup

Before the loop begins, `SkillManager.start()` immediately calls `await skill.start()` for every skill that is already `enabled` at launch time. This means memory-enabled skills are active before the first loop tick fires.

### Main loop (every 1 second)

```
_main_loop():
    for each skill:
        if skill.enabled and not skill.is_active:
            await skill.start()
        elif not skill.enabled and skill.is_active:
            await skill.stop()
        if skill.is_active:
            await skill.update()
```

This means enabling a skill in `config.json` (or via the web API) at runtime will cause the skill to start on the next loop tick without any restart.

### `toggle_skill(name, state)`

Called by the web API's `POST /skills/{name}/toggle?enable=bool` endpoint. Sets `config.skills[name]["enabled"]` and saves to `config.json`.

---

## Skill Configuration

Each skill has its own section under `config.json → "skills"`:

```json
"skills": {
  "memory":    { "enabled": true,  ... },
  "discord":   { "enabled": false, ... },
  "minecraft": { "enabled": false, ... },
  "monologue": { "enabled": false, ... }
}
```

Changing `enabled` in the config file or via the web UI will start/stop the skill at runtime.

---

## Creating a New Skill

1. Create `src/modules/skills/my_skill.py`:

```python
from src.modules.skills.base_skill import BaseSkill

class MySkill(BaseSkill):
    def initialize(self):
        self.my_setting = self.skill_config.get("my_setting", "default")

    async def update(self):
        if self.context.is_speaking:
            return
        # your logic here
        self.log("Doing something!")
```

2. Register it in `SkillManager.initialize()`:

```python
self._register_skill("my_skill", MySkill)
```

3. Add its config section to `config.json`:

```json
"my_skill": { "enabled": false, "my_setting": "value" }
```

The skill is now visible in the web dashboard's Skills page and can be toggled at runtime.

---

## Skill Pages

| Skill | Document |
|---|---|
| Memory (RAG) | [memory.md](memory.md) |
| Discord Voice | [discord.md](discord.md) |
| Minecraft Agent | [minecraft.md](minecraft.md) |
| Monologue | [monologue.md](monologue.md) |
