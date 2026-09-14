"""How to tell each provider "answer now, don't think about it".

Bea talks in a voice call. A model that spends eight seconds on a reasoning
trace before the first token is not slow, it is broken — the moment has passed
by the time she opens her mouth. Every provider spells the same intent
differently, so it gets translated once, here.

`optional_keys` names the fields a model may reject: some models force
reasoning and answer 400 to anything that switches it off. Those calls are
retried without them instead of failing.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple

# what the config may ask for
LEVELS = ("off", "low", "medium", "high", "auto")

DEFAULT_LEVEL = "off"


@dataclass(frozen=True)
class ReasoningStyle:
    """The extra body one provider needs, and which of it is negotiable."""

    extra_body: Dict[str, Any] = field(default_factory=dict)
    optional_keys: Tuple[str, ...] = ()

    def without_optional(self) -> Dict[str, Any]:
        return {k: v for k, v in self.extra_body.items() if k not in self.optional_keys}

    @property
    def negotiable(self) -> bool:
        return bool(self.optional_keys) and self.without_optional() != self.extra_body


NO_STYLE = ReasoningStyle()


def _openai(level: str) -> ReasoningStyle:
    # chat completions on openai-family models; minimal is the floor there
    effort = "minimal" if level == "off" else level
    return ReasoningStyle({"reasoning_effort": effort}, ("reasoning_effort",))


def _local(level: str) -> ReasoningStyle:
    # ollama documents exactly this scale and maps it in the open: none
    # switches thinking off, while minimal is clamped to low — sending
    # minimal for "off" would leave every local thinker thinking. Without
    # any parameter ollama auto-enables thinking, so omitting it is not
    # an option either. Negotiable all the same: lm studio may refuse
    # none, and then the call goes out unhinted rather than failing.
    effort = "none" if level == "off" else level
    return ReasoningStyle({"reasoning_effort": effort}, ("reasoning_effort",))


def _responses(level: str) -> ReasoningStyle:
    # the responses api carries effort as an object; minimal is the floor for
    # "answer now" on gpt-5, and openrouter documents the same scale.
    # Model-dependent all the way down (newer models accept none, some
    # reject minimal), so negotiable like the rest: whatever refuses it
    # gets the call again without it rather than a failure.
    effort = "minimal" if level == "off" else level
    return ReasoningStyle({"reasoning": {"effort": effort}}, ("reasoning",))


_TRANSLATORS = {
    "openrouter": _responses,
    "groq": _responses,
    "openai": _responses,
    # chat completions shaped
    "local": _local,
    "openai_compat": _openai,
    # google's openai endpoint and the anthropic family take no documented
    # equivalent: gemini thinking levels are a different scale where minimal
    # errors, and anthropic thinking is opt-in with token budgets — both are
    # guesses that turn working models into 400s, and both default to the
    # fast behavior anyway
}


def style_for(provider: str, level: str = DEFAULT_LEVEL) -> ReasoningStyle:
    """The extra body `provider` needs for this reasoning level.

    An unknown provider or level asks for nothing: guessing a parameter name is
    how you turn a working model into a 400.
    """
    level = (level or DEFAULT_LEVEL).strip().lower()
    if level == "auto" or level not in LEVELS:
        return NO_STYLE
    translate = _TRANSLATORS.get((provider or "").strip().lower())
    return translate(level) if translate else NO_STYLE
