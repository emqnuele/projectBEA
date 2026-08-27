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


def _openrouter(level: str) -> ReasoningStyle:
    # unified `reasoning` parameter; enabled:false really switches it off on the
    # hybrid models, and exclude keeps the trace out of the response
    if level == "off":
        return ReasoningStyle({"reasoning": {"enabled": False}}, ("reasoning",))
    return ReasoningStyle({"reasoning": {"effort": level, "exclude": True}}, ("reasoning",))


def _groq(level: str) -> ReasoningStyle:
    # on gpt-oss the effort floor is what it is; reasoning_format=hidden at
    # least keeps the trace out of the text she would otherwise say out loud
    effort = "none" if level == "off" else level
    return ReasoningStyle(
        {"reasoning_effort": effort, "reasoning_format": "hidden"},
        ("reasoning_effort", "reasoning_format"),
    )


def _openai(level: str) -> ReasoningStyle:
    effort = "minimal" if level == "off" else level
    return ReasoningStyle({"reasoning_effort": effort}, ("reasoning_effort",))


_TRANSLATORS = {
    "openrouter": _openrouter,
    "groq": _groq,
    "openai": _openai,
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
