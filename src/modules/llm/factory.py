from typing import Optional

from src.core.agent.llm_client import LLMClient
from src.interfaces.base_interfaces import STTInterface
from src.utils.logger import get_logger

logger = get_logger("bea.llm.factory")

# provider -> (config key for the api key, config key for the default model)
_PROVIDERS = {
    "openai": ("openai_key", "openai_model"),
    "groq": ("groq_key", "groq_model"),
    "openrouter": ("openrouter_key", "openrouter_model"),
}


class LLMConfigError(Exception):
    pass


def build_client(provider: str, model: str, config,
                 stt: Optional[STTInterface] = None) -> LLMClient:
    """Builds one tool-aware client for an explicit provider/model pair.

    The single place that knows how to instantiate a provider. `ModelRegistry`
    calls it once per pool entry; `build_llm` calls it for the legacy single-model
    path.
    """
    if provider not in _PROVIDERS:
        raise LLMConfigError(f"Unknown LLM provider: {provider!r}. Valid: {list(_PROVIDERS)}")

    key_field, _ = _PROVIDERS[provider]
    api_key = getattr(config, key_field, None)
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


def build_llm(config, stt: Optional[STTInterface] = None) -> LLMClient:
    """Builds the client described by `llm_provider` + `<provider>_model`.

    Kept for callers that want one explicit model rather than a role pool.
    """
    provider = config.llm_provider
    if provider not in _PROVIDERS:
        raise LLMConfigError(f"Unknown LLM provider: {provider!r}. Valid: {list(_PROVIDERS)}")
    _, model_field = _PROVIDERS[provider]
    return build_client(provider, getattr(config, model_field), config, stt=stt)
