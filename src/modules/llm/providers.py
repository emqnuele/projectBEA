"""Every provider as data: which transport it speaks and where it lives.

Adding a provider that speaks one of the three protocols is one entry here —
no subclass, no branch anywhere else. The factory reads this table; the doctor
and the wizard read it too, so the three never drift apart.
"""

from dataclasses import dataclass
from typing import Dict, Optional

RESPONSES = "responses"
CHAT = "chat"
ANTHROPIC = "anthropic"

TRANSPORTS = (RESPONSES, CHAT, ANTHROPIC)


@dataclass(frozen=True)
class Provider:
    """One row per provider id.

    `base_url` is fixed for first-party endpoints and empty for brought-your-
    own ones, where it comes from the `url_field` config value instead.
    `key_field` empty means no key exists for this provider at all; `needs_key`
    false means the key is optional (localhost, or an endpoint that may not
    want one). `api_choice_field` names a `chat|responses` config knob for
    generic endpoints whose protocol only the owner knows.
    """

    id: str
    transport: str
    base_url: str
    key_field: str
    env_var: str
    model_field: str
    default_model: str
    needs_key: bool
    url_field: str = ""
    send_tool_choice: bool = True
    api_choice_field: str = ""


PROVIDERS: Dict[str, Provider] = {
    "openai": Provider(
        id="openai", transport=RESPONSES, base_url="https://api.openai.com/v1",
        key_field="openai_key", env_var="OPENAI_API_KEY",
        model_field="openai_model", default_model="gpt-5", needs_key=True),
    "openrouter": Provider(
        id="openrouter", transport=RESPONSES, base_url="https://openrouter.ai/api/v1",
        key_field="openrouter_key", env_var="OPENROUTER_API_KEY",
        model_field="openrouter_model", default_model="deepseek/deepseek-v4-flash",
        needs_key=True),
    "groq": Provider(
        id="groq", transport=RESPONSES, base_url="https://api.groq.com/openai/v1",
        key_field="groq_key", env_var="GROQ_API_KEY",
        model_field="groq_model", default_model="openai/gpt-oss-120b",
        needs_key=True),
    "google": Provider(
        id="google", transport=CHAT,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        key_field="google_key", env_var="GOOGLE_API_KEY",
        model_field="google_model", default_model="gemini-3.8-flash",
        needs_key=True),
    "claude": Provider(
        id="claude", transport=ANTHROPIC, base_url="https://api.anthropic.com/v1",
        key_field="claude_key", env_var="ANTHROPIC_API_KEY",
        model_field="claude_model", default_model="claude-sonnet-5",
        needs_key=True),
    # any self-hosted openai-compatible server. chat is the universal default;
    # the owner flips the knob when the endpoint speaks responses.
    "openai_compat": Provider(
        id="openai_compat", transport=CHAT, base_url="",
        key_field="openai_compat_key", env_var="OPENAI_COMPAT_API_KEY",
        model_field="openai_compat_model", default_model="", needs_key=False,
        url_field="openai_compat_base_url", api_choice_field="openai_compat_api"),
    # any anthropic-compatible endpoint.
    "anthropic_compat": Provider(
        id="anthropic_compat", transport=ANTHROPIC, base_url="",
        key_field="anthropic_compat_key", env_var="ANTHROPIC_COMPAT_API_KEY",
        model_field="anthropic_compat_model", default_model="", needs_key=False,
        url_field="anthropic_compat_base_url"),
    # the models on this machine. chat works on every ollama and lm studio;
    # ollama documents tools but rejects tool_choice, hence the quirk.
    "local": Provider(
        id="local", transport=CHAT, base_url="http://localhost:11434/v1",
        key_field="local_key", env_var="LOCAL_API_KEY",
        model_field="local_model", default_model="qwen3:8b", needs_key=False,
        url_field="local_base_url", send_tool_choice=False),
}


def get(provider_id: str) -> Optional[Provider]:
    return PROVIDERS.get((provider_id or "").strip().lower())


__all__ = ["Provider", "PROVIDERS", "TRANSPORTS", "RESPONSES", "CHAT", "ANTHROPIC", "get"]
