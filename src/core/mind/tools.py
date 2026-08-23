"""What the mind can do right now, assembled once instead of per step.

The registry used to be rebuilt from scratch on every call to `_tool_schemas()`
AND on every `_dispatch()` — two or more full rebuilds per model step, each one
walking every active skill and constructing every Tool object.

The set only changes when a capability is toggled, so it is cached and
invalidated then. `speak` and `stay_silent` live here because they are not a
skill's: they are what the mind itself does.
"""

from typing import Callable, List, Optional

from src.core.agent.tools import Tool, ToolRegistry
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
                "mood": {"type": "string",
                         "description": "normal, shock, love, cry, angry, ew, bored"},
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
