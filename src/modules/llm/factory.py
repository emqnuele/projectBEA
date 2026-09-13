from typing import Optional

from src.core.agent.llm_client import LLMClient
from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.reasoning import DEFAULT_LEVEL, style_for
from src.utils.logger import get_logger

logger = get_logger("bea.llm.factory")

# provider -> (config key for the api key, config key for the default model)
_PROVIDERS = {
    "openai": ("openai_key", "openai_model"),
    "groq": ("groq_key", "groq_model"),
    "openrouter": ("openrouter_key", "openrouter_model"),
    # --- new providers ---
    "google_ai_studio": ("google_ai_studio_key", "google_ai_studio_model"),
    "google": ("google_ai_studio_key", "google_ai_studio_model"),
    "gemini": ("google_ai_studio_key", "google_ai_studio_model"),
    "openai_compat": ("openai_compat_key", "openai_compat_model"),
    "openai_compatible": ("openai_compat_key", "openai_compat_model"),
    "local": ("local_key", "local_model"),
    "ollama": ("local_key", "local_model"),
    "lmstudio": ("local_key", "local_model"),
    "claude": ("claude_key", "claude_model"),
    "anthropic": ("claude_key", "claude_model"),
    "anthropic_compat": ("anthropic_compat_key", "anthropic_compat_model"),
    "anthropic_compatible": ("anthropic_compat_key", "anthropic_compat_model"),
}

OPTIONAL_KEY_PROVIDERS = {
    "local", "ollama", "lmstudio",
    "openai_compat", "openai_compatible",
    "anthropic_compat", "anthropic_compatible",
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
    if not api_key and provider not in OPTIONAL_KEY_PROVIDERS:
        raise LLMConfigError(f"{key_field} is missing (set it via env, config.json, or CLI).")

    level = (getattr(config, "models", None) or {}).get("reasoning", DEFAULT_LEVEL)
    reasoning = style_for(provider, level)

    if provider == "openai":
        from src.modules.llm.openai_llm import OpenAILLM
        return OpenAILLM(api_key=api_key, model_name=model, stt_interface=stt,
                         reasoning=reasoning)
    if provider == "groq":
        from src.modules.llm.groq_llm import GroqLLM
        return GroqLLM(api_key=api_key, model_name=model, stt_interface=stt,
                       reasoning=reasoning)
    if provider == "openrouter":
        from src.modules.llm.openrouter_llm import OpenRouterLLM
        return OpenRouterLLM(api_key=api_key, model_name=model, stt_interface=stt,
                             reasoning=reasoning)

    # --- new providers ---

    if provider in ("google_ai_studio", "google", "gemini"):
        from src.modules.llm.google_ai_studio_llm import GoogleAIStudioLLM
        return GoogleAIStudioLLM(api_key=api_key, model_name=model, stt_interface=stt,
                                 reasoning=reasoning)

    if provider in ("openai_compat", "openai_compatible"):
        from src.modules.llm.openai_compat_generic_llm import OpenAICompatibleGenericLLM
        return OpenAICompatibleGenericLLM(
            base_url=getattr(config, "openai_compat_base_url", "http://localhost:8000/v1"),
            api_key=api_key,
            model_name=model,
            stt_interface=stt,
            reasoning=reasoning,
        )

    if provider in ("local", "ollama", "lmstudio"):
        from src.modules.llm.local_llm import LocalLLM
        return LocalLLM(
            base_url=getattr(config, "local_base_url", "http://localhost:11434/v1"),
            api_key=api_key,
            model_name=model,
            stt_interface=stt,
            reasoning=reasoning,
        )

    if provider in ("claude", "anthropic"):
        from src.modules.llm.claude_llm import ClaudeLLM
        return ClaudeLLM(api_key=api_key, model_name=model, stt_interface=stt,
                         reasoning=reasoning)

    if provider in ("anthropic_compat", "anthropic_compatible"):
        from src.modules.llm.anthropic_compat_llm import AnthropicCompatLLM
        return AnthropicCompatLLM(
            base_url=getattr(config, "anthropic_compat_base_url", "https://api.anthropic.com/v1"),
            api_key=api_key,
            model_name=model,
            stt_interface=stt,
            reasoning=reasoning,
        )

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
