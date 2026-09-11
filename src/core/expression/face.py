"""What a mood looks like on a face that has one.

The mood she picks for a line reaches her voice through `prosody.py` and her
face through here, both reading the same two numbers in `moods.py`. One choice,
two readers, so how she sounds and how she looks cannot disagree.

VRM 1.0 standardises five emotions — happy, angry, sad, relaxed, surprised —
plus five visemes and the blinks. Bea has seven moods. Five of them are named
after the preset they use; the other two, `disgusted` and `bored`, have no
preset of their own and are blends. Those blends are the only judgement call in
this file, and `tests/test_face.py` checks them against the valence/arousal
vectors in `moods.py` so they cannot drift apart from how she actually feels.
"""

from typing import Dict

from src.core.mind.moods import MOODS, normalize_mood

# the emotion presets VRM 1.0 declares, and nothing invented on top
VRM_EMOTIONS = ("happy", "angry", "sad", "relaxed", "surprised", "neutral")

# The mouth shapes, in the order a spectrum puts them: dark to bright. The
# order is the point — `pcm.envelope` places every frame on that axis as one
# number, and the page blends the two shapes it falls between. Reordering this
# tuple without reordering the page's own list draws the wrong vowels.
VRM_VISEMES = ("ou", "oh", "aa", "ee", "ih")

WEIGHTS: Dict[str, Dict[str, float]] = {
    "neutral": {"neutral": 1.0},
    "happy": {"happy": 1.0},
    "sad": {"sad": 1.0},
    "angry": {"angry": 1.0},
    "surprised": {"surprised": 0.9},
    # disgust has no preset: contempt reads as a little anger over unhappiness
    "disgusted": {"angry": 0.45, "sad": 0.35},
    # `relaxed` alone reads as serene, which is the opposite of bored. It needs
    # the unhappiness under it or she looks pleased to be ignoring you.
    "bored": {"relaxed": 0.25, "sad": 0.35},
}

# a mood with no face would silently do nothing on screen. Not an `assert`:
# those are stripped under `python -O`, and this is the check that stops a new
# mood from reaching a stream with no expression behind it.
if set(WEIGHTS) != set(MOODS):
    raise RuntimeError(
        f"every mood needs expression weights; the two disagree on "
        f"{sorted(set(WEIGHTS) ^ set(MOODS))}"
    )


def weights_for(mood: str) -> Dict[str, float]:
    """The expression weights for a mood, normalising whatever the model said.

    Always returns every emotion, zeros included: a face that is handed only the
    weights that changed keeps whatever it was wearing before.
    """
    wanted = WEIGHTS[normalize_mood(mood)]
    return {name: float(wanted.get(name, 0.0)) for name in VRM_EMOTIONS}
