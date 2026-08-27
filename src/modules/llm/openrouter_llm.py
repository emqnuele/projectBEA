from typing import Optional

from openai import OpenAI

from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.openai_compat import OpenAICompatibleClient
from src.modules.llm.reasoning import ReasoningStyle
from src.utils.logger import get_logger

logger = get_logger("bea.llm.openrouter")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterLLM(OpenAICompatibleClient):
    """OpenRouter routes one OpenAI-compatible endpoint to virtually any model
    (set `model` to e.g. `openai/gpt-4o-mini`, `anthropic/claude-3.5-sonnet`,
    `google/gemini-2.0-flash`). Tool use works through the standard API."""

    def __init__(self, api_key: str, model_name: str = "openai/gpt-4o-mini", stt_interface: Optional[STTInterface] = None,
                 reasoning: Optional[ReasoningStyle] = None):
        self.api_key = api_key
        super().__init__(OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL), model_name, stt_interface, reasoning)

    def reload_config(self, config) -> None:
        if config.openrouter_key != self.api_key:
            self.api_key = config.openrouter_key
            self.client = OpenAI(api_key=self.api_key, base_url=OPENROUTER_BASE_URL)
        if config.openrouter_model != self.model_name:
            self.model_name = config.openrouter_model
