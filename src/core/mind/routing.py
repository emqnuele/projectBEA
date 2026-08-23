"""Where does a perception go: the stage, or a scoped conversation?

Pure, and deliberately an explicit if/else. The one rule that must never break:
**a perception goes to exactly one turn.** Two consumers over the same batch
would mean Bea answering the same message twice, from two contexts that do not
know about each other.

The stage is everything she does *live*, in front of an audience: her voice, a
Discord call, the game, the owner at the console. A scoped conversation is
asynchronous written text — a channel, a group, a thread — which does not need
the stage and should not hold it up.
"""

from typing import Optional

from src.core.perception.types import Perception, PerceptionKind

STAGE = "stage"

# written surfaces whose messages belong to a channel, not to the stage. Only a
# fallback: a PlatformSkill declares `conversation_key` in the perception itself,
# which is the path that actually matters.
TEXT_SURFACES = {"voice:discord", "chat:telegram", "chat:twitch", "chat:mc"}


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

    if p.kind is PerceptionKind.CHAT and p.surface in TEXT_SURFACES:
        channel = (p.meta or {}).get("channel_id")
        if channel:
            platform = p.author.platform if p.author else p.surface
            return f"{platform}:{channel}"
    return STAGE


def is_stage(p: Perception) -> bool:
    return conversation_key(p) == STAGE


def awaits_a_reply(p: Perception) -> bool:
    """Someone is blocked on an HTTP call waiting for her answer.

    Those must stay on the stage no matter what the surface says: the caller is
    waiting on the live loop's correlation, and a scoped turn cannot resolve it.
    """
    return bool((p.meta or {}).get("correlation_id"))


def route(batch) -> "tuple[list, dict]":
    """Splits a batch into (stage, {conversation_key: [perceptions]}).

    Every perception lands in exactly one bucket.
    """
    stage = []
    scoped: dict = {}
    for p in batch:
        key = STAGE if awaits_a_reply(p) else conversation_key(p)
        if key == STAGE:
            stage.append(p)
        else:
            scoped.setdefault(key, []).append(p)
    return stage, scoped


def channel_of(key: str) -> Optional[str]:
    """The channel id inside a conversation key, or None."""
    _, sep, channel = key.partition(":")
    return channel if sep and channel else None


def platform_of(key: str) -> str:
    return key.partition(":")[0]
