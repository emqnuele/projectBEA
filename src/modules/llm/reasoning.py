"""How to tell each provider "answer now, don't think about it".

Bea talks in a voice call. A model that spends eight seconds on a reasoning
trace before the first token is not slow, it is broken — the moment has passed
by the time she opens her mouth. Every provider spells the same intent
differently, so it gets translated once, here.

`optional_keys` names the fields a model may reject: some models force
reasoning and answer 400 to anything that switches it off. Those calls are
retried without them instead of failing — the ordinary one and the streamed
one alike.

"off" means *as little as this endpoint allows*, and that is not the same
string everywhere. OpenRouter documents an explicit switch; gpt-5 has a floor
rather than an off; groq's gpt-oss only takes low, medium and high. Writing one
of those names into another provider's request is how a working model turns
into a 400, so each one is spelled out on its own line below with what it is.
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


def _openai_chat(level: str) -> ReasoningStyle:
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


def _openai(level: str) -> ReasoningStyle:
    # the responses api carries effort as an object. `minimal` is the floor for
    # "answer now" on gpt-5 — there is no off — and newer models accept `none`,
    # which is why this stays negotiable rather than guessing per model.
    effort = "minimal" if level == "off" else level
    return ReasoningStyle({"reasoning": {"effort": effort}}, ("reasoning",))


def _openrouter(level: str) -> ReasoningStyle:
    # openrouter documents a switch rather than a floor: `enabled: false` turns
    # reasoning off on every family it routes to, while `effort` is an
    # openai-family scale that a deepseek or a qwen simply ignores. Sending the
    # floor to switch it off is how a model went on thinking for eight seconds
    # a turn with the config saying reasoning was off.
    if level == "off":
        return ReasoningStyle({"reasoning": {"enabled": False}}, ("reasoning",))
    return ReasoningStyle({"reasoning": {"effort": level}}, ("reasoning",))


def _groq(level: str) -> ReasoningStyle:
    # groq's own models take low, medium and high and nothing below: `none` is
    # accepted by some of them and rejected by gpt-oss, so "off" asks for the
    # least it will take rather than for a value half the catalogue 400s on.
    effort = "low" if level == "off" else level
    return ReasoningStyle({"reasoning": {"effort": effort}}, ("reasoning",))


_TRANSLATORS = {
    "openrouter": _openrouter,
    "groq": _groq,
    "openai": _openai,
    # chat completions shaped
    "local": _local,
    "openai_compat": _openai_chat,
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
