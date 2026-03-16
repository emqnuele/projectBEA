from src.modules.skills.base_skill import BaseSkill
from src.modules.skills.minecraft.mc_agent.core.agent import Agent
from src.modules.skills.minecraft.mc_agent.core.config import Config as MCConfig
from src.core.events import EventCategory
from src.utils.logger import get_logger
import logging
import asyncio

logger = get_logger("bea.skills.minecraft")

class MinecraftSkill(BaseSkill):
    def initialize(self):
        logger.info(f"Initializing {self.name} skill...")
        
        # capture the main loop for thread-safe callbacks
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            
        # sync config
        config_dict = {
            "openai_key": self.config.openai_key,
            "minecraft": self.skill_config
        }
        MCConfig.update_from_dict(config_dict)
        
        # pending speech tracking
        self.pending_speech = 0

        # initialize agent with callback
        try:
            self.agent = Agent(
                on_thought_callback=self._on_agent_thought
            )
            self._setup_logging()
            self.log("Minecraft Agent initialized successfully.")
            
        except Exception as e:
            self.log(f"Failed to initialize Minecraft Agent: {e}")
            self.agent = None

    def _on_agent_thought(self, thought: str):
        """Callback from Agent (Background Thread) -> Main Loop."""
        if self.skill_config.get("auto_speak_thoughts", False):
            self.pending_speech += 1
            
            # schedule task
            asyncio.run_coroutine_threadsafe(
                self._speak_thought(thought), 
                self.loop
            )

    async def _speak_thought(self, thought: str):
        """Executes on main loop."""
        try:
            # check busy state
            if self.context and self.context.is_speaking:
                # skip tts if busy
                self.log(f"Skipping TTS (Busy): {thought[:30]}...")
                self.context.history_manager.add_message(
                    role="assistant", 
                    content=thought, 
                    mood="normal", 
                    metadata={"source": "minecraft_thought", "audio_skipped": True}
                )
                return

            # infer mood
            if self.context:
                # save to history
                self.context.history_manager.add_message(
                    role="assistant", 
                    content=thought, 
                    mood="normal", 
                    metadata={"source": "minecraft_thought"}
                )
                await self.context.perform_output_task("normal", thought)
        finally:
            if self.pending_speech > 0:
                self.pending_speech -= 1

    def _setup_logging(self):
        """Attaches a custom handler to capture agent logs."""
        class BridgeHandler(logging.Handler):
            def __init__(self, skill_instance):
                super().__init__()
                self.skill = skill_instance
            
            def emit(self, record):
                try:
                    msg = self.format(record)
                    self.skill.log(msg)
                except Exception:
                    self.handleError(record)

        handler = BridgeHandler(self)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        
        for logger_name in ["Agent", "MinecraftWS"]:
            l = logging.getLogger(logger_name)
            l.addHandler(handler)

    async def start(self):
        if not self.agent:
            self.log("Cannot start: Agent not initialized.")
            return
            
        await super().start()
        self.log("Starting Minecraft Agent Connection...")
        try:
            self.agent.start()
        except Exception as e:
            self.log(f"CRITICAL: Failed to start Minecraft Agent: {e}")

    async def stop(self):
        await super().stop()
        if self.agent:
            self.log("Stopping Minecraft Agent...")
            try:
                self.agent.stop()
            except Exception as e:
                self.log(f"Error stopping Minecraft Agent: {e}")

    async def update(self):
        # sync config
        if self.agent:
            try:
                config_dict = {
                    "openai_key": self.config.openai_key,
                    "minecraft": self.skill_config
                }
                MCConfig.update_from_dict(config_dict)
            except Exception as e:
                pass

    def on_config_reload(self):
        """Checks if critical MC config changed and restarts agent if needed."""
        self.log("Handling Config Reload...")
        
        # update static config
        MCConfig.update_from_dict({
            "openai_key": self.config.openai_key,
            "minecraft": self.skill_config
        })
        
        # restart agent if active
        if self.is_active and self.agent:
            new_url = self.skill_config.get("server_url")
            self.log("Restarting Agent Connection to apply settings...")
            asyncio.create_task(self._restart_agent())

    async def _restart_agent(self):
        if self.agent:
            self.agent.stop()
            await asyncio.sleep(1)
            self.agent.start()
