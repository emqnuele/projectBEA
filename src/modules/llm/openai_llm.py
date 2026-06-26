from typing import Optional

from openai import OpenAI

from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.openai_compat import OpenAICompatibleClient
from src.utils.logger import get_logger

logger = get_logger("bea.llm.openai")


class OpenAILLM(OpenAICompatibleClient):
    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini", stt_interface: Optional[STTInterface] = None):
        self.api_key = api_key
        super().__init__(OpenAI(api_key=api_key), model_name, stt_interface)

    def reload_config(self, config) -> None:
        if config.openai_key != self.api_key:
            self.api_key = config.openai_key
            self.client = OpenAI(api_key=self.api_key)
        if config.openai_model != self.model_name:
            self.model_name = config.openai_model
