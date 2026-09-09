"""What a mood looks like on a face that has one.

The mood she picks for a line reaches her voice through `prosody.py` and her
face through here, both reading the same two numbers in `moods.py`. One choice,
two readers, so how she sounds and how she looks cannot disagree.

VRM 1.0 standardises five emotions — happy, angry, sad, relaxed, surprised —
plus five visemes and the blinks. Bea has seven moods. Two of them, `ew` and
`bored`, have no preset of their own and are blends. Those blends are the only
judgement call in this file, and `tests/test_face.py` checks them against the
valence/arousal vectors in `moods.py` so they cannot drift apart from how she
actually feels.
"""

from typing import Dict

from src.core.mind.moods import MOODS, normalize_mood

# the emotion presets VRM 1.0 declares, and nothing invented on top
VRM_EMOTIONS = ("happy", "angry", "sad", "relaxed", "surprised", "neutral")

# the mouth shapes; `aa` is the one the lip sync drives
VRM_VISEMES = ("aa", "ih", "ou", "ee", "oh")

WEIGHTS: Dict[str, Dict[str, float]] = {
    "normal": {"neutral": 1.0},
    "shock": {"surprised": 0.9},
    "love": {"happy": 1.0},
    "cry": {"sad": 1.0},
    "angry": {"angry": 1.0},
    # disgust has no preset: contempt reads as a little anger over unhappiness
    "ew": {"angry": 0.45, "sad": 0.35},
    # `relaxed` alone reads as serene, which is the opposite of bored. It needs
    # the unhappiness under it or she looks pleased to be ignoring you.
    "bored": {"relaxed": 0.25, "sad": 0.35},
}

# a mood with no face would silently do nothing on screen
assert set(WEIGHTS) == set(MOODS), "every mood needs expression weights"


def weights_for(mood: str) -> Dict[str, float]:
    """The expression weights for a mood, normalising whatever the model said.

    Always returns every emotion, zeros included: a face that is handed only the
    weights that changed keeps whatever it was wearing before.
    """
    wanted = WEIGHTS[normalize_mood(mood)]
    return {name: float(wanted.get(name, 0.0)) for name in VRM_EMOTIONS}
