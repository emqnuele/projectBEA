"""Handoff: carrying consciousness across windows, not compressing chat.

A summary answers "what was said". A handoff answers "who am i, where am i,
what was happening, what is still open". The hot ongoing is preserved verbatim
by the swap itself, so this covers the cold past only: two hours about food
become the fact they talked about food plus what mattered, and the rest goes.
"""

from typing import Any, Dict, List

# cap per field: a handoff is a bridge, not a second window
MAX_FACTS = 20
MAX_FIELD_CHARS = 500

HANDOFF_SYSTEM = (
    "You carry continuity for someone who cannot see the earlier part of her "
    "own context any more. Given the older turns below, write a handoff as "
    "flat JSON with exactly these keys: identity (one line, who she is), "
    "place (platform/channel she is in), people (names that mattered), facts "
    "(what happened, threads only), open_loops (unfinished business), doing "
    "(what she was in the middle of), last_outcome (how the last thing ended), "
    "mood_carry (one line), must_not_forget (promises, names, decisions). "
    "The recent past is preserved verbatim elsewhere: do NOT repeat it, cover "
    "the older part only. Facts and threads, no commentary, no preamble."
)

HANDOFF_KEYS = ("identity", "place", "people", "facts", "open_loops", "doing",
                "last_outcome", "mood_carry", "must_not_forget")


def empty_handoff() -> Dict[str, Any]:
    """Fallback when the worker fails: an empty bridge beats a lost turn."""
    return {key: ([] if key in ("people", "facts", "open_loops", "must_not_forget") else "")
            for key in HANDOFF_KEYS}


def _str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(v)[:MAX_FIELD_CHARS] for v in value if str(v).strip()][:MAX_FACTS]


def validate_handoff(data: Any) -> Dict[str, Any]:
    """Normalises a worker reply into the handoff shape. Never raises."""
    if not isinstance(data, dict):
        return empty_handoff()
    out: Dict[str, Any] = {}
    for key in ("identity", "place", "doing", "last_outcome", "mood_carry"):
        value = data.get(key)
        out[key] = str(value)[:MAX_FIELD_CHARS] if isinstance(value, str) else ""
    for key in ("people", "facts", "open_loops", "must_not_forget"):
        out[key] = _str_list(data.get(key))
    return out


def render_handoff(handoff: Dict[str, Any]) -> str:
    """The handoff as the system block opening the next window."""
    lines = ["[CONTINUITY FROM EARLIER]"]
    for key in HANDOFF_KEYS:
        value = handoff.get(key)
        if not value:
            continue
        if isinstance(value, list):
            lines.append(f"{key}: " + " | ".join(value))
        else:
            lines.append(f"{key}: {value}")
    if len(lines) == 1:
        lines.append("nothing carried: the earlier window was empty.")
    return "\n".join(lines)


def build_handoff_payload(cold_text: str, previous_handoff: str = "") -> str:
    """User payload for the worker: previous bridge plus what scrolled cold."""
    if previous_handoff.strip():
        return f"PREVIOUS HANDOFF:\n{previous_handoff}\n\nTURNS GONE COLD:\n{cold_text}"
    return cold_text
