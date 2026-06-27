import asyncio
from typing import Any, Dict, Optional

from src.core.perception.types import Perception, PerceptionKind
from src.core.skills.base import Skill
from src.core.skills.voice.transport import DiscordTransport
from src.utils.logger import get_logger

logger = get_logger("bea.skills.voice")


class VoiceSurface(Skill):
    """Discord voice capability. Owns the bot transport (node subprocess) and
    turns transcribed speech into VOICE perceptions.

    Input: transcripts arrive via the HTTP endpoints the bot calls -> perceive().
    Output: rendered WAV bytes handed back to the bot (Expression route='remote').
    """

    name = "voice:discord"
    skill_name = "discord"

    def initialize(self) -> None:
        self.transport = DiscordTransport(self.config)
        self._monitor: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if not self.enabled:
            logger.info("VoiceSurface inactive (discord skill disabled).")
            return
        if self.transport.start():
            self.active = True
            self._monitor = asyncio.create_task(self._watch_transport())
            logger.info("VoiceSurface started.")

    async def stop(self) -> None:
        self.active = False
        if self._monitor:
            self._monitor.cancel()
            self._monitor = None
        self.transport.stop()
        logger.info("VoiceSurface stopped.")

    async def _watch_transport(self) -> None:
        """If the bot process dies, the capability goes inactive."""
        while self.active:
            if self.transport.poll_exit() is not None:
                self.active = False
                break
            await asyncio.sleep(2)

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

    async def send_message(self, channel_id: str, content: str) -> bool:
        return await self.transport.send_message(channel_id, content)
