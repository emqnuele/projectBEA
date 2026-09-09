"""A mood has to look like what it feels like.

`moods.py` already places every mood on two axes, and `prosody.py` already reads
them to colour her voice. The expression weights are the third reader of the
same numbers, and these tests are what stop them drifting apart — the same
reflex as the `assert set(VECTORS) == set(MOODS)` at the bottom of `moods.py`.
"""

import json
import struct
from pathlib import Path

import pytest

from src.core.expression.face import VRM_EMOTIONS, VRM_VISEMES, WEIGHTS, weights_for
from src.core.mind.moods import MOODS, VECTORS

# fetched by `make model`, gitignored: present on a developer's machine, absent in CI
SAMPLE = Path("data/models/VRM1_Constraint_Twist_Sample.vrm")


def positive(weights) -> float:
    return weights.get("happy", 0.0) + weights.get("relaxed", 0.0)


def negative(weights) -> float:
    return weights.get("sad", 0.0) + weights.get("angry", 0.0)


# --- the shape ---------------------------------------------------------------


def test_every_mood_has_a_face():
    assert set(WEIGHTS) == set(MOODS)


def test_nothing_is_invented_that_vrm_does_not_standardise():
    for mood, weights in WEIGHTS.items():
        for name in weights:
            assert name in VRM_EMOTIONS, f"{mood} asks for {name!r}, which is not a VRM preset"


def test_every_weight_is_a_weight():
    for mood, weights in WEIGHTS.items():
        for name, value in weights.items():
            assert 0.0 <= value <= 1.0, f"{mood}.{name} is {value}"


def test_a_face_is_handed_every_emotion_so_none_is_left_behind():
    """A face given only what changed keeps whatever it was wearing."""
    face = weights_for("angry")
    assert set(face) == set(VRM_EMOTIONS)
    assert face["angry"] == 1.0
    assert face["happy"] == 0.0


def test_whatever_the_model_invents_still_lands_on_a_real_face():
    assert weights_for("happy") == weights_for("love")
    assert weights_for("nonsense-the-model-made-up") == weights_for("normal")


# --- agreement with how she actually feels ----------------------------------


@pytest.mark.parametrize("mood", MOODS)
def test_a_mood_does_not_look_the_opposite_of_how_it_feels(mood):
    """Caught a real mistake: `bored` first read as `relaxed`, which is serene.

    `relaxed` in VRM means at ease. Bored has negative valence, so a face built
    mostly out of `relaxed` made her look pleased to be ignoring you.
    """
    valence, _arousal = VECTORS[mood]
    weights = WEIGHTS[mood]

    if valence > 0.2:
        assert positive(weights) > negative(weights), f"{mood} feels good but looks bad"
    if valence < -0.2:
        assert negative(weights) > positive(weights), f"{mood} feels bad but looks good"


def test_the_only_neutral_face_is_the_neutral_mood():
    for mood, weights in WEIGHTS.items():
        if mood == "normal":
            assert weights == {"neutral": 1.0}
        else:
            assert "neutral" not in weights, f"{mood} would sit under a neutral face"


def test_the_two_moods_vrm_has_no_preset_for_are_blends():
    """`ew` and `bored` are the only judgement calls in the table."""
    assert len(WEIGHTS["ew"]) > 1
    assert len(WEIGHTS["bored"]) > 1


# --- against a model that actually exists -----------------------------------


def gltf_json(path: Path) -> dict:
    raw = path.read_bytes()
    offset = 12
    while offset < len(raw):
        length, kind = struct.unpack_from("<II", raw, offset)
        offset += 8
        if kind == 0x4E4F534A:
            return json.loads(raw[offset:offset + length].decode("utf-8"))
        offset += length
    raise ValueError("no JSON chunk")


@pytest.mark.skipif(not SAMPLE.is_file(), reason="run `make model` to fetch the sample")
def test_the_sample_model_really_has_every_face_the_table_asks_for():
    preset = gltf_json(SAMPLE)["extensions"]["VRMC_vrm"]["expressions"]["preset"]

    for mood, weights in WEIGHTS.items():
        for name in weights:
            assert name in preset, f"{mood} wants {name!r}, the sample model has no such expression"
            assert preset[name].get("morphTargetBinds"), f"{name!r} drives no morph target"


@pytest.mark.skipif(not SAMPLE.is_file(), reason="run `make model` to fetch the sample")
def test_the_sample_model_has_a_mouth_the_lip_sync_can_move():
    preset = gltf_json(SAMPLE)["extensions"]["VRMC_vrm"]["expressions"]["preset"]
    assert "aa" in preset, "no 'aa' viseme: her mouth cannot move while she talks"
    assert set(VRM_VISEMES) <= set(preset)
