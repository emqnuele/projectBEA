"""The one list of moods.

It used to live in three places that could drift apart: a table in
`operating.md`, a free-text description in the `speak` tool, and the keys of
`avatar_map`. The table stays in the file — it is the explanation, and the file
is meant to be edited. This is the enforcement: the tool's enum, the default
avatar slots, the normaliser and the words that reach each mood all read from
here.

The ids are the plain names of the feelings. She is shown this list every turn
and has to pick from it in the time it takes to answer, so an id that has to be
learned (`ew`, `cry`) is a worse id than one she would have guessed.
"""

from typing import Dict, Optional, Sequence, Tuple

MOODS: Tuple[str, ...] = (
    "neutral", "happy", "sad", "angry", "surprised", "disgusted", "bored",
)

DEFAULT_MOOD = "neutral"

# what each one is for, shown to her as a table and used nowhere else
WHEN: Dict[str, str] = {
    "neutral": "Casual chatting, judging people, talking about yourself.",
    "happy": "Money, compliments to YOU, wins that matter to you, being pleased with yourself.",
    "sad": "Fake crying for sympathy or donations, or when you lose.",
    "angry": "When corrected, when losing, or when it is obviously lag.",
    "surprised": "When someone insults you, you hear gossip, or something unexpected happens.",
    "disgusted": "Cheap things, bad food, comments that are beneath you.",
    "bored": "When someone writes too much, or the topic is uninteresting.",
}

# Where each mood sits on the two axes that matter: valence (how good it feels)
# and arousal (how activated it is). Two axes rather than one because angry and
# sad are both negative and sound nothing alike — separating them is the whole
# reason prosody can tell them apart.
VECTORS: Dict[str, Tuple[float, float]] = {
    "neutral": (0.0, 0.0),
    "happy": (0.90, 0.50),
    "sad": (-0.70, -0.25),
    "angry": (-0.80, 0.85),
    "surprised": (-0.15, 0.85),
    "disgusted": (-0.50, 0.15),
    "bored": (-0.30, -0.70),
}

# a mood without a vector would silently stop colouring her voice. Not an
# `assert`: those are stripped under `python -O`, and this is the check that
# stops a new mood from reaching a stream with no sound behind it.
if set(VECTORS) != set(MOODS):
    raise RuntimeError(
        f"every mood needs a valence/arousal vector; the two disagree on "
        f"{sorted(set(VECTORS) ^ set(MOODS))}"
    )


# What each mood covers, in words. Read only when a word reaches the matcher
# that the tables below did not catch, and embedded instead of the bare mood
# name: `disgusted` on its own is close to a handful of words, the whole row is
# close to most of the ways she would ever write it.
#
# One judgement call worth knowing about before editing: `smug` sits on `happy`
# because it is the only mood with a visible smile behind it, and a smug line
# delivered deadpan reads as flat. `mocking` sits on `neutral` because she is
# judging, which is what `neutral` is for — the amusement is in the words.
COVERS: Dict[str, str] = {
    "neutral": "neutral, normal, plain, casual, deadpan, dry, matter of fact, calm, "
               "unbothered, mocking, sarcastic, sly, teasing, judging",
    "happy": "happy, delighted, thrilled, pleased, proud, gleeful, cheerful, warm, "
             "adoring, affectionate, smitten, smug, cocky, pleased with yourself",
    "sad": "sad, crying, tearful, sobbing, miserable, wounded, heartbroken, "
           "sorry for yourself, defeated, sulking, dejected",
    "angry": "angry, furious, mad, irritated, annoyed, seething, indignant, "
             "outraged, snapping, offended, fed up",
    "surprised": "surprised, shocked, startled, astonished, amazed, stunned, "
                 "taken aback, wide eyed, incredulous, speechless",
    "disgusted": "disgusted, revolted, contempt, distaste, grossed out, sneering, "
                 "repulsed, appalled, disdain, cringing",
    "bored": "bored, uninterested, tired, listless, unimpressed, tuned out, "
             "glazed over, indifferent, weary, over it",
}

# a mood without words to match on would only ever be reachable by its exact
# id. Same shape as the vector check above: fail loud, so it cannot ship.
if set(COVERS) != set(MOODS):
    raise RuntimeError(
        f"every mood needs words that reach it; the two disagree on "
        f"{sorted(set(COVERS) ^ set(MOODS))}"
    )


# The ids these moods used to have. Kept because they are written into saved
# sessions, into `avatar_map`, and into every config file already in the wild:
# dropping them would silently blank somebody's avatar on upgrade.
RENAMED: Dict[str, str] = {
    "normal": "neutral",
    "love": "happy",
    "cry": "sad",
    "shock": "surprised",
    "ew": "disgusted",
}

# a model asked for a mood will invent one. An avatar that silently fails to
# change is worse than landing on the nearest thing she actually has.
_NEAR_MISSES: Dict[str, str] = {
    **RENAMED,
    "excited": "happy", "joy": "happy", "affection": "happy", "smug": "happy",
    "upset": "sad", "disappointed": "sad", "crying": "sad",
    "calm": "neutral", "default": "neutral", "idle": "neutral",
    "mad": "angry", "annoyed": "angry", "furious": "angry", "irritated": "angry",
    "disgust": "disgusted", "gross": "disgusted", "cringe": "disgusted",
    "surprise": "surprised", "shocked": "surprised",
    "boring": "bored", "unimpressed": "bored", "tired": "bored",
}


def normalize_mood(raw: Optional[str]) -> str:
    """Whatever the model said, mapped onto a mood that exists."""
    mood = (raw or "").strip().lower()
    if mood in MOODS:
        return mood
    return _NEAR_MISSES.get(mood, DEFAULT_MOOD)


def known_mood(raw: Optional[str]) -> Optional[str]:
    """The mood `raw` names, or None when nothing here recognises it.

    The same lookup as `normalize_mood` without the fallback, so a caller that
    can do better than the default — by matching on meaning — can tell the two
    apart. `normalize_mood` cannot: everything it does not know comes back as
    `neutral`, which is also a perfectly good answer.
    """
    mood = (raw or "").strip().lower()
    if mood in MOODS:
        return mood
    return _NEAR_MISSES.get(mood)


def vector_for(raw: Optional[str]) -> Tuple[float, float]:
    """The (valence, arousal) of a mood, normalising whatever the model said."""
    return VECTORS[normalize_mood(raw)]


def rename_legacy(mapping: Optional[Dict]) -> Dict:
    """A mood-keyed dict with any old ids moved onto the current ones.

    Only fills a slot that is not already set: somebody who has configured both
    the old key and the new one meant the new one.
    """
    if not isinstance(mapping, dict):
        return {}
    renamed = dict(mapping)
    for old, new in RENAMED.items():
        if old in renamed and not renamed.get(new):
            renamed[new] = renamed[old]
        renamed.pop(old, None)
    return renamed


def mood_table() -> str:
    """The markdown table, generated so it can never drift from `MOODS`."""
    rows = "\n".join(f"| `{m}` | {WHEN.get(m, '')} |" for m in MOODS)
    return "| MOOD ID | WHEN TO USE |\n| --- | --- |\n" + rows


def default_avatar_map() -> Dict[str, Dict[str, str]]:
    """One idle/talking slot per mood, so a new mood cannot be avatar-less."""
    return {mood: {"idle": "", "talking": ""} for mood in MOODS}


def enum_schema() -> Sequence[str]:
    return list(MOODS)
