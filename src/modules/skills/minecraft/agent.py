import asyncio
import json
from typing import Optional

from src.core.agent.llm_client import LLMClient
from src.core.agent.runner import AgentHooks, AgentRunner
from src.modules.skills.minecraft.mc_client import MinecraftClient
from src.modules.skills.minecraft.tools import build_minecraft_tools
from src.utils.logger import get_logger

logger = get_logger("bea.skills.minecraft.agent")


class MinecraftAgent:
    """Continuous survival agent built on the shared agent harness.

    Each cycle perceives the latest game state, runs a bounded reasoning burst
    (think -> call tools -> observe, via `AgentRunner`), then paces until the
    next interrupt or idle tick. Tool observations come back from the mod
    itself, so the model reacts to real outcomes instead of guessing.
    """

    def __init__(
        self,
        llm: LLMClient,
        client: MinecraftClient,
        system_prompt: str,
        hooks: Optional[AgentHooks] = None,
        idle_interval: float = 10.0,
        burst_steps: int = 6,
        history_limit: int = 20,
    ):
        self.client = client
        self.idle_interval = idle_interval
        self.history_limit = history_limit
        self.runner = AgentRunner(llm, build_minecraft_tools(client), max_steps=burst_steps, hooks=hooks)
        self.messages = [{"role": "system", "content": system_prompt}]
        self.running = False

    async def run(self) -> None:
        self.running = True
        await self.client.wait_until_ready()
        logger.info("Minecraft agent ready — entering loop.")

        while self.running:
            try:
                events = self.client.drain_events()
                self.messages.append({"role": "user", "content": self._perceive(events)})
                await self.runner.run(self.messages)
                self._trim()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Agent loop error: {e}")
            await self.client.wait_for_event_or_timeout(self.idle_interval)

    def stop(self) -> None:
        self.running = False

    def _perceive(self, events: list) -> str:
        parts = []
        if events:
            parts.append("EVENTS:\n" + "\n".join(events))
        parts.append("GAME STATE:\n" + json.dumps(self.client.latest_state))
        return "\n\n".join(parts)

    def _trim(self) -> None:
        """Caps context, never leaving an orphan tool message at the front."""
        if len(self.messages) <= self.history_limit + 1:
            return
        tail = self.messages[-self.history_limit:]
        while tail and tail[0].get("role") == "tool":
            tail.pop(0)
        self.messages = [self.messages[0]] + tail
