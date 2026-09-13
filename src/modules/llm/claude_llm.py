from typing import Optional

from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.anthropic_compat import AnthropicCompatibleClient
from src.modules.llm.reasoning import ReasoningStyle
from src.utils.logger import get_logger

logger = get_logger("bea.llm.claude")
CLAUDE_BASE_URL = "https://api.anthropic.com/v1"


class ClaudeLLM(AnthropicCompatibleClient):
    def __init__(
        self,
        api_key: str,
        model_name: str = "claude-3-7-sonnet-latest",
        stt_interface: Optional[STTInterface] = None,
        reasoning: Optional[ReasoningStyle] = None,
    ):
        super().__init__(
            api_key=api_key,
            base_url=CLAUDE_BASE_URL,
            model_name=model_name,
            stt_interface=stt_interface,
            reasoning=reasoning,
        )

    def reload_config(self, config) -> None:
        key = getattr(config, "claude_key", None)
        model = getattr(config, "claude_model", None)
        if key and key != self.api_key:
            self.api_key = key
        if model and model != self.model_name:
            self.model_name = model
