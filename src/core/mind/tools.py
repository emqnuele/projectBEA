"""What the mind can do right now.

The set only changes when a capability is toggled, so it is cached and
invalidated then rather than rebuilt on every model step. `speak` and
`stay_silent` live here: they belong to the mind, not to a skill.
"""

from typing import Callable, List, Optional

from src.core.agent.tools import Tool, ToolRegistry
from src.core.mind.moods import enum_schema
from src.utils.logger import get_logger

logger = get_logger("bea.mind.tools")


class MindTools:
    """The mind's toolbox: its own two, plus whatever the active skills offer."""

    def __init__(self, surfaces, *, speak: Callable, stay_silent: Callable):
        self.surfaces = surfaces
        self._speak = speak
        self._stay_silent = stay_silent
        self._cache: Optional[ToolRegistry] = None
        self._cached_for: tuple = ()

    def invalidate(self) -> None:
        """Called when a capability is toggled: the set of tools just changed."""
        self._cache = None

    def registry(self) -> ToolRegistry:
        signature = tuple(sorted(s.name for s in self.surfaces.active()))
        if self._cache is not None and signature == self._cached_for:
            return self._cache

        registry = ToolRegistry()
        registry.add(
            "speak",
            "Say something out loud (with a facial expression). Non-blocking: you keep "
            "acting while it plays.",
            {"type": "object", "properties": {
                # an enum, not a description: the model is told what exists
                # rather than asked to remember it
                "mood": {"type": "string", "enum": enum_schema()},
                "message": {"type": "string"},
            }, "required": ["mood", "message"]},
            self._speak,
        )
        registry.add(
            "stay_silent",
            "Choose to say nothing right now.",
            {"type": "object", "properties": {"reason": {"type": "string"}}, "required": []},
            self._stay_silent,
        )
        for tool in self.surfaces.tools():
            registry.register(tool)

        self._cache = registry
        self._cached_for = signature
        logger.debug(f"Tool registry rebuilt: {len(registry)} tools for {signature}.")
        return registry

    def schemas(self) -> Optional[List[dict]]:
        return self.registry().schemas() or None

    def get(self, name: str) -> Optional[Tool]:
        return self.registry().get(name)
