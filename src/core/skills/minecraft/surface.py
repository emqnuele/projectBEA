import asyncio
from typing import List, Optional

from src.core.agent.tools import Tool
from src.core.perception.types import Perception, PerceptionKind
from src.core.skills.base import Skill
from src.core.skills.minecraft.client import MinecraftClient
from src.core.skills.minecraft.notebook import Notebook
from src.core.skills.minecraft.state import render_state
from src.core.skills.minecraft.tools import build_minecraft_tools
from src.utils.logger import get_logger
from src.utils.prompts import load_text

logger = get_logger("bea.skills.minecraft")


class MinecraftSurface(Skill):
    """The game body. Perceives game events/state; exposes in-game actions.

    While active it injects the survival rules (context_section) and arms the
    minecraft tools, so Bea only "knows how to play" when actually connected.
    Game events arrive as GAME perceptions; the consciousness reasons over them
    in the same single context as chat and voice.
    """

    name = "game:mc"
    skill_name = "minecraft"

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
        if not self.skill_config.get("enabled", False):
            logger.info("MinecraftSurface inactive (minecraft skill disabled).")
            return
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
        """Streams game events onto the bus.

        The periodic snapshot is deliberately marked `noise`: the state is always
        available as live_state, so it does not need to wake the mind. Only real
        events (interrupts, deaths) do.
        """
        if self.client is None:
            return
        await self.client.wait_until_ready()
        self.bus.put(Perception(PerceptionKind.GAME, self.name,
                                "You just woke up inside Minecraft.", salience=0.4,
                                meta={"first_state": True}))
        while self.active and self.client is not None:
            await self.client.wait_for_event_or_timeout(10.0)
            if self.client is None:
                break
            events = self.client.drain_events()
            if not events:
                # a heartbeat with nothing in it: the state is already live_state,
                # so don't pay to serialize 700 lidar blocks nobody will read
                self.bus.put(Perception(PerceptionKind.GAME, self.name, "(still playing)",
                                        salience=0.15, meta={"noise": True}))
                continue
            self.bus.put(Perception(
                PerceptionKind.GAME, self.name, self._snapshot(events), salience=0.9,
            ))

    def _snapshot(self, events: Optional[List[str]] = None) -> str:
        parts = []
        if events:
            parts.append("EVENTS:\n" + "\n".join(events))
        parts.append("GAME STATE:\n" + render_state(self._latest_state()))
        return "\n\n".join(parts)

    def _latest_state(self) -> dict:
        return self.client.latest_state if self.client is not None else {}

    @property
    def context_section(self) -> Optional[str]:
        return self._rules or None

    def tools(self) -> List[Tool]:
        return self._registry.tools() if self._registry else []

    def live_state(self) -> Optional[str]:
        if not self.active:
            return None
        parts = [
            "YOUR NOTEBOOK (private working memory — never spoken; update it with "
            "update_notebook):\n" + self.notebook.render()
        ]
        # the game state lives here rather than in a perception: it is *where she
        # is*, always true, not an event that should make her think
        body = render_state(self._latest_state())
        if body:
            parts.append("YOUR BODY IN MINECRAFT (right now):\n" + body)
        return "\n\n".join(parts)
