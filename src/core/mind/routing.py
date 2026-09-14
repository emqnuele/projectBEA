"""Which conversation a perception belongs to — a tag, not a fork.

One loop, one context: every perception lands in the same frame of the same
turn. The key only says *where it came from* (for the provenance tag, the
follow-up gate and the per-key cooldowns), never which mind answers it.

A PlatformSkill sets `conversation_key` on the perception it emits; what
follows is the fallback for senses that don't.
"""

from typing import Optional

from src.core.perception.types import Perception, PerceptionKind

STAGE = "stage"


def conversation_key(p: Perception) -> str:
    """The conversation a perception belongs to, or `STAGE`."""
    explicit = (p.meta or {}).get("conversation_key")
    if explicit:
        return str(explicit)

    # her voice, her body and the console are the stage by nature
    if p.kind in (PerceptionKind.VOICE, PerceptionKind.GAME,
                  PerceptionKind.ACTION, PerceptionKind.IDLE):
        return STAGE
    if p.surface == "chat:ui":
        return STAGE

    # written text with a channel is a conversation with a key
    if p.kind is PerceptionKind.CHAT:
        channel = (p.meta or {}).get("channel_id")
        if channel:
            platform = p.author.platform if p.author else p.surface
            return f"{platform}:{channel}"
    return STAGE


def is_stage(p: Perception) -> bool:
    return conversation_key(p) == STAGE


def channel_of(key: str) -> Optional[str]:
    """The channel id inside a conversation key, or None."""
    _, sep, channel = key.partition(":")
    return channel if sep and channel else None


def platform_of(key: str) -> str:
    return key.partition(":")[0]
