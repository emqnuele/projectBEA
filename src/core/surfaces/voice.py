from typing import Any, Dict, Optional

from src.core.perception.types import Perception, PerceptionKind
from src.core.surfaces.base import Surface


class VoiceSurface(Surface):
    """Discord voice. Input: transcribed speech -> VOICE perceptions.

    Output: rendered WAV bytes handed back to the Discord bot (the bot plays them
    in the call). Generation itself happens in Expression(route="remote").
    """

    name = "voice:discord"

    def perceive(self, transcript: str, user: str, meta: Optional[Dict[str, Any]] = None) -> Perception:
        p = Perception(
            kind=PerceptionKind.VOICE,
            surface=self.name,
            content=f"[{user}] (voice): {transcript}",
            salience=0.85,
            meta={**(meta or {}), "user": user},
        )
        self.bus.put(p)
        return p

    async def emit_voice(self, audio_bytes: bytes, meta: Optional[Dict[str, Any]] = None) -> None:
        # delivery to the bot is handled via the HTTP correlation in Fase 4;
        # kept here so the surface owns its output contract.
        return None
