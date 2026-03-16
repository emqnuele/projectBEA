import asyncio
from typing import Dict, Type
from src.core.config import BrainConfig
from src.modules.skills.base_skill import BaseSkill
from src.modules.skills.implementations.monologue import MonologueSkill
from src.modules.skills.implementations.minecraft_skill import MinecraftSkill
from src.modules.skills.memory.memory_skill import MemorySkill
from src.modules.skills.discord.discord_skill import DiscordSkill
from src.utils.logger import get_logger

logger = get_logger("bea.skills.manager")

class SkillManager:
    def __init__(self, config: BrainConfig, brain_context):
        self.config = config
        self.context = brain_context
        self.skills: Dict[str, BaseSkill] = {}
        self.running = False
        self._loop_task = None

    def log(self, skill_name: str, message: str):
        # delegate to event manager
        if hasattr(self.context, 'event_manager'):
            from src.core.events import EventCategory
            category = EventCategory.SKILL
            if message.startswith("Thought:"):
                category = EventCategory.THOUGHT
                message = message.replace("Thought:", "").strip()
            
            self.context.event_manager.publish(category, f"skill:{skill_name}", message)
        else:
            logger.info(f"[{skill_name}] {message}")

    def initialize(self):
        """Registers and initializes available skills."""
        logger.info("Initializing Skill Manager...")
        
        # register skills
        self._register_skill("monologue", MonologueSkill)
        self._register_skill("minecraft", MinecraftSkill)
        self._register_skill("memory", MemorySkill)
        self._register_skill("discord", DiscordSkill)

        # initialize skills
        for name, skill in self.skills.items():
            skill.initialize()
            if skill.enabled:
                logger.info(f"Skill '{name}' is enabled in config.")

    def _register_skill(self, name: str, skill_cls: Type[BaseSkill]):
        self.skills[name] = skill_cls(name, self.config, self.context)

    async def start(self):
        """Starts the main skills loop."""
        self.running = True
        
        # start enabled skills
        for skill in self.skills.values():
            if skill.enabled:
                await skill.start()

        self._loop_task = asyncio.create_task(self._main_loop())
        logger.info("Skill Manager started.")

    async def stop(self):
        self.running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        
        for skill in self.skills.values():
            if skill.is_active:
                await skill.stop()
        logger.info("Skill Manager stopped.")

    async def _main_loop(self):
        logger.info("Skill Manager loop active.")
        while self.running:
            for skill in self.skills.values():
                if skill.enabled and not skill.is_active:
                    await skill.start()
                elif not skill.enabled and skill.is_active:
                    await skill.stop()
                
                if skill.is_active:
                    try:
                        await skill.update()
                    except Exception as e:
                        logger.error(f"Error in skill '{skill.name}': {e}")
            
            await asyncio.sleep(1)

    def toggle_skill(self, name: str, state: bool):
        if name in self.skills:
            # update runtime and config
            self.config.skills[name]["enabled"] = state
            self.config.save_to_file()
            return True
        return False

    def reload_config(self):
        """Propagates reload to all skills."""
        for name, skill in self.skills.items():
            try:
                if hasattr(skill, 'on_config_reload'):
                    skill.on_config_reload()
            except Exception as e:
                logger.error(f"Error checking reload for skill '{name}': {e}")
