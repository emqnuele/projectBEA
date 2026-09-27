"""What a model says about itself, read without loading a single mesh."""

import pytest

from src.modules.avatar.vrm_file import describe, expression_names, read_glb, thumbnail
from tests.glb import PNG, glb, vrm0, vrm1, vrma


def test_the_thumbnail_is_the_exact_slice_a_vrm_1_points_at(tmp_path):
    assert thumbnail(vrm1(tmp_path / "bea.vrm")) == ("image/png", PNG)


def test_a_vrm_0_thumbnail_is_found_through_its_texture(tmp_path):
    assert thumbnail(vrm0(tmp_path / "old.vrm")) == ("image/png", PNG)


def test_a_model_without_a_thumbnail_says_none_instead_of_failing(tmp_path):
    assert thumbnail(vrm1(tmp_path / "bea.vrm", thumbnail=None)) is None
    assert thumbnail(vrm0(tmp_path / "old.vrm", thumbnail=None)) is None


def test_something_that_is_not_a_glb_is_refused_by_name(tmp_path):
    fake = tmp_path / "bea.vrm"
    fake.write_bytes(b"PK\x03\x04 a zip wearing a .vrm")
    with pytest.raises(ValueError, match="bea.vrm"):
        read_glb(fake)


def test_a_vrm_0_is_described_under_the_names_the_renderer_uses(tmp_path):
    names = expression_names(read_glb(vrm0(tmp_path / "old.vrm"))[0])
    assert {"aa", "happy", "sad", "relaxed", "angry", "neutral"} <= set(names)
    # a custom group named Surprised is not the surprised preset three-vrm looks for
    assert "surprised" not in names


def test_a_vrm_0_licence_is_read_from_its_permission_url(tmp_path):
    info = describe(vrm0(tmp_path / "old.vrm"))
    assert info["vrm"] == "0.x"
    assert info["licence"]["credit_required"] is True
    assert info["licence"]["redistribution"] is True
    assert info["title"] == "Old Bea"


def test_a_model_that_cannot_move_its_mouth_is_warned_about(tmp_path):
    info = describe(vrm1(tmp_path / "bea.vrm", presets=("happy", "neutral")))
    assert any("'aa'" in w for w in info["warnings"])
    assert any("surprised" in w for w in info["warnings"])


def test_a_complete_model_has_nothing_to_warn_about(tmp_path):
    info = describe(vrm1(tmp_path / "bea.vrm"))
    assert info["vrm"] == "1.0"
    assert info["warnings"] == []
    assert info["has_thumbnail"] is True
    assert info["licence"]["credit_required"] is False


def test_a_plain_gltf_is_not_mistaken_for_a_vrm(tmp_path):
    plain = tmp_path / "cube.glb"
    plain.write_bytes(glb({"asset": {"version": "2.0"}}))
    assert describe(plain)["vrm"] is None


def test_a_clip_is_not_mistaken_for_a_model(tmp_path):
    assert describe(vrma(tmp_path / "wave.vrma"))["vrm"] is None
