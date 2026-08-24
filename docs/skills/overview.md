# Skills — the capability layer

← [Back to README](../../README.md) | [Architecture](../architecture.md)

---

## What a skill is

A **skill** is one capability of the single consciousness. There is one loop —
the consciousness — and a skill plugs into it by doing any subset of these:

| Hook | What it does |
|---|---|
| perceive | pushes `Perception` objects onto the bus — this is a *sense* |
| `tools()` | tools armed only while the skill is active |
| `conversation_tools(channel_id, reply_to)` | a different, smaller set for a scoped conversation turn |
| `context_section` | static prompt rules mounted while active |
| `context_for(batch)` | prompt content computed from the current batch (e.g. recall) |
| `live_state()` | volatile state injected into every frame (e.g. where her body is) |
| `start()` / `stop()` | owns infrastructure — a subprocess, a WebSocket, a poller |

**File:** `src/core/skills/base.py`

```python
class Skill:
    name: str                        # unique id, e.g. "voice:discord"
    skill_name: Optional[str] = None # config/UI toggle key; None = core, always on

    def __init__(self, config, bus, expression, context=None)
    def initialize(self) -> None                  # one-time setup, no connections
    async def start(self) -> None                 # gated by `enabled`
    async def stop(self) -> None
```

`enabled` reads `config.skills[skill_name].enabled`. **The UI is the single
source of truth** — Bea can never arm a capability by herself. A skill with
`skill_name = None` is core: always on, never shown as a toggle.

---

## `SkillRegistry`

The catalog. It has no loop and no scheduler: the consciousness iterates it when
it builds a prompt or dispatches a tool.

```python
registry.all()              # every skill
registry.active()           # the ones currently running
registry.toggleable()       # the ones with a config key (what the UI lists)
registry.get(name)          # by `name`
registry.get_by_key(key)    # by `skill_name`
registry.context_sections() # static rules from active skills
registry.dynamic_context(batch)
registry.tools()            # every tool from every active skill
```

Everything is built in `AIVtuberBrain._build_consciousness()` and started by
`Consciousness.start()`, which calls `start()` on each one.

---

## The skills

| Skill | `name` | toggle | What it does |
|---|---|---|---|
| `ChatSurface` | `chat:ui` | — (core) | text from the dashboard; the author is the owner |
| `StreamPlanSkill` | `plan` | — (core) | [today's objectives](plan.md); contributes nothing while the plan is empty |
| `VoiceSurface` | `voice:discord` | `discord` | [Discord](discord.md) voice + text; owns the node subprocess |
| `TelegramSkill` | `chat:telegram` | `telegram` | [Telegram](telegram.md), in-process |
| `TwitchSkill` | `chat:twitch` | `twitch` | [Twitch](twitch.md) chat, read anonymously |
| `DonationSkill` | `donation` | `donations` | [donations](donations.md) via webhook |
| `MinecraftSurface` | `game:mc` | `minecraft` | [the game body](minecraft.md) |
| `IdleSurface` | `idle` | `monologue` | [the passage of time](monologue.md) |
| `MemorySkill` | `memory` | `memory` | [long-term recall](memory.md) and the diary |
| `SocialMemory` | `social` | `social_memory` | [who people are](social.md) |
| `DreamSkill` | `dream` | `dream` | [sleep, self-lore, consolidation](dream.md) |

---

## Tools by owner

`speak` and `stay_silent` belong to the mind itself (`src/core/mind/tools.py`),
not to a skill. Everything else is armed by whichever skill is active:

| Owner | Tools |
|---|---|
| the mind | `speak`, `stay_silent` |
| `plan` | `objective_started`, `objective_done`, `objective_dropped` |
| `voice:discord` | `discord_send_message`, `discord_reply`, `discord_react`, `discord_send_dm`, `discord_list_voice_channels`, `discord_join_voice`, `discord_leave_voice`, `discord_summon` |
| `chat:telegram` | `telegram_send_message` |
| `chat:twitch` | `twitch_say` |
| `donation` | `recall_donors` |
| `game:mc` | `play_minecraft`, `mc_chat`, `mc_stop`, `mc_goto_player`, `mc_follow_player`, `mc_look_at_player`, `mc_give_item` |
| `social` | `remember_person`, `recall_person` |
| `dream` | `go_to_sleep` |
| `memory` | none — recall is injected every turn via `context_for` |

The registry is built once and cached; it is rebuilt only when a capability is
toggled (`MindTools.invalidate()`), not on every model step.

A **scoped conversation turn** gets a different set: `reply`, `send_message`,
`react`, `say_nothing`, plus `remember_person`. No `speak` and no body actions —
absent by construction, not by a rule in the prompt.

---

## Two shapes of skill

**A platform** (Discord, Telegram, Twitch) extends `PlatformSkill`
(`src/core/skills/platform.py`) instead of `Skill`. It only owes three things —
`platform`, a way to build an `Author`, and a way to send text — and inherits
perception building, the humanizer delivery and the conversation tools.

**Everything else** extends `Skill` directly.

---

## Adding a skill

1. Create `src/core/skills/my_skill/surface.py`:

```python
from src.core.skills.base import Skill


class MySkill(Skill):
    name = "my:skill"
    skill_name = "my_skill"   # the config/UI toggle key

    def initialize(self) -> None:
        self.setting = self.config.skills.get("my_skill", {}).get("setting", "default")

    def tools(self):
        if not self.active:
            return []
        return [...]
```

2. Add it to the tuple in `AIVtuberBrain._build_consciousness()`.
3. Add its block to `config.example.json` under `skills`.

It now appears in the dashboard's Skills page and can be toggled at runtime.

If it is a text platform, extend `PlatformSkill` instead and the roster, person
cards, attention gate and scoped conversations work with no extra code —
they are all keyed on `Author` and `conversation_key`.
