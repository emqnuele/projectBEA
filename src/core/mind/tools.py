"""What the mind can do right now.

Assembled fresh on every read. A skill's tool set moves with the skill's own
state and not with whether the skill is on: `discord_leave_voice` exists only
while she is in a call, the objective tools only while there is a plan, the
game tools only while the mod is connected. None of that shows up in the set of
active skills, so a toolbox cached against that set offers the model a prompt
that names tools the schema does not carry — and a model told to call something
it has not been given invents the call. The whole set costs microseconds to
build; correctness is worth more than that.

`speak` and `stay_silent` live here: they belong to the mind, not to a skill.

One loop, one toolbox: written answers go out through `send_message` with an
explicit destination (`platform`, `channel`) — no bound "here", because a
single turn can answer in several places at once. `speak` stays the live
voice; `say_nothing` is the written equivalent of `stay_silent`.
"""

from typing import Callable, List, Optional

from src.core.agent.tools import ToolRegistry
from src.core.expression.tags import DIRECTIONS
from src.core.mind.moods import enum_schema

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

    def platforms(self) -> List[str]:
        """The platforms she can actually write on, right now.

        A skill with a `platform` is not necessarily one that takes text —
        donations have a platform and no channel to answer in, and minecraft
        is typed into with `mc_chat`. Offering her a destination nothing can
        deliver to is a message she sends into a failure.
        """
        return sorted({s.platform for s in self._writers()})

    def writer(self, platform: str):
        """The active skill that can write on `platform`, if there is one."""
        return next((s for s in self._writers() if s.platform == platform), None)

    def _writers(self):
        return (s for s in self.surfaces.active()
                if getattr(s, "platform", "") and callable(getattr(s, "deliver", None)))

    def registry(self) -> ToolRegistry:
        """Every tool armed right now, rebuilt from the live skills."""
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
            reaches=True,
        )
        written = self.platforms()
        if self._send_text is not None and written:
            # the list is read off the live skills rather than written out:
            # naming a platform she cannot reach is a destination she will try
            where = ", ".join(written)
            registry.add(
                "send_message",
                f"Write a text message where it arrived: {where}. The destination "
                "is explicit every time — read it off the [via ...] tag on the "
                "line you answer. Each LINE becomes its own message, with a "
                "typing pause in between — write like you text.",
                {"type": "object", "properties": {
                    "platform": {"type": "string", "enum": written},
                    "channel": {"type": "string",
                                "description": "the channel id from the [via ...] tag"},
                    "text": {"type": "string"},
                    "reply_to": {"type": "string",
                                 "description": "optional message id to quote"}},
                 "required": ["platform", "channel", "text"]},
                self._send_text,
                reaches=True,
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
                reaches=True,
            )
        if self._say_nothing is not None:
            registry.add(
                "say_nothing",
                "Decide this written conversation needs no answer from you. "
                "Perfectly normal — a person doesn't reply to everything.",
                {"type": "object", "properties": {"reason": {"type": "string"}},
                 "required": []},
                self._say_nothing,
                reaches=True,
            )
        for tool in self.surfaces.tools():
            registry.register(tool)
        return registry

    def names(self) -> List[str]:
        """What she can call right now, for the check that the prompt agrees."""
        return [t.name for t in self.registry().tools()]

    def schemas(self) -> Optional[List[dict]]:
        return self.registry().schemas() or None
