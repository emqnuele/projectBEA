from abc import ABC
from typing import Any, Dict, List, Optional

from src.core.agent.tools import Tool
from src.utils.logger import get_logger

logger = get_logger("bea.surfaces")


class Surface(ABC):
    """A channel through which Bea perceives and/or expresses.

    One surface = one input adapter (pushes `Perception`s onto the bus) plus an
    optional output sink (renders what Bea decides to send to it). Adding a new
    channel later (Twitch, Telegram) means writing one Surface subclass — the
    consciousness and Expression never change.
    """

    name: str = "surface"
    # which skill toggle (config.skills[...]) gates this surface; None = always on (core)
    skill_name: Optional[str] = None

    def __init__(self, config, bus, expression, context=None):
        self.config = config
        self.bus = bus
        self.expression = expression
        self.context = context
        self.active = False

    @property
    def enabled(self) -> bool:
        """A surface is a capability gate: on only when its skill is toggled on."""
        if self.skill_name is None:
            return True
        return bool(self.config.skills.get(self.skill_name, {}).get("enabled", False))

    def initialize(self) -> None:
        """One-time setup (no connections yet)."""

    async def start(self) -> None:
        """Open connections and begin pushing perceptions onto the bus."""
        if not self.enabled:
            logger.info(f"Surface '{self.name}' stays inactive (skill '{self.skill_name}' disabled).")
            return
        self.active = True

    async def stop(self) -> None:
        self.active = False

    # --- output sinks (override the ones this surface supports) -------------

    async def emit_text(self, text: str, meta: Optional[Dict[str, Any]] = None) -> None:
        """Send a text message out on this surface (discord/twitch/telegram)."""

    async def emit_voice(self, audio_bytes: bytes, meta: Optional[Dict[str, Any]] = None) -> None:
        """Send rendered voice audio out on this surface (discord voice)."""

    # --- context contributed while this surface is active ------------------

    @property
    def context_section(self) -> Optional[str]:
        """Prompt rules injected into the single context only while active.

        e.g. the minecraft survival rules appear only when connected to the game.
        """
        return None

    def tools(self) -> List[Tool]:
        """Tools armed only while this surface is active (e.g. in-game actions)."""
        return []

    def live_state(self) -> Optional[str]:
        """Volatile state injected into every perception frame (e.g. the game notebook)."""
        return None


class SurfaceRegistry:
    """Holds the active set of surfaces and aggregates what they contribute."""

    def __init__(self):
        self._surfaces: Dict[str, Surface] = {}

    def register(self, surface: Surface) -> None:
        self._surfaces[surface.name] = surface

    def get(self, name: str) -> Optional[Surface]:
        return self._surfaces.get(name)

    def all(self) -> List[Surface]:
        return list(self._surfaces.values())

    def active(self) -> List[Surface]:
        return [s for s in self._surfaces.values() if s.active]

    def context_sections(self) -> List[str]:
        return [s.context_section for s in self.active() if s.context_section]

    def tools(self) -> List[Tool]:
        out: List[Tool] = []
        for s in self.active():
            out.extend(s.tools())
        return out
