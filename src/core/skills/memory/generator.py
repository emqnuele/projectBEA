"""The diary pass: one finished conversation into one page she keeps.

It runs on the background model, after she has already answered, and what it
writes is injected back into her context by retrieval for as long as it stays
relevant. That is why it is told which language to write in: a pass that always
wrote English quietly pulled an Italian conversation back towards English every
turn, and the drift looked like it was coming out of the model.
"""

import datetime
from typing import Dict, List, Optional

from src.core.agent.llm_client import LLMClient
from src.core.language import write_in
from src.core.persona import Persona
from src.utils.logger import get_logger
from src.utils.prompts import load_text

logger = get_logger("bea.skills.memory.generator")

DEFAULT_PROMPT_PATH = "data/prompts/diary.md"

FALLBACK = ("You are a diary writer. Summarize the following conversation in JSON, "
            "with `diary_content`, `tags` and `user_id`.")


class DiaryGenerator:
    def __init__(self, llm: LLMClient, *, persona: Optional[Persona] = None,
                 language: str = "", prompt_path: str = DEFAULT_PROMPT_PATH):
        self.llm = llm
        self.persona = persona or Persona()
        self.language = language
        self.prompt_path = prompt_path or DEFAULT_PROMPT_PATH

    @property
    def prompt_template(self) -> str:
        """Read per pass, not cached: it is an editable file like every other."""
        return self.persona.fill(load_text(self.prompt_path, fallback=FALLBACK))

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
        system_prompt = (self.prompt_template
                         .replace("{date}", today_str)
                         .replace("{language}", write_in(self.language)))
        user_prompt = f"CONVERSATION HISTORY:\n{conversation_text}\n\nExisting Tags: []"

        try:
            res = await self.llm.complete_json(user_prompt, system_prompt)
            return res if isinstance(res, dict) else None
        except Exception as e:
            logger.error(f"DiaryGenerator: Generation failed: {e}")
            return None
