import asyncio
import json
from typing import List, Optional

from src.core.agent.tools import Tool
from src.core.perception.types import Perception, PerceptionKind
from src.core.surfaces.base import Surface
from src.modules.skills.minecraft.mc_client import MinecraftClient
from src.modules.skills.minecraft.notebook import Notebook
from src.modules.skills.minecraft.tools import build_minecraft_tools
from src.utils.prompts import load_text
from src.utils.logger import get_logger

logger = get_logger("bea.surfaces.minecraft")


class MinecraftSurface(Surface):
    """The game body. Perceives game events/state; exposes in-game actions.

    While active it injects the survival rules (context_section) and arms the
    minecraft tools, so Bea only "knows how to play" when actually connected.
    Game events arrive as GAME perceptions; the consciousness reasons over them
    in the same single context as chat and voice.
    """

    name = "game:mc"

    def initialize(self) -> None:
        self._rules = load_text(self.skill_config.get("system_prompt_path", "data/prompts/minecraft.md"))
        self.client: Optional[MinecraftClient] = None
        self.notebook = Notebook()
        self._registry = None
        self._poll_task: Optional[asyncio.Task] = None

    @property
    def skill_config(self) -> dict:
        return self.config.skills.get("minecraft", {})

    async def start(self) -> None:
        url = self.skill_config.get("server_url", "ws://localhost:8080")
        loop = asyncio.get_running_loop()
        self.client = MinecraftClient(url, loop)
        self._registry = build_minecraft_tools(self.client, self.notebook)
        self.client.connect()
        self.active = True
        self._poll_task = asyncio.create_task(self._perceive_loop())
        logger.info("MinecraftSurface started.")

    async def stop(self) -> None:
        self.active = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        if self.client:
            self.client.stop()
            self.client = None
        logger.info("MinecraftSurface stopped.")

    async def _perceive_loop(self) -> None:
        """Streams game events + periodic state snapshots onto the bus."""
        await self.client.wait_until_ready()
        self.bus.put(Perception(PerceptionKind.GAME, self.name, self._snapshot(), salience=0.4))
        while self.active:
            await self.client.wait_for_event_or_timeout(10.0)
            events = self.client.drain_events()
            content = self._snapshot(events)
            salience = 0.9 if events else 0.3  # an interrupt grabs attention
            self.bus.put(Perception(PerceptionKind.GAME, self.name, content, salience=salience))

    def _snapshot(self, events: Optional[List[str]] = None) -> str:
        parts = []
        if events:
            parts.append("EVENTS:\n" + "\n".join(events))
        parts.append("GAME STATE:\n" + json.dumps(self.client.latest_state))
        return "\n\n".join(parts)

    @property
    def context_section(self) -> Optional[str]:
        return self._rules or None

    def tools(self) -> List[Tool]:
        return self._registry.tools() if self._registry else []
