"""Thin Telegram handlers: extract the minimum, deposit a perception, return.

No decision is made here — the attention gate decides whether Bea reacts, a
scoped turn decides what she says. `is_bot_called` is split out so it can be
tested against a table of cases instead of against Telegram.
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


# what a non-text message is, in the order telegram fills the fields
MEDIA_KINDS = ("sticker", "photo", "voice", "video_note", "video", "animation",
               "audio", "document")


def media_kind(message: Any) -> str:
    """Which kind of attachment this is, or "" for plain text."""
    for kind in MEDIA_KINDS:
        if getattr(message, kind, None):
            return kind
    return ""


def _label(message: Any, kind: str) -> str:
    if kind == "sticker":
        emoji = (getattr(getattr(message, "sticker", None), "emoji", "") or "").strip()
        return f"[sticker {emoji}]" if emoji else "[sticker]"
    if kind == "document":
        name = (getattr(getattr(message, "document", None), "file_name", "") or "").strip()
        return f"[file: {name}]" if name else "[file]"
    return {
        "photo": "[photo]", "voice": "[voice note]", "video": "[video]",
        "video_note": "[video message]", "animation": "[gif]", "audio": "[audio]",
    }[kind]


def describe_message(message: Any) -> str:
    """What arrived, as one line she can read.

    A photo she cannot see is still a photo someone sent her, and knowing that
    beats not hearing the message at all.
    """
    kind = media_kind(message)
    text = message_text(message)
    if not kind:
        return text
    label = _label(message, kind)
    return f"{label} {text}" if text else label


def is_private(message: Any) -> bool:
    chat = getattr(message, "chat", None)
    return getattr(chat, "type", "") == "private"


def display_name(user: Any) -> str:
    if user is None:
        return "someone"
    return (getattr(user, "full_name", None)
            or getattr(user, "username", None)
            or str(getattr(user, "id", "someone")))
