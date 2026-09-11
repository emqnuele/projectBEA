"""The moods are named after the feelings now. Nobody's setup may notice.

Every mood id is a key somewhere on disk: the PNG the OBS source swaps to, the
behaviour a 3D model plays, the expression VTube Studio loads. An upgrade that
quietly empties those leaves someone streaming with a blank avatar, which is the
one outcome worth a migration.
"""

import json

from src.core.config import BrainConfig
from src.core.mind.moods import MOODS, RENAMED, default_avatar_map, rename_legacy


def test_the_ids_are_the_plain_names_of_the_feelings():
    assert set(MOODS) == {
        "neutral", "happy", "sad", "angry", "surprised", "disgusted", "bored",
    }


def test_every_old_id_points_at_one_that_exists():
    assert all(new in MOODS for new in RENAMED.values())
    assert not set(RENAMED) & set(MOODS)


def test_an_avatar_configured_under_the_old_ids_still_has_its_images():
    old = {"normal": {"idle": "n.png", "talking": "nt.png"},
           "ew": {"idle": "e.png", "talking": "et.png"}}
    assert rename_legacy(old) == {
        "neutral": {"idle": "n.png", "talking": "nt.png"},
        "disgusted": {"idle": "e.png", "talking": "et.png"},
    }


def test_a_setup_that_already_uses_the_new_id_keeps_it():
    """Both keys present means the new one was set deliberately."""
    assert rename_legacy({"love": "old.png", "happy": "new.png"}) == {"happy": "new.png"}


def test_an_old_key_with_nothing_in_it_does_not_blank_a_new_one():
    assert rename_legacy({"cry": "", "sad": "kept.png"}) == {"sad": "kept.png"}


def test_reading_a_config_from_before_the_rename_moves_every_mood_keyed_block(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(json.dumps({
        "avatar_map": {"shock": {"idle": "s.png", "talking": "st.png"}},
        "stage": {
            "mood_clips": {"love": "wave"},
            "vts_expressions": {"cry": "tears.exp3.json"},
            "vts_clips": {"ew": "hk-9"},
        },
    }))

    cfg = BrainConfig()

    assert cfg.avatar_map["surprised"] == {"idle": "s.png", "talking": "st.png"}
    assert cfg.stage["mood_clips"] == {"happy": "wave"}
    assert cfg.stage["vts_expressions"] == {"sad": "tears.exp3.json"}
    assert cfg.stage["vts_clips"] == {"disgusted": "hk-9"}


def test_a_fresh_install_gets_a_slot_for_every_mood_and_nothing_else():
    assert set(default_avatar_map()) == set(MOODS)
