from typing import Any, Dict, Optional

from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import Skill


class ChatSurface(Skill):
    """Text chat from the web UI (and a template for twitch/telegram later).

    Input only: pushes CHAT perceptions. Output is rendered locally by Expression
    (VOICE), so there is no per-surface text sink here.
    """

    name = "chat:ui"

    def perceive(self, text: str, user: str = "user", meta: Optional[Dict[str, Any]] = None) -> Perception:
        # the local UI is single-user: this is the owner talking
        author = Author(platform="ui", native_id=user, display_name=user, is_owner=True)
        p = Perception(
            kind=PerceptionKind.CHAT,
            surface=self.name,
            content=f"[{user}] {text}",
            salience=0.8,  # someone is talking to you directly
            meta={**(meta or {}), "user": user},
            author=author,
        )
        self.bus.put(p)
        return p
