from typing import Optional

from openai import OpenAI

from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.openai_compat import OpenAICompatibleClient
from src.modules.llm.reasoning import ReasoningStyle
from src.utils.logger import get_logger

logger = get_logger("bea.llm.google_ai_studio")
GOOGLE_AI_STUDIO_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class GoogleAIStudioLLM(OpenAICompatibleClient):
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash",
        stt_interface: Optional[STTInterface] = None,
        reasoning: Optional[ReasoningStyle] = None,
    ):
        self.api_key = api_key
        super().__init__(
            OpenAI(api_key=api_key, base_url=GOOGLE_AI_STUDIO_BASE_URL),
            model_name,
            stt_interface,
            reasoning,
        )

    def reload_config(self, config) -> None:
        key = getattr(config, "google_ai_studio_key", None)
        model = getattr(config, "google_ai_studio_model", None)
        if key and key != self.api_key:
            self.api_key = key
            self.client = OpenAI(api_key=self.api_key, base_url=GOOGLE_AI_STUDIO_BASE_URL)
        if model and model != self.model_name:
            self.model_name = model
