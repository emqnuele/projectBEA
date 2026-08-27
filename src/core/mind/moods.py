"""The one list of moods.

It used to live in three places that could drift apart: a table in
`operating.md`, a free-text description in the `speak` tool, and the keys of
`avatar_map`. The table stays in the file — it is the explanation, and the file
is meant to be edited. This is the enforcement: the tool's enum, the default
avatar slots and the normaliser all read from here.
"""

from typing import Dict, Optional, Sequence, Tuple

MOODS: Tuple[str, ...] = ("normal", "shock", "love", "cry", "angry", "ew", "bored")

DEFAULT_MOOD = "normal"

# what each one is for, shown to her as a table and used nowhere else
WHEN: Dict[str, str] = {
    "normal": "Casual chatting, judging people, talking about yourself.",
    "shock": "When someone insults you, you hear gossip, or something unexpected happens.",
    "love": "ONLY for money, compliments to YOU, or wins that matter to you.",
    "cry": "Fake crying for sympathy or donations, or when you lose.",
    "angry": "When corrected, when losing, or when it is obviously lag.",
    "ew": "Cheap things, bad food, boring comments.",
    "bored": "When someone writes too much, or the topic is uninteresting.",
}

# a model asked for a mood will invent one. An avatar that silently fails to
# change is worse than landing on the nearest thing she actually has.
_NEAR_MISSES: Dict[str, str] = {
    "happy": "love", "excited": "love", "joy": "love", "affection": "love",
    "sad": "cry", "crying": "cry", "upset": "cry", "disappointed": "cry",
    "neutral": "normal", "calm": "normal", "default": "normal", "idle": "normal",
    "mad": "angry", "annoyed": "angry", "furious": "angry", "irritated": "angry",
    "disgust": "ew", "disgusted": "ew", "gross": "ew", "cringe": "ew",
    "surprise": "shock", "surprised": "shock", "shocked": "shock",
    "tired": "bored", "boring": "bored", "unimpressed": "bored",
}


def normalize_mood(raw: Optional[str]) -> str:
    """Whatever the model said, mapped onto a mood that exists."""
    mood = (raw or "").strip().lower()
    if mood in MOODS:
        return mood
    return _NEAR_MISSES.get(mood, DEFAULT_MOOD)


def mood_table() -> str:
    """The markdown table, generated so it can never drift from `MOODS`."""
    rows = "\n".join(f"| `{m}` | {WHEN.get(m, '')} |" for m in MOODS)
    return "| MOOD ID | WHEN TO USE |\n| --- | --- |\n" + rows


def default_avatar_map() -> Dict[str, Dict[str, str]]:
    """One idle/talking slot per mood, so a new mood cannot be avatar-less."""
    return {mood: {"idle": "", "talking": ""} for mood in MOODS}


def enum_schema() -> Sequence[str]:
    return list(MOODS)
