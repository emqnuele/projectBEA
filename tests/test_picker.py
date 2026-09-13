"""Matching a word she wrote to something she actually has.

She invents constantly, and every invention used to land on `neutral` — which
on screen is a face that never changes. The failures worth pinning here are the
two ways this goes wrong: a word that should have matched and did not, and a
word that matched something it has nothing to do with.
"""

import re

from src.core.expression.picker import Picker, clip_picker, mood_picker
from src.core.mind.moods import DEFAULT_MOOD
from src.core.stage import installed_clips


class Meanings:
    """An embedder with an opinion you wrote down.

    Real similarity is a model's judgement, and these tests are about what the
    picker does with that judgement — so the judgement is written down instead
    of downloaded. Each group is one axis: a text sits on every axis one of
    whose words it contains, and a text on no axis is close to nothing, which
    is exactly the case the threshold exists for.
    """

    def __init__(self, groups):
        self.groups = dict(groups)
        self.calls = []

    def embed(self, texts):
        texts = list(texts)
        self.calls.append(texts)
        return [self._one(text) for text in texts]

    def _one(self, text):
        words = set(re.findall(r"[a-z]+", text.lower()))
        return [1.0 if words & set(members) else 0.0
                for members in self.groups.values()]


MOOD_MEANINGS = Meanings({
    "neutral": ["neutral", "deadpan", "dry", "flat"],
    "happy": ["happy", "delighted", "chuffed", "elated"],
    "sad": ["sad", "wistful", "forlorn", "crestfallen"],
    "angry": ["angry", "furious", "livid", "incensed"],
    "surprised": ["surprised", "flabbergasted", "agog"],
    "disgusted": ["disgusted", "revolted", "queasy"],
    "bored": ["bored", "listless", "torpid"],
})


def moods(embedder=MOOD_MEANINGS) -> Picker:
    """A picker ready to answer, which is what `warm` is for.

    Nothing loads a model on the thread a line is being spoken on, so a picker
    is only able to match once somebody has warmed it — at startup, on a thread
    of its own. Doing it here is doing what the brain does.
    """
    picker = mood_picker(embedder)
    picker.warm()
    return picker


def clips(embedder=None) -> Picker:
    picker = clip_picker(CLIPS, embedder)
    picker.warm()
    return picker


# --- the fast path, which costs nothing --------------------------------------


def test_a_mood_she_named_correctly_never_reaches_the_model():
    # deliberately not warmed: the fast path has to work before anything loads,
    # because on a cold start it is all she has
    embedder = Meanings({})
    assert mood_picker(embedder).pick("angry") == "angry"
    assert embedder.calls == []


def test_a_near_miss_is_answered_from_the_table():
    embedder = Meanings({})
    assert mood_picker(embedder).pick("furious") == "angry"
    assert embedder.calls == []


def test_an_old_id_still_lands_where_it_used_to():
    """Somebody's config, written before the rename, must not blank her face."""
    assert moods().pick("ew") == "disgusted"
    assert moods().pick("cry") == "sad"


def test_nothing_at_all_is_the_default_mood():
    assert moods().pick("") == DEFAULT_MOOD


# --- and the one that does ----------------------------------------------------


def test_a_word_no_table_knows_is_matched_by_meaning():
    """The whole point: `wistful` used to be a neutral face."""
    assert moods().pick("wistful") == "sad"
    assert moods().pick("deadpan") == "neutral"
    assert moods().pick("flabbergasted") == "surprised"


def test_a_word_close_to_nothing_falls_back_rather_than_guessing():
    assert moods().pick("thursday") == DEFAULT_MOOD


def test_the_moods_are_embedded_by_what_they_cover_not_by_their_name():
    """`disgusted` alone is close to a handful of words; the row is close to
    most of the ways she would ever write it."""
    embedder = Meanings(dict(MOOD_MEANINGS.groups))
    moods(embedder)

    embedded = embedder.calls[0]
    assert len(embedded) == 7
    assert any("grossed out" in row for row in embedded)


def test_the_answer_is_remembered():
    embedder = Meanings(dict(MOOD_MEANINGS.groups))
    picker = moods(embedder)
    picker.pick("wistful")
    picker.pick("wistful")

    # one for the seven rows, one for the word itself, and nothing after that
    assert len(embedder.calls) == 2


def test_without_a_model_it_is_exactly_the_table_it_always_was():
    picker = moods(embedder=None)
    assert picker.pick("furious") == "angry"
    assert picker.pick("wistful") == DEFAULT_MOOD


def test_a_model_that_falls_over_costs_a_face_and_never_a_turn():
    class Broken:
        def embed(self, texts):
            raise RuntimeError("the model is not there")

    assert moods(Broken()).pick("wistful") == DEFAULT_MOOD


# --- behaviours, where the names are file names -------------------------------


CLIP_MEANINGS = Meanings({
    "wave": ["wave", "shrug", "dismissive"],
    "nod": ["nod", "agree", "yes"],
    "point": ["point", "accuse", "blame"],
})

CLIPS = ["003_dismissive_wave", "slow_nod", "point_at_you_02"]


def test_a_behaviour_she_named_exactly_is_the_one_that_plays():
    assert clip_picker(CLIPS, CLIP_MEANINGS).pick("slow_nod") == "slow_nod"


def test_the_capitals_a_file_was_saved_with_do_not_have_to_be_guessed():
    assert clip_picker(["Slow_Nod"], CLIP_MEANINGS).pick("slow_nod") == "Slow_Nod"


def test_a_file_name_is_matched_by_what_it_is_of():
    """`shrug` is what she means; `003_dismissive_wave` is what is on disk."""
    assert clips(CLIP_MEANINGS).pick("shrug") == "003_dismissive_wave"
    assert clips(CLIP_MEANINGS).pick("agree") == "slow_nod"


def test_the_numbering_people_leave_on_exports_is_not_vocabulary():
    embedder = Meanings(dict(CLIP_MEANINGS.groups))
    clips(embedder)

    assert embedder.calls[0] == ["dismissive wave", "slow nod", "point at you"]


def test_a_behaviour_she_does_not_have_plays_nothing():
    """Playing the wrong one is worse than playing none: it is what is seen."""
    assert clips(CLIP_MEANINGS).pick("backflip") == ""


def test_with_no_behaviours_installed_nothing_ever_plays():
    assert clip_picker([], CLIP_MEANINGS).pick("shrug") == ""


# --- what counts as installed -------------------------------------------------


class Config:
    def __init__(self, **stage):
        self.stage = {"avatar_backend": "model", "clips_dir": "data/clips", **stage}


def test_a_still_image_has_no_behaviours(tmp_path):
    (tmp_path / "wave.vrma").write_bytes(b"")
    config = Config(avatar_backend="png", clips_dir=str(tmp_path))
    assert installed_clips(config) == []


def test_the_model_backend_reads_the_folder(tmp_path):
    (tmp_path / "wave.vrma").write_bytes(b"")
    (tmp_path / "nod.vrma").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("not a behaviour")

    assert installed_clips(Config(clips_dir=str(tmp_path))) == ["nod", "wave"]


def test_a_folder_that_is_not_there_is_no_behaviours(tmp_path):
    assert installed_clips(Config(clips_dir=str(tmp_path / "nope"))) == []


def test_vtube_studio_reads_the_hotkeys_you_mapped():
    config = Config(avatar_backend="vtube_studio",
                    vts_clips={"wave": "hotkey-1", "nod": "hotkey-2"})
    assert installed_clips(config) == ["nod", "wave"]


# --- what it refuses to do on the thread she is speaking on ------------------


def test_a_cold_picker_falls_back_rather_than_loading_a_model():
    """`pick` is called from inside a line already going out to the room.

    Loading the model is most of a second on a machine that has it and a
    download on one that does not, and either would land in the middle of a
    sentence. So a picker nobody has warmed answers with the fallback.
    """
    embedder = Meanings(dict(MOOD_MEANINGS.groups))
    picker = mood_picker(embedder)

    assert picker.ready is False
    assert picker.pick("wistful") == DEFAULT_MOOD
    assert embedder.calls == [], "it went and loaded the model anyway"


def test_warming_twice_costs_nothing_the_second_time():
    embedder = Meanings(dict(MOOD_MEANINGS.groups))
    picker = mood_picker(embedder)
    picker.warm()
    picker.warm()

    assert len(embedder.calls) == 1
    assert picker.ready is True
