import asyncio

from src.core.agent.runner import AgentHooks
from src.modules.skills.base_skill import BaseSkill
from src.modules.skills.minecraft.agent import MinecraftAgent
from src.modules.skills.minecraft.mc_client import MinecraftClient
from src.utils.prompts import load_text, compose
from src.utils.logger import get_logger

logger = get_logger("bea.skills.minecraft")

DEFAULT_RULES = "You are playing Minecraft. Use the available tools to stay alive and progress."


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

        self.rules = self._load_rules()
        self.system_prompt = self._build_prompt()
        self.client = None
        self.agent = None
        self._task = None

    def _load_rules(self) -> str:
        path = self.skill_config.get("system_prompt_path")
        return load_text(path, DEFAULT_RULES) if path else DEFAULT_RULES

    def _build_prompt(self) -> str:
        """Bea's shared soul + the minecraft-specific rules."""
        soul = getattr(self.context, "soul", "")
        return compose(soul, self.rules)

    async def start(self):
        await super().start()

        # the single-brain consciousness drives minecraft via MinecraftSurface
        if getattr(self.context, "consciousness_active", False):
            self.log("Skipping legacy minecraft agent: consciousness owns the game.")
            return

        llm = getattr(self.context, "llm", None)
        if llm is None:
            self.log("Cannot start: no LLM available on the brain.")
            return

        self.system_prompt = self._build_prompt()
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
        self.rules = self._load_rules()
        new_prompt = self._build_prompt()
        if new_prompt != self.system_prompt:
            self.system_prompt = new_prompt
        if self.is_active:
            self.log("Restarting Minecraft agent to apply settings...")
            asyncio.create_task(self._restart())

    async def _restart(self):
        await self.stop()
        await asyncio.sleep(1)
        await self.start()
