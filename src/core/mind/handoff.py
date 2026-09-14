"""Handoff: what scrolled cold, in her own words — plus the hot turns verbatim.

Two parts, different jobs. The cold past becomes a short prose recap ("you
talked about food for two hours, marco hates pineapple..."): what happened,
threads still open, nothing else. The hot ongoing is NOT rewritten at all —
it travels verbatim as speaker-labelled turns ("marco: ciao / you: ei"),
because rewriting the last half hour is how a persona loses the moment.

Who she is never belongs here: soul.md is in context on every turn already.
"""

# cap: a handoff is a bridge, not a second window (~5-8k tokens)
MAX_HANDOFF_CHARS = 24_000

HANDOFF_SYSTEM = (
    "You keep a running memory for someone who cannot see the earlier part of "
    "her own context any more. Given the older turns below, write a short "
    "prose recap, at most 150 words, in the second person ('you talked "
    "about...'), covering what happened and what is still open. Facts and "
    "threads only — no commentary, no preamble, no identity, no people list. "
    "The recent turns are preserved verbatim elsewhere: cover the older part "
    "only, do not repeat them."
)

HANDOFF_HEADER = "[EARLIER]"


def normalize_handoff(text: object) -> str:
    """A worker reply into clean prose. Empty when there is nothing to carry."""
    if not isinstance(text, str):
        return ""
    return text.strip()[:MAX_HANDOFF_CHARS]


def render_handoff(prose: str) -> str:
    """The handoff as the block opening the next window."""
    prose = normalize_handoff(prose)
    if not prose:
        return ""
    return f"{HANDOFF_HEADER}\n{prose}"


def build_handoff_payload(cold_text: str, previous_handoff: str = "") -> str:
    """User payload for the worker: previous recap plus what went cold."""
    if previous_handoff.strip():
        return f"PREVIOUS RECAP:\n{previous_handoff}\n\nOLDER TURNS:\n{cold_text}"
    return cold_text


def format_turns(messages: list) -> str:
    """Hot turns as speaker-labelled lines, verbatim, newest last.

    `messages` are plain {"role", "content"} dicts; user content already
    carries the speaker ("[marco] ciao"), bea lines are hers.
    """
    lines = []
    for m in messages:
        content = str(m.get("content") or "").strip()
        if not content:
            continue
        if m.get("role") == "assistant":
            lines.append(f"you: {content}")
        else:
            lines.append(content)
    return "\n".join(lines)
