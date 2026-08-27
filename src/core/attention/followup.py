"""Is this person answering her? A separate gate, and a deterministic one.

The score in `rules.py` answers "does this concern me", which is a judgement
call and rightly probabilistic. "Are you talking to me" is not a judgement
call, and rolling a die on it is exactly what makes a bot feel broken — you
reply to her and she ignores you.

So this one is deterministic, and it skips the cooldown and the quiet hours:
those exist so she is not pushy, and answering someone who just spoke to you
is not being pushy. The only brake is a cap on turns in a row, without which
two people stay locked in a ping-pong forever.
"""

from dataclasses import dataclass
from typing import Optional, Sequence

from src.utils.text_match import contains_any_word_fuzzy


@dataclass(frozen=True)
class Turn:
    """One line of a conversation, as the gate needs to see it."""

    role: str            # "user" | "bea"
    identity: str = ""   # who said it (users only)
    addressee: str = ""  # who she was answering (her lines only)
    content: str = ""


def interposed_allowance(recent_activity: int, base: int, active_bonus: int) -> int:
    """How many other messages may land between her line and the reply.

    In a fast group, other people always get in between. A fixed low ceiling
    would switch the follow-up off in exactly the rooms that are alive.
    """
    return base + min(max(recent_activity, 0), max(active_bonus, 0))


def is_followup(
    history: Sequence[Turn],
    *,
    identity: str,
    seconds_since_bea: Optional[float],
    recent_activity: int = 0,
    window_seconds: float = 180.0,
    max_turns: int = 3,
    max_interposed: int = 3,
    active_bonus: int = 5,
    trigger_words: Sequence[str] = (),
) -> bool:
    """True if the incoming message continues an exchange she opened.

    `history` is the conversation in reading order, WITHOUT the new message.
    """
    if not history or seconds_since_bea is None:
        return False
    if seconds_since_bea > window_seconds:
        return False

    last_bea = _last_bea(history)
    if last_bea is None:
        return False
    if history[last_bea].addressee != identity:
        return False

    interposed = len(history) - 1 - last_bea
    if interposed > interposed_allowance(recent_activity, max_interposed, active_bonus):
        return False

    return _chain_length(history, last_bea, identity, trigger_words) < max_turns


def _last_bea(history: Sequence[Turn]) -> Optional[int]:
    for i in range(len(history) - 1, -1, -1):
        if history[i].role == "bea":
            return i
    return None


def _chain_length(history: Sequence[Turn], last_bea: int, identity: str,
                  trigger_words: Sequence[str]) -> int:
    """How many turns in a row she has already given this person unasked.

    Being called by name resets it: the cap limits her insistence, not their
    wish to keep talking to her.
    """
    chain = 0
    for i in range(last_bea, -1, -1):
        turn = history[i]
        if turn.role == "bea":
            if turn.addressee != identity:
                break
            chain += 1
        elif turn.identity == identity and contains_any_word_fuzzy(turn.content, trigger_words):
            break
    return chain
