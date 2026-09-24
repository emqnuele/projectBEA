import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class PerceptionKind(str, Enum):
    """What kind of thing Bea just perceived."""

    CHAT = "chat"       # a text message (UI chat, discord text, future twitch/telegram)
    VOICE = "voice"     # a voice transcript (discord voice, UI audio)
    GAME = "game"       # events + state snapshot from the minecraft mod
    ACTION = "action"   # the result of a BODY action that ran asynchronously
    IDLE = "idle"       # time passed with nothing happening
    SYSTEM = "system"   # internal events (session, errors, config)


@dataclass
class Author:
    """Stable identity of whoever produced a perception.

    `identity` (platform:native_id) is the source of truth — deterministic and
    stable across renames. `display_name` is cosmetic and may change. This is the
    foundation the social memory builds on: without a structured author there is
    no roster, no per-person memory, no cross-platform identity.
    """

    platform: str        # "ui" | "discord" | "telegram" | "twitch" | "donation"
    native_id: str       # stable native id of the account (NOT the display name)
    display_name: str
    is_owner: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)  # e.g. donation amount

    @property
    def identity(self) -> str:
        return f"{self.platform}:{self.native_id}"


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
    author: Optional[Author] = None                # who produced it (None for system/idle/game)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ts: float = field(default_factory=time.time)

    @property
    def is_noise(self) -> bool:
        """a heartbeat already carried by the live state: it must not wake the mind."""
        return bool((self.meta or {}).get("noise"))

    @property
    def is_memorable(self) -> bool:
        """the idle tick is the loop talking to itself; everything else happened."""
        return self.kind is not PerceptionKind.IDLE and not self.is_noise

    @property
    def kept(self) -> str:
        """What stays of it once its turn is over.

        Usually all of it. A sense that delivers something bulky — a whole web
        page — says what to keep instead, so the window and the stream hold one
        line rather than paying for the page on every turn after.
        """
        return str((self.meta or {}).get("keep_as") or self.content)

    def render(self, now: Optional[float] = None, kept: bool = False) -> str:
        """How this perception appears inside a perception frame.

        With `now`, anything old enough to matter says so. A batch that spans a
        few seconds gets no stamps at all — they would be noise on every line.
        `kept` renders what stays of it rather than what arrived.
        """
        text = self.kept if kept else self.content
        if now is None:
            return text
        from src.core.timeline import stamp_for

        return f"{stamp_for(now - self.ts)}{text}"
