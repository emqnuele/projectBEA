from typing import Any, Dict, Optional

from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import Skill


class ChatSurface(Skill):
    """Chat from the web UI, typed or spoken (and a template for twitch/telegram).

    Input only: pushes CHAT and VOICE perceptions. Output is rendered locally by
    Expression (VOICE), so there is no per-surface text sink here.
    """

    name = "chat:ui"

    def _author(self, user: str) -> Author:
        # the local UI is single-user: this is the owner talking
        return Author(platform="ui", native_id=user, display_name=user, is_owner=True)

    def perceive(self, text: str, user: str = "user", meta: Optional[Dict[str, Any]] = None) -> Perception:
        p = Perception(
            kind=PerceptionKind.CHAT,
            surface=self.name,
            content=f"[{user}] {text}",
            salience=0.8,  # someone is talking to you directly
            meta={**(meta or {}), "user": user},
            author=self._author(user),
        )
        self.bus.put(p)
        return p

    def perceive_voice(self, transcript: str, user: str = "user",
                       meta: Optional[Dict[str, Any]] = None) -> Perception:
        """The dashboard microphone: the owner, out loud, in the same room.

        This used to be handed to the discord surface, for no better reason than
        that being where voice had been implemented first. It arrived as an
        unknown person speaking in a call — so the attention gate was entitled
        to let it go by, and did: the mic worked, the transcript came back, and
        she said nothing at all.
        """
        p = Perception(
            kind=PerceptionKind.VOICE,
            surface=self.name,
            content=f"[{user}] (spoken): {transcript}",
            # she is being spoken to directly, with nobody else in the room
            salience=0.9,
            meta={**(meta or {}), "user": user, "listeners": 1,
                  "alone_with_speaker": True},
            author=self._author(user),
        )
        self.bus.put(p)
        return p
