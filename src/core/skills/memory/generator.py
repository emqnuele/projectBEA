import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.core.agent.llm_client import LLMClient
from src.utils.logger import get_logger

logger = get_logger("bea.skills.memory.generator")

class DiaryGenerator:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self._load_prompt()

    def _load_prompt(self):
        try:
            prompt_path = Path(__file__).parent / "diary_prompt.txt"
            if prompt_path.exists():
                self.prompt_template = prompt_path.read_text(encoding="utf-8")
            else:
                self.prompt_template = "You are a diary writer. Summarize the following conversation in JSON."
        except Exception as e:
            logger.error(f"DiaryGenerator: Error loading prompt: {e}")
            self.prompt_template = ""

    async def generate_diary(self, history: List[Dict]) -> Optional[Dict]:
        logger.info("DiaryGenerator: Generating diary with active LLM...")

        # 1. format history
        conversation_text = ""
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            conversation_text += f"{role}: {content}\n"

        # 2. prepare prompt
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        system_prompt = self.prompt_template.replace("{date}", today_str)
        user_prompt = f"CONVERSATION HISTORY:\n{conversation_text}\n\nExisting Tags: []"

        try:
            res = await self.llm.complete_json(user_prompt, system_prompt)
            return res if isinstance(res, dict) else None
        except Exception as e:
            logger.error(f"DiaryGenerator: Generation failed: {e}")
            return None
