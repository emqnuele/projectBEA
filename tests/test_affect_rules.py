"""How she feels, as a table of cases — the point of keeping it pure.

Two properties would rot quietly if nobody pinned them: the state decays in
time rather than per utterance, and the render never tells her how to behave.
"""

import pytest

from src.core.affect.rules import (
    FELT,
    HALF_LIFE_SECONDS,
    Affect,
    decay,
    faded,
    is_strong,
    render,
    stir,
    warmth_phrase,
)
from src.core.mind.moods import MOODS, VECTORS, vector_for

T0 = 1_000_000.0

ANGRY = VECTORS["angry"]
LOVE = VECTORS["love"]
NORMAL = VECTORS["normal"]


# --- the mood table ---------------------------------------------------------


def test_every_mood_has_a_vector():
    assert set(VECTORS) == set(MOODS)


def test_normal_is_the_origin():
    assert vector_for("normal") == (0.0, 0.0)


def test_an_invented_mood_lands_on_a_real_vector():
    assert vector_for("furious") == VECTORS["angry"]
    assert vector_for("nonsense") == VECTORS["normal"]


def test_angry_and_sad_are_told_apart_by_arousal():
    # both negative; if they collapsed onto one axis prosody could not separate
    # a shout from a sulk
    assert VECTORS["angry"][0] < 0 and VECTORS["cry"][0] < 0
    assert VECTORS["angry"][1] > 0 > VECTORS["cry"][1]


# --- decay ------------------------------------------------------------------


def test_one_half_life_halves_it():
    assert faded(0.8, HALF_LIFE_SECONDS, HALF_LIFE_SECONDS) == pytest.approx(0.4)


def test_decay_never_crosses_zero():
    assert faded(-0.8, HALF_LIFE_SECONDS * 20, HALF_LIFE_SECONDS) == pytest.approx(0.0, abs=1e-5)
    assert faded(-0.8, HALF_LIFE_SECONDS * 20, HALF_LIFE_SECONDS) <= 0.0


def test_no_time_passing_changes_nothing():
    before = Affect(-0.5, 0.5, T0)
    assert decay(before, T0) == before


def test_a_long_gap_brings_her_back_to_baseline():
    # the restart case: she was furious, the process was down for six hours
    after = decay(Affect(-0.9, 0.9, T0), T0 + 6 * 3600)
    assert after.felt is False


# --- stir -------------------------------------------------------------------


def test_one_sharp_line_is_a_blip_not_a_mood():
    assert stir(Affect(), ANGRY, now=T0).felt is False


def test_two_in_a_row_are_a_mood():
    state = stir(Affect(), ANGRY, now=T0)
    state = stir(state, ANGRY, now=T0 + 10)
    assert state.felt is True
    assert state.valence < 0 and state.arousal > 0


def test_a_neutral_line_does_not_scrub_the_mood():
    """The additive-vs-slide property, and the reason it is additive."""
    angry = stir(stir(Affect(), ANGRY, now=T0), ANGRY, now=T0 + 1)
    after = stir(angry, NORMAL, now=T0 + 2)
    assert after.valence == pytest.approx(angry.valence, abs=0.01)
    assert after.felt is True


def test_time_is_what_clears_a_mood_not_talking():
    angry = stir(stir(Affect(), ANGRY, now=T0), ANGRY, now=T0 + 1)
    assert stir(angry, NORMAL, now=T0 + HALF_LIFE_SECONDS * 4).felt is False


def test_the_opposite_mood_pulls_her_back_faster():
    angry = stir(stir(Affect(), ANGRY, now=T0), ANGRY, now=T0 + 1)
    assert stir(angry, LOVE, now=T0 + 2).valence > angry.valence


def test_it_never_leaves_the_unit_range():
    state = Affect()
    for i in range(20):
        state = stir(state, ANGRY, now=T0 + i)
    assert -1.0 <= state.valence <= 1.0
    assert -1.0 <= state.arousal <= 1.0


def test_stirring_ages_what_was_already_there():
    old = Affect(-0.8, 0.0, T0)
    fresh = stir(old, NORMAL, now=T0 + HALF_LIFE_SECONDS)
    assert fresh.valence == pytest.approx(-0.4)


# --- is_strong --------------------------------------------------------------


@pytest.mark.parametrize("mood", ["angry", "love", "cry"])
def test_the_moods_that_mean_someone_got_to_her(mood):
    assert is_strong(VECTORS[mood]) is True


@pytest.mark.parametrize("mood", ["normal", "shock", "ew", "bored"])
def test_the_moods_that_are_not_about_a_person(mood):
    # shock is loud but a surprise is not somebody doing something to her
    assert is_strong(VECTORS[mood]) is False


# --- render -----------------------------------------------------------------


def test_a_calm_state_says_nothing_at_all():
    assert render(Affect()) == ""


def test_just_under_the_threshold_still_says_nothing():
    assert render(Affect(-FELT + 0.01, 0.0, T0)) == ""


def test_wound_up_and_flat_do_not_read_the_same():
    wound_up = render(Affect(-0.7, 0.7, T0))
    flat = render(Affect(-0.7, -0.7, T0))
    assert wound_up and flat and wound_up != flat


def test_good_and_bad_do_not_read_the_same():
    assert render(Affect(0.7, 0.7, T0)) != render(Affect(-0.7, 0.7, T0))


def test_it_is_labelled_so_she_can_tell_it_from_a_perception():
    assert render(Affect(-0.7, 0.7, T0)).startswith("[HOW YOU FEEL]")


# every quadrant, plus the two neutral-valence edges
QUADRANTS = [(-0.7, 0.7), (-0.7, -0.7), (-0.7, 0.0), (0.7, 0.7), (0.7, -0.7),
             (0.0, 0.7), (0.0, -0.7)]

# a render that starts telling her how to act has stopped describing a state,
# and has started overwriting whatever soul the owner wrote
INSTRUCTIONS = ("be ", "act ", "keep ", "don't", "do not", "should", "make sure",
                "try to", "remember to", "so you")


@pytest.mark.parametrize("valence,arousal", QUADRANTS)
def test_it_describes_a_state_and_never_gives_an_order(valence, arousal):
    text = render(Affect(valence, arousal, T0)).lower()
    assert text
    assert not any(phrase in text for phrase in INSTRUCTIONS)


@pytest.mark.parametrize("valence,arousal", QUADRANTS)
def test_every_quadrant_has_something_to_say(valence, arousal):
    assert render(Affect(valence, arousal, T0)) != ""


# --- warmth -----------------------------------------------------------------


def test_a_neutral_standing_is_not_worth_a_word():
    assert warmth_phrase(0.0) == ""
    assert warmth_phrase(0.2) == ""
    assert warmth_phrase(-0.2) == ""


def test_warmth_reads_as_words_not_as_a_number():
    for value in (-0.9, -0.4, 0.4, 0.9):
        phrase = warmth_phrase(value)
        assert phrase and not any(c.isdigit() for c in phrase)


def test_cold_and_fond_do_not_read_the_same():
    assert warmth_phrase(-0.9) != warmth_phrase(0.9)
