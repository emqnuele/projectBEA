"""What the mind can do right now.

The set only changes when a capability is toggled, so it is cached and
invalidated then rather than rebuilt on every model step. `speak` and
`stay_silent` live here: they belong to the mind, not to a skill.

One loop, one toolbox: written answers go out through `send_message` with an
explicit destination (`platform`, `channel`) — no bound "here", because a
single turn can answer in several places at once. `speak` stays the live
voice; `say_nothing` is the written equivalent of `stay_silent`.
"""

from typing import Callable, List, Optional

from src.core.agent.tools import Tool, ToolRegistry
from src.core.expression.tags import DIRECTIONS
from src.core.mind.moods import enum_schema
from src.utils.logger import get_logger

logger = get_logger("bea.mind.tools")

MOOD, DO = DIRECTIONS


class MindTools:
    """The mind's toolbox: its own three, plus whatever the active skills offer."""

    def __init__(self, surfaces, *, speak: Callable, stay_silent: Callable,
                 send_text: Optional[Callable] = None,
                 react_to: Optional[Callable] = None,
                 say_nothing: Optional[Callable] = None):
        self.surfaces = surfaces
        self._speak = speak
        self._stay_silent = stay_silent
        self._send_text = send_text
        self._react_to = react_to
        self._say_nothing = say_nothing
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
            "acting while it plays. Use this for the voice call, the stream, and the "
            "dashboard chat — never for telegram/discord/twitch/minecraft text.",
            {"type": "object", "properties": {
                # an enum, not a description: the model is told what exists
                # rather than asked to remember it
                "mood": {"type": "string", "enum": enum_schema(),
                         "description": "The face you start the line with."},
                "message": {
                    "type": "string",
                    "description": (
                        f"What you say. You may change your face and move part-way "
                        f"through it by writing <{MOOD}:word> or <{DO}:word> inline; "
                        f"neither is ever spoken."
                    ),
                },
            }, "required": ["mood", "message"]},
            self._speak,
        )
        registry.add(
            "stay_silent",
            "Choose to say nothing right now.",
            {"type": "object", "properties": {"reason": {"type": "string"}}, "required": []},
            self._stay_silent,
        )
        if self._send_text is not None:
            registry.add(
                "send_message",
                "Write a text message where it arrived: telegram, discord text, "
                "twitch chat, minecraft chat. The destination is explicit every "
                "time — read it off the [via ...] tag on the line you answer. "
                "Each LINE becomes its own message, with a typing pause in "
                "between — write like you text.",
                {"type": "object", "properties": {
                    "platform": {"type": "string",
                                 "description": "telegram, discord, twitch or minecraft"},
                    "channel": {"type": "string",
                                "description": "the channel id from the [via ...] tag"},
                    "text": {"type": "string"},
                    "reply_to": {"type": "string",
                                 "description": "optional message id to quote"}},
                 "required": ["platform", "channel", "text"]},
                self._send_text,
            )
        if self._react_to is not None:
            registry.add(
                "react",
                "React to a message with a single emoji, instead of writing. "
                "Only where the [via ...] tag shows a platform with reactions.",
                {"type": "object", "properties": {
                    "platform": {"type": "string"},
                    "channel": {"type": "string"},
                    "message_id": {"type": "string"},
                    "emoji": {"type": "string"}},
                 "required": ["platform", "channel", "message_id", "emoji"]},
                self._react_to,
            )
        if self._say_nothing is not None:
            registry.add(
                "say_nothing",
                "Decide this written conversation needs no answer from you. "
                "Perfectly normal — a person doesn't reply to everything.",
                {"type": "object", "properties": {"reason": {"type": "string"}},
                 "required": []},
                self._say_nothing,
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
