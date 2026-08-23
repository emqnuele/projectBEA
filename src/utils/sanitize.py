"""Strips a model's raw output down to the message it actually meant to send.

Cheap models do not always return only the answer: they emit reasoning chains
(`<think>…</think>`), gpt-oss's channel format
(`<|channel|>analysis<|message|>…`) and special tokens (`<|endoftext|>`,
`<|im_end|>`). Unfiltered, that reaches the TTS and Bea *pronounces* it — a bug
already seen in production on riba, on the same model pool.

Everything here is pure: raw string in, clean string out (possibly empty, if the
whole thing was scaffolding — in which case the caller should treat it as a
failed generation rather than say it out loud).

Ported from riba/core/sanitize.py.
"""

import re

# reasoning wrapped in tags: removed entirely
_THINK_TAGS = ("think", "thinking", "thought", "reason", "reasoning", "analysis", "scratchpad")
_THINK_BLOCK_RE = re.compile(
    r"<\s*(" + "|".join(_THINK_TAGS) + r")\s*>.*?<\s*/\s*\1\s*>",
    re.DOTALL | re.IGNORECASE,
)

# a reasoning block opened and never closed (truncated output): drop everything
# from the opening onwards
_THINK_OPEN_RE = re.compile(
    r"<\s*(?:" + "|".join(_THINK_TAGS) + r")\s*>.*\Z",
    re.DOTALL | re.IGNORECASE,
)

# gpt-oss "harmony" format: keep ONLY the final channel
_FINAL_CHANNEL_RE = re.compile(
    r"<\|channel\|>\s*final\s*<\|message\|>(.*?)(?:<\|(?:end|return|endoftext|channel|start)\|>|\Z)",
    re.DOTALL | re.IGNORECASE,
)

# any special token between <| … |>
_SPECIAL_TOKEN_RE = re.compile(r"<\|[^|>]*\|>")

# leftover role markers at the start, from ChatML-ish formats
_ROLE_PREFIX_RE = re.compile(
    r"^\s*(?:assistant|assistente|system|user|final|response)\s*(?:[:>]|\n)\s*",
    re.IGNORECASE,
)


def clean_model_output(text: str) -> str:
    """Extracts the real message from a raw model output.

    Returns "" when nothing sensible survives — the caller must not speak that.
    """
    if not text:
        return ""

    out = text

    final = _FINAL_CHANNEL_RE.search(out)
    if final:
        out = final.group(1)

    out = _THINK_BLOCK_RE.sub("", out)
    out = _THINK_OPEN_RE.sub("", out)
    out = _SPECIAL_TOKEN_RE.sub("", out)
    out = _ROLE_PREFIX_RE.sub("", out.strip())

    # collapse the blank-line runs the removals left behind
    out = re.sub(r"\n{3,}", "\n\n", out)

    return out.strip()
