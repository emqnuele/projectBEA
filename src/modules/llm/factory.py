from typing import Optional

from src.core.agent.llm_client import LLMClient
from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.anthropic import AnthropicClient
from src.modules.llm.chat import ChatCompletionsClient
from src.modules.llm.providers import ANTHROPIC, CHAT, RESPONSES, get
from src.modules.llm.reasoning import DEFAULT_LEVEL, style_for
from src.utils.logger import get_logger

logger = get_logger("bea.llm.factory")


class LLMConfigError(Exception):
    pass


def build_client(provider: str, model: str, config,
                 stt: Optional[STTInterface] = None) -> LLMClient:
    """Builds one tool-aware client for an explicit provider/model pair.

    The single place that knows how to instantiate a provider. `ModelRegistry`
    calls it once per pool entry; `build_llm` calls it for the legacy single-model
    path. Transports are natively async over aiohttp: no thread pools.
    """
    preset = get(provider)
    if preset is None:
        from src.modules.llm.providers import PROVIDERS

        raise LLMConfigError(f"Unknown LLM provider: {provider!r}. Valid: {list(PROVIDERS)}")

    api_key = getattr(config, preset.key_field, None) if preset.key_field else None
    if preset.needs_key and not api_key:
        raise LLMConfigError(f"{preset.key_field} is missing (set it via env, config.json, or CLI).")

    base_url = preset.base_url
    if preset.url_field:
        configured = (getattr(config, preset.url_field, None) or "").strip()
        if configured:
            base_url = configured
    if not base_url:
        raise LLMConfigError(f"{preset.url_field} is missing (the endpoint url for "
                             f"{preset.id!r}).")

    transport = preset.transport
    if preset.api_choice_field:
        choice = (getattr(config, preset.api_choice_field, None) or CHAT).strip().lower()
        if choice not in (CHAT, RESPONSES):
            raise LLMConfigError(f"{preset.api_choice_field} must be 'chat' or 'responses'.")
        transport = choice

    level = (getattr(config, "models", None) or {}).get("reasoning", DEFAULT_LEVEL)
    reasoning = style_for(preset.id, level)

    fields = {"key_field": preset.key_field, "model_field": preset.model_field,
              "url_field": preset.url_field}
    if transport == RESPONSES:
        from src.modules.llm.responses import ResponsesClient

        return ResponsesClient(base_url=base_url, model_name=model, api_key=api_key,
                               stt=stt, reasoning=reasoning, **fields)
    if transport == CHAT:
        return ChatCompletionsClient(base_url=base_url, model_name=model, api_key=api_key,
                                     stt=stt, reasoning=reasoning,
                                     send_tool_choice=preset.send_tool_choice, **fields)
    if transport == ANTHROPIC:
        return AnthropicClient(base_url=base_url, model_name=model, api_key=api_key,
                               stt=stt, reasoning=reasoning, **fields)

    raise LLMConfigError(f"Provider {provider!r} has no transport.")  # unreachable


def build_llm(config, stt: Optional[STTInterface] = None) -> LLMClient:
    """Builds the client described by `llm_provider` + `<provider>_model`.

    Kept for callers that want one explicit model rather than a role pool.
    """
    preset = get(getattr(config, "llm_provider", ""))
    if preset is None:
        from src.modules.llm.providers import PROVIDERS

        raise LLMConfigError(f"Unknown LLM provider: {config.llm_provider!r}. "
                             f"Valid: {list(PROVIDERS)}")
    return build_client(preset.id, getattr(config, preset.model_field), config, stt=stt)
