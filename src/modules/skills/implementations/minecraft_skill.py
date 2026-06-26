import asyncio
from pathlib import Path

from src.core.agent.runner import AgentHooks
from src.modules.skills.base_skill import BaseSkill
from src.modules.skills.minecraft.agent import MinecraftAgent
from src.modules.skills.minecraft.mc_client import MinecraftClient
from src.utils.logger import get_logger

logger = get_logger("bea.skills.minecraft")

DEFAULT_PROMPT = "You are a Minecraft survival agent. Use the available tools to stay alive and progress."


class MinecraftSkill(BaseSkill):
    """Drives an autonomous Minecraft agent on the shared agent harness.

    The agent reuses the Brain's provider-agnostic LLM and exposes the mod's
    actions as tools; its spoken thoughts are routed back through Bea's voice.
    """

    def initialize(self):
        logger.info(f"Initializing {self.name} skill...")
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()

        self.system_prompt = self._load_prompt()
        self.client = None
        self.agent = None
        self._task = None

    def _load_prompt(self) -> str:
        path = self.skill_config.get("system_prompt_path")
        if path and Path(path).exists():
            try:
                return Path(path).read_text(encoding="utf-8")
            except Exception as e:
                self.log(f"Could not read system prompt ({path}): {e}")
        return DEFAULT_PROMPT

    async def start(self):
        await super().start()

        llm = getattr(self.context, "llm", None)
        if llm is None:
            self.log("Cannot start: no LLM available on the brain.")
            return

        url = self.skill_config.get("server_url", "ws://localhost:8080")
        self.client = MinecraftClient(url, self.loop)
        hooks = AgentHooks(
            on_thought=self._on_thought,
            on_tool_call=lambda name, args: self.log(f"Action: {name}({args})"),
            on_tool_result=lambda name, result: self.log(f"-> {name}: {result}"),
        )
        self.agent = MinecraftAgent(llm, self.client, self.system_prompt, hooks=hooks)

        self.client.connect()
        self._task = asyncio.create_task(self.agent.run())
        self.log("Starting Minecraft agent...")

    async def stop(self):
        await super().stop()
        if self.agent:
            self.agent.stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self.client:
            self.client.stop()
            self.client = None
        self.log("Minecraft agent stopped.")

    def _on_thought(self, thought: str) -> None:
        # routed to the THOUGHT event category by the skill manager
        self.log(f"Thought: {thought}")
        if self.skill_config.get("auto_speak_thoughts", False):
            asyncio.create_task(self._speak(thought))
        if self.skill_config.get("auto_chat_thoughts", False) and self.client:
            safe = thought.replace("\n", " ").strip()[:100]
            asyncio.create_task(self.client.execute("chat", {"message": safe}, instant=True))

    async def _speak(self, thought: str) -> None:
        if not self.context:
            return
        if self.context.is_speaking:
            self.log(f"Skipping TTS (busy): {thought[:30]}...")
            return
        self.context.history_manager.add_message(
            role="assistant", content=thought, mood="normal",
            metadata={"source": "minecraft_thought"},
        )
        await self.context.perform_output_task("normal", thought)

    def on_config_reload(self):
        new_prompt = self._load_prompt()
        if new_prompt != self.system_prompt:
            self.system_prompt = new_prompt
        if self.is_active:
            self.log("Restarting Minecraft agent to apply settings...")
            asyncio.create_task(self._restart())

    async def _restart(self):
        await self.stop()
        await asyncio.sleep(1)
        await self.start()
