from typing import Optional

from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.anthropic_compat import AnthropicCompatibleClient
from src.modules.llm.reasoning import ReasoningStyle
from src.utils.logger import get_logger

logger = get_logger("bea.llm.anthropic_compat_llm")


class AnthropicCompatLLM(AnthropicCompatibleClient):
    def __init__(
        self,
        base_url: str = "https://api.anthropic.com/v1",
        api_key: Optional[str] = None,
        model_name: str = "claude-3-7-sonnet-latest",
        stt_interface: Optional[STTInterface] = None,
        reasoning: Optional[ReasoningStyle] = None,
    ):
        super().__init__(
            api_key=api_key or "not-needed",
            base_url=base_url,
            model_name=model_name,
            stt_interface=stt_interface,
            reasoning=reasoning,
        )

    def reload_config(self, config) -> None:
        key = getattr(config, "anthropic_compat_key", None) or "not-needed"
        base_url = (getattr(config, "anthropic_compat_base_url", None) or self.base_url).rstrip("/")
        model = getattr(config, "anthropic_compat_model", None)

        if key != self.api_key:
            self.api_key = key
        if base_url != self.base_url:
            self.base_url = base_url
        if model and model != self.model_name:
            self.model_name = model
