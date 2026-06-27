import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class PerceptionKind(str, Enum):
    """What kind of thing Bea just perceived."""

    CHAT = "chat"       # a text message (UI chat, discord text, future twitch/telegram)
    VOICE = "voice"     # a voice transcript (discord voice, UI audio)
    GAME = "game"       # events + state snapshot from the minecraft mod
    ACTION = "action"   # the result of a BODY action that ran asynchronously
    IDLE = "idle"       # time passed with nothing happening
    SYSTEM = "system"   # internal events (session, errors, config)


@dataclass
class Perception:
    """A single sensory input feeding the one consciousness.

    `content` is already-rendered text (e.g. "[mario]: ciao"). `salience` is
    informative, NOT imperative: it hints how strongly this pulls attention, but
    Bea decides what to do with it. `meta` carries routing info (username,
    channel_id, correlation_id, ...).
    """

    kind: PerceptionKind
    surface: str                                   # e.g. "chat:ui", "voice:discord", "game:mc"
    content: str
    salience: float = 0.5
    meta: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ts: float = field(default_factory=time.time)

    def render(self) -> str:
        """How this perception appears inside a perception frame."""
        return self.content
