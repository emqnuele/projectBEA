from typing import Optional

from src.core.agent.llm_client import LLMClient
from src.interfaces.base_interfaces import STTInterface
from src.utils.logger import get_logger

logger = get_logger("bea.llm.factory")

# provider -> (module attr, config key for the api key, config key for the model)
_PROVIDERS = {
    "openai": ("openai_key", "openai_model"),
    "groq": ("groq_key", "groq_model"),
    "openrouter": ("openrouter_key", "openrouter_model"),
}


class LLMConfigError(Exception):
    pass


def build_llm(config, stt: Optional[STTInterface] = None) -> LLMClient:
    """Builds the configured tool-aware LLM client.

    Single source of truth for provider selection, shared by the engine entry
    point and any agent (chat, minecraft, ...) that needs its own client.
    """
    provider = config.llm_provider
    if provider not in _PROVIDERS:
        raise LLMConfigError(f"Unknown LLM provider: {provider!r}. Valid: {list(_PROVIDERS)}")

    key_field, model_field = _PROVIDERS[provider]
    api_key = getattr(config, key_field)
    model = getattr(config, model_field)

    if not api_key:
        raise LLMConfigError(f"{key_field} is missing (set it via env, config.json, or CLI).")

    if provider == "openai":
        from src.modules.llm.openai_llm import OpenAILLM
        return OpenAILLM(api_key=api_key, model_name=model, stt_interface=stt)
    if provider == "groq":
        from src.modules.llm.groq_llm import GroqLLM
        return GroqLLM(api_key=api_key, model_name=model, stt_interface=stt)
    if provider == "openrouter":
        from src.modules.llm.openrouter_llm import OpenRouterLLM
        return OpenRouterLLM(api_key=api_key, model_name=model, stt_interface=stt)

    raise LLMConfigError(f"Provider {provider!r} has no builder.")  # unreachable
