from typing import Any, Dict, Optional

from src.core.perception.types import Perception, PerceptionKind
from src.core.skills.base import Skill


class ChatSurface(Skill):
    """Text chat from the web UI (and a template for twitch/telegram later).

    Input only: pushes CHAT perceptions. Output is rendered locally by Expression
    (VOICE), so there is no per-surface text sink here.
    """

    name = "chat:ui"

    def perceive(self, text: str, user: str = "user", meta: Optional[Dict[str, Any]] = None) -> Perception:
        p = Perception(
            kind=PerceptionKind.CHAT,
            surface=self.name,
            content=f"[{user}] {text}",
            salience=0.8,  # someone is talking to you directly
            meta={**(meta or {}), "user": user},
        )
        self.bus.put(p)
        return p
