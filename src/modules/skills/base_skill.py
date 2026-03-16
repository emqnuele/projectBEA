from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from src.core.config import BrainConfig
from src.utils.logger import get_logger
import asyncio

logger = get_logger("bea.skills.base")

class BaseSkill(ABC):
    def __init__(self, name: str, config: BrainConfig, context: Any = None):
        """
        :param name: Unique name of the skill (e.g., 'monologue')
        :param config: Reference to the global BrainConfig
        :param context: Reference to the Brain or specific managers (LLM, TTS, OBS)
        """
        self.name = name
        self.config = config
        self.context = context
        self.is_active = False
        self._execution_lock = asyncio.Lock()

    def log(self, message: str):
        """Logs a message to the SkillManager."""
        if self.context and hasattr(self.context, 'skill_manager'):
            self.context.skill_manager.log(self.name, message)
        else:
            logger.info(f"[{self.name}] {message}")

    @property
    def skill_config(self) -> Dict[str, Any]:
        """Returns the specific config dict for this skill."""
        return self.config.skills.get(self.name, {})

    @property
    def enabled(self) -> bool:
        return self.skill_config.get("enabled", False)

    @abstractmethod
    def initialize(self):
        """Called once when the skill is loaded."""
        pass

    async def start(self):
        """Called when the skill is manually started or enabled."""
        self.is_active = True
        logger.info(f"Skill '{self.name}' started.")

    async def stop(self):
        """Called when the skill is stopped or disabled."""
        self.is_active = False
        logger.info(f"Skill '{self.name}' stopped.")

    async def update(self):
        """
        Called continuously by the SkillManager loop.
        Should return quickly.
        """
        pass

    def on_config_reload(self):
        """
        Called when global configuration is hot-reloaded.
        Override this to handle dynamic updates (e.g. reconnection).
        """
        pass
