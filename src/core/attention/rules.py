"""The attention decision, as pure functions: no IO, so it stays testable.

Two questions, kept apart: `is_addressed` ("is this for me?") is deterministic
and bypasses cooldown and quiet hours; `score` ("does this concern me?") is
probabilistic.
"""

from typing import Optional, Sequence, Tuple

from src.core.perception.types import Perception, PerceptionKind
from src.utils.text_match import contains_any_word_fuzzy

# a body interrupt is Bea's own emergency: it always deserves a reaction
CRITICAL_GAME_EVENTS = frozenset({"death", "interrupted", "hurt_by_player", "damage"})

# how close another player has to be, in blocks, before their in-game chat
# counts as being said *to* her rather than near her
NEARBY_BLOCKS = 6.0

# beyond this, "she hasn't spoken in a while" stops growing
LONG_SILENCE_SECONDS = 600.0

# recent activity saturates here: a busy room is busy, more does not mean more
ACTIVITY_SATURATION = 5.0


def in_quiet_hours(hour: int, start: int, end: int) -> bool:
    """True when `hour` falls in the quiet window (handles the midnight wrap)."""
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def is_addressed(
    p: Perception,
    *,
    trigger_words: Sequence[str] = (),
    self_ids: Sequence[str] = (),
) -> Optional[str]:
    """The reason this perception is aimed at Bea, or None."""
    meta = p.meta or {}
    author = p.author

    # a sense that already knows this one is for her says so explicitly
    declared = meta.get("addressed")
    if declared:
        return f"addressed:{declared}"

    # her own body shouting: an interrupt, a death, damage from a player
    if p.kind is PerceptionKind.ACTION:
        return "addressed:body"
    event = str(meta.get("event", "")).lower()
    if event in CRITICAL_GAME_EVENTS:
        return f"addressed:{event}"
    if event == "hurt" and str(meta.get("source", "")).lower() == "player":
        # being hit by a person is a social event, not just damage
        return "addressed:attacked"

    if author is not None:
        if author.is_owner:
            return "addressed:owner"
        if float(author.extra.get("amount", 0) or 0) > 0:
            return "addressed:donation"

    if meta.get("is_dm"):
        return "addressed:dm"
    if meta.get("whisper"):
        return "addressed:whisper"
    if meta.get("mentions_self"):
        return "addressed:mention"

    reply_to = str(meta.get("reply_to_author_id", "") or "")
    if meta.get("reply_to_self") or (reply_to and reply_to in set(self_ids)):
        return "addressed:reply"

    if trigger_words and contains_any_word_fuzzy(p.content, trigger_words):
        return "addressed:name"

    # a one-to-one voice call: everything said is said to her
    if p.kind is PerceptionKind.VOICE and meta.get("alone_with_speaker"):
        return "addressed:voice-1on1"

    # standing right next to her in game and talking counts as talking to her
    distance = meta.get("distance")
    if distance is not None and float(distance) <= NEARBY_BLOCKS:
        return "addressed:nearby"

    return None


def score(
    *,
    salience: float,
    text: str,
    author_known: bool = False,
    author_promoted: bool = False,
    donation: float = 0.0,
    hot_names: Sequence[str] = (),
    seconds_since_spoke: Optional[float] = None,
    recent_activity: int = 0,
    hour: int = 12,
    quiet: Tuple[int, int] = (3, 9),
    cooldown_seconds: float = 20.0,
) -> float:
    """Appetite to speak up, in [0,1]. Pure and deterministic.

    `salience` is an input, not an order. IDLE never reaches here: the bus's
    idle timer is already its own gate.
    """
    # hard gates: she just spoke, or it is the middle of the night
    if seconds_since_spoke is not None and seconds_since_spoke < cooldown_seconds:
        return 0.0
    if in_quiet_hours(hour, quiet[0], quiet[1]):
        return 0.0

    text = text or ""
    value = 0.0

    # how alive the room is
    value += min(recent_activity / ACTIVITY_SATURATION, 1.0) * 0.40
    # a name she cares about pulls hard
    if hot_names and contains_any_word_fuzzy(text, hot_names):
        value += 0.50
    # someone she actually knows is speaking — she notices her own people
    if author_promoted or donation > 0:
        value += 0.35
    elif author_known:
        value += 0.15
    # a question invites an answer
    if "?" in text:
        value += 0.10
    # quiet for a while: more likely to chime in
    if seconds_since_spoke is None or seconds_since_spoke > LONG_SILENCE_SECONDS:
        value += 0.15

    # salience modulates, it does not command: a game snapshot (0.15) is damped,
    # a scream (0.95) is amplified, and a normal message (0.5) passes through
    value *= 0.5 + _clamp(salience)

    return _clamp(value)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))
