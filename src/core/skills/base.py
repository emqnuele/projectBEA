from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable

from src.core.agent.tools import Tool
from src.utils.logger import get_logger

logger = get_logger("bea.skills")


@runtime_checkable
class SkillContext(Protocol):
    """The brain, as much of it as a skill is allowed to reach for.

    A protocol rather than the class itself: skills are built by the brain and
    hold a reference back to it, so naming the concrete type here would be a
    cycle. This also says plainly what that reference is for — everything a
    skill reads is on this list, and anything that is not is a skill reaching
    past what it was given.
    """

    memory: Any
    history_manager: Any
    event_manager: Any
    skill_registry: Any
    surface_registry: Any
    consciousness: Any
    stt: Any
    llm: Any

    def model_for(self, role: str) -> Any:
        ...


# not an ABC: every hook below is optional, a skill overrides only what it supports
class Skill:
    """A toggleable capability of the one consciousness.

    A skill may do any subset of these — all optional:
    - perceive: push `Perception`s onto the bus (the senses: chat, voice, game)
    - expose tools: `tools()` armed only while the skill is active
    - contribute static prompt rules: `context_section` (e.g. game survival rules)
    - contribute dynamic context per batch: `context_for(batch)` (e.g. memory RAG)
    - own infrastructure: `start`/`stop` (a bot process, a WS client, a vector store)

    This single abstraction replaces the old Surface/BaseSkill split. The
    `skill_name` is the config/UI toggle key; `None` means a core skill that is
    always on and not shown as a toggle (e.g. the UI chat input).
    """

    name: str = "skill"
    skill_name: Optional[str] = None  # config.skills[...] toggle key; None = core/always-on

    def __init__(self, config, bus, expression, context: Optional[SkillContext] = None):
        self.config = config
        self.bus = bus
        self.expression = expression
        self.context = context
        self.active = False

    @property
    def brain(self) -> SkillContext:
        """The brain this skill belongs to, for the skills that cannot work without one.

        Most of what a skill reads off `context` is optional and asked for with
        `getattr`. Memory is not: a skill built around it is broken without one,
        and saying so here is better than the `NoneType has no attribute` four
        lines later that names neither the skill nor what it was missing.
        """
        if self.context is None:
            raise RuntimeError(
                f"skill '{self.name}' needs the brain it is part of, and was built without one")
        return self.context

    @property
    def enabled(self) -> bool:
        """The UI is the single source of truth: on only when its toggle is on."""
        if self.skill_name is None:
            return True
        return bool(self.config.skills.get(self.skill_name, {}).get("enabled", False))

    def initialize(self) -> None:
        """One-time setup (no connections/processes yet)."""

    async def start(self) -> None:
        """Open connections/processes and begin contributing. Gated by `enabled`."""
        if not self.enabled:
            logger.info(f"Skill '{self.name}' stays inactive (toggle '{self.skill_name}' off).")
            return
        self.active = True

    async def stop(self) -> None:
        self.active = False

    # --- output sinks (override the ones this skill supports) ---------------

    async def emit_text(self, text: str, meta: Optional[Dict[str, Any]] = None) -> List[str]:
        """Send a text message out on this skill (discord/twitch/telegram).

        Returns the id of each message that went out — one line of hers can
        become several — so a caller can reply into the thread it just started.
        Nothing sent, nothing returned.

        There is deliberately no `emit_voice` beside it: audio leaves the brain
        in exactly one place, `Expression`, which is what lets ducking, stopping
        and knowing how far a sentence got live together.
        """
        return []

    # --- context contributed while this skill is active --------------------

    @property
    def context_section(self) -> Optional[str]:
        """Static prompt rules injected while active (e.g. minecraft survival)."""
        return None

    def context_for(self, batch) -> Optional[str]:
        """Dynamic context computed from the current perception batch (e.g. RAG)."""
        return None

    def tools(self) -> List[Tool]:
        """Tools armed only while active (e.g. in-game actions, recall_memory)."""
        return []

    def conversation_tools(self, channel_id: Optional[str],
                           reply_to: Optional[str] = None) -> List[Tool]:
        """Tools for a SCOPED conversation turn in one channel.

        Deliberately a different set from `tools()`: a scoped turn has no voice
        and no body, and the channel is context rather than an argument — she is
        talking in one place, so she should not have to name it every time.
        """
        return []

    def live_state(self) -> Optional[str]:
        """Volatile state injected into every perception frame (e.g. the notebook)."""
        return None


class SkillRegistry:
    """The single catalog of capabilities. The UI reads it; the consciousness
    iterates it for active tools, prompt sections and dynamic context."""

    def __init__(self):
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def get_by_key(self, skill_name: str) -> Optional[Skill]:
        """Looks up a skill by its config/UI toggle key (skill_name)."""
        for s in self._skills.values():
            if s.skill_name == skill_name:
                return s
        return None

    def all(self) -> List[Skill]:
        return list(self._skills.values())

    def toggleable(self) -> List[Skill]:
        """Skills that appear as UI toggles (have a config key)."""
        return [s for s in self._skills.values() if s.skill_name]

    def active(self) -> List[Skill]:
        return [s for s in self._skills.values() if s.active]

    def _contribution(self, skill: Skill, what: str, call) -> Optional[str]:
        """One block of context, or nothing at all when producing it went wrong.

        A skill that raises while describing itself used to take the whole turn
        with it: the loop caught the error far away from here, so what reached
        the log named neither the skill nor what it had been asked for, and she
        said nothing at all rather than saying something without that block.
        """
        try:
            return call()
        except Exception as e:
            logger.error(f"Skill '{skill.name}' could not contribute its {what}: {e}",
                         exc_info=True)
            return None

    def context_sections(self, exclude: Sequence[str] = ()) -> List[str]:
        out: List[str] = []
        for s in self.active():
            if s.name in exclude:
                continue
            text = self._contribution(s, "prompt section", lambda s=s: s.context_section)
            if text:
                out.append(text)
        return out

    def live_states(self) -> List[str]:
        out: List[str] = []
        for s in self.active():
            text = self._contribution(s, "live state", lambda s=s: s.live_state())
            if text:
                out.append(text)
        return out

    def dynamic_context(self, batch) -> List[str]:
        out: List[str] = []
        for s in self.active():
            text = self._contribution(s, "context for this batch", lambda s=s: s.context_for(batch))
            if text:
                out.append(text)
        return out

    def tools(self) -> List[Tool]:
        out: List[Tool] = []
        for s in self.active():
            out.extend(s.tools())
        return out
