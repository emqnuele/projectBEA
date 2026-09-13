from typing import Optional

from openai import OpenAI

from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.openai_compat import OpenAICompatibleClient
from src.modules.llm.reasoning import ReasoningStyle
from src.utils.logger import get_logger

logger = get_logger("bea.llm.openai_compat_generic")


class OpenAICompatibleGenericLLM(OpenAICompatibleClient):
    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: Optional[str] = None,
        model_name: str = "gpt-4o-mini",
        stt_interface: Optional[STTInterface] = None,
        reasoning: Optional[ReasoningStyle] = None,
    ):
        self.base_url = (base_url or "http://localhost:8000/v1").rstrip("/")
        self.api_key = api_key or "not-needed"
        super().__init__(
            OpenAI(api_key=self.api_key, base_url=self.base_url),
            model_name,
            stt_interface,
            reasoning,
        )

    def reload_config(self, config) -> None:
        key = getattr(config, "openai_compat_key", None) or "not-needed"
        base_url = (getattr(config, "openai_compat_base_url", None) or self.base_url).rstrip("/")
        model = getattr(config, "openai_compat_model", None)

        rebuild = False
        if key != self.api_key:
            self.api_key = key
            rebuild = True
        if base_url != self.base_url:
            self.base_url = base_url
            rebuild = True

        if rebuild:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        if model and model != self.model_name:
            self.model_name = model
