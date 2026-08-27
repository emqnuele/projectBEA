from typing import Optional

from groq import Groq

from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.openai_compat import OpenAICompatibleClient
from src.modules.llm.reasoning import ReasoningStyle
from src.utils.logger import get_logger

logger = get_logger("bea.llm.groq")


class GroqLLM(OpenAICompatibleClient):
    def __init__(self, api_key: str, model_name: str = "llama3-70b-8192", stt_interface: Optional[STTInterface] = None,
                 reasoning: Optional[ReasoningStyle] = None):
        self.api_key = api_key
        super().__init__(Groq(api_key=api_key), model_name, stt_interface, reasoning)

    def reload_config(self, config) -> None:
        if config.groq_key != self.api_key:
            self.api_key = config.groq_key
            self.client = Groq(api_key=self.api_key)
        if config.groq_model != self.model_name:
            self.model_name = config.groq_model
