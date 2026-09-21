from typing import Optional

from openai import OpenAI

from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.openai_compat import OpenAICompatibleClient
from src.utils.logger import get_logger

logger = get_logger("bea.llm.omniroute")

OMNIROUTE_BASE_URL = "http://localhost:20128/v1"


class OmniRouteLLM(OpenAICompatibleClient):
    """OmniRoute local proxy (OpenAI-compatible) at localhost:20128.

    Uses the same OpenAI SDK client shape as the OpenAI and OpenRouter paths,
    just with a different base URL and the HERMES_CUSTOM_OMNIROUTE_API_KEY
    environment variable as the default key source.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "auto/best-chat",
        stt_interface: Optional[STTInterface] = None,
        base_url: str = OMNIROUTE_BASE_URL,
    ):
        self.api_key = api_key
        self.base_url = base_url
        super().__init__(
            OpenAI(api_key=api_key, base_url=base_url),
            model_name,
            stt_interface,
        )

    def reload_config(self, config) -> None:
        if config.omniroute_key and config.omniroute_key != self.api_key:
            self.api_key = config.omniroute_key
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        if getattr(config, "omniroute_model", None) and config.omniroute_model != self.model_name:
            self.model_name = config.omniroute_model
