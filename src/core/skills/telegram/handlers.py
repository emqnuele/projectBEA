"""Thin Telegram handlers: extract the minimum, deposit a perception, return.

Deliberately thin, riba-style. No decision is made here — the attention gate
decides whether Bea reacts, and a scoped conversation turn decides what she says.
An handler that reasons is an handler that duplicates the mind.

The pure part (`is_bot_called`) is separated out so it can be tested against a
table of cases instead of against Telegram.
"""

from typing import Any, Optional, Sequence

from src.utils.logger import get_logger
from src.utils.text_match import contains_any_word_fuzzy

logger = get_logger("bea.skills.telegram.handlers")


def is_bot_called(text: str, *, bot_username: str = "", bot_id: Optional[int] = None,
                  reply_to_user_id: Optional[int] = None,
                  trigger_words: Sequence[str] = ()) -> bool:
    """True if this message is aimed at Bea: her name, an @mention, or a reply.

    The name match tolerates one typo, so "beatrcie" still reaches her, but only
    on whole words — "beautiful" and "beach" must not.
    """
    low = (text or "").lower()
    if trigger_words and contains_any_word_fuzzy(low, trigger_words):
        return True
    if bot_username and f"@{bot_username.lower()}" in low:
        return True
    if bot_id is not None and reply_to_user_id == bot_id:
        return True
    return False


def message_text(message: Any) -> str:
    """The text of a message, whatever kind it is (captions included)."""
    return (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()


def is_private(message: Any) -> bool:
    chat = getattr(message, "chat", None)
    return getattr(chat, "type", "") == "private"


def display_name(user: Any) -> str:
    if user is None:
        return "someone"
    return (getattr(user, "full_name", None)
            or getattr(user, "username", None)
            or str(getattr(user, "id", "someone")))
