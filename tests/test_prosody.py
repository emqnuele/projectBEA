"""What a mood does to her voice, and the one thing it must never do.

Neutral has to stay exactly neutral: if it did not, switching the feature off
would still change how she sounds.
"""

import pytest

from src.core.affect.rules import Affect
from src.core.expression.prosody import (
    NEUTRAL,
    PITCH_LIMITS,
    RATE_LIMITS,
    VOLUME_LIMITS,
    Prosody,
    as_hz,
    as_percent,
    combine_hz,
    combine_percent,
    for_mood,
)

T0 = 1_000_000.0
FURIOUS = Affect(-0.8, 0.8, T0)
DELIGHTED = Affect(0.8, 0.6, T0)
CALM = Affect(0.0, 0.0, T0)


# --- neutrality -------------------------------------------------------------


def test_no_mood_and_no_feeling_leaves_the_voice_alone():
    assert for_mood("neutral") == NEUTRAL
    assert for_mood("neutral").neutral is True


def test_a_calm_state_leaves_a_neutral_line_alone():
    assert for_mood("neutral", CALM) == NEUTRAL


def test_an_unknown_mood_falls_back_to_neutral():
    assert for_mood("gibberish") == NEUTRAL


# --- direction --------------------------------------------------------------


def test_angry_is_faster_higher_and_louder_than_flat():
    angry, bored = for_mood("angry"), for_mood("bored")
    assert angry.rate > bored.rate
    assert angry.pitch_hz > bored.pitch_hz
    assert angry.volume > bored.volume


def test_angry_and_sad_do_not_sound_the_same():
    # both are negative; only arousal separates a shout from a sulk
    angry, cry = for_mood("angry"), for_mood("sad")
    assert angry.rate > cry.rate
    assert angry.pitch_hz > cry.pitch_hz


def test_sad_is_slower_and_lower_than_neutral():
    cry = for_mood("sad")
    assert cry.rate < 1.0
    assert cry.pitch_hz < 0.0


def test_delight_lifts_the_pitch():
    assert for_mood("happy").pitch_hz > 0.0


# --- the standing state -----------------------------------------------------


def test_a_matching_state_makes_a_line_land_harder():
    assert for_mood("angry", FURIOUS).pitch_hz > for_mood("angry").pitch_hz


def test_a_contradicting_state_softens_it():
    assert for_mood("angry", DELIGHTED).pitch_hz < for_mood("angry").pitch_hz


def test_an_ordinary_line_said_while_furious_is_not_ordinary():
    assert for_mood("neutral", FURIOUS) != NEUTRAL


def test_a_state_below_the_threshold_changes_nothing():
    barely = Affect(-0.1, 0.1, T0)
    assert for_mood("angry", barely) == for_mood("angry")
    assert for_mood("neutral", barely) == NEUTRAL


# --- limits -----------------------------------------------------------------


@pytest.mark.parametrize("mood", ["neutral", "surprised", "happy", "sad", "angry", "disgusted", "bored"])
@pytest.mark.parametrize("affect", [None, FURIOUS, DELIGHTED, Affect(-1.0, -1.0, T0)])
def test_no_mood_can_push_the_voice_out_of_range(mood, affect):
    p = for_mood(mood, affect)
    assert RATE_LIMITS[0] <= p.rate <= RATE_LIMITS[1]
    assert PITCH_LIMITS[0] <= p.pitch_hz <= PITCH_LIMITS[1]
    assert VOLUME_LIMITS[0] <= p.volume <= VOLUME_LIMITS[1]


# --- translation ------------------------------------------------------------


@pytest.mark.parametrize("value,expected", [(1.0, "+0%"), (1.12, "+12%"), (0.9, "-10%")])
def test_a_multiplier_becomes_a_signed_percentage(value, expected):
    assert as_percent(value) == expected


@pytest.mark.parametrize("value,expected", [(0.0, "+0Hz"), (9.6, "+10Hz"), (-4.2, "-4Hz")])
def test_an_offset_becomes_signed_hz(value, expected):
    assert as_hz(value) == expected


def test_the_configured_voice_and_the_mood_compose():
    # +10% configured, 12% faster from the mood: she ends up 23% over nominal
    assert combine_percent("+10%", 1.12) == "+23%"
    assert combine_hz("+5Hz", 9.6) == "+15Hz"


def test_neutral_prosody_leaves_the_configured_voice_untouched():
    assert combine_percent("+10%", 1.0) == "+10%"
    assert combine_hz("+5Hz", 0.0) == "+5Hz"
    assert combine_percent("+33%", 1.0) == "+33%"


@pytest.mark.parametrize("base", ["", None, "loud", "%"])
def test_a_malformed_configured_value_is_no_change_rather_than_a_crash(base):
    assert combine_percent(base, 1.0) == "+0%"
    assert combine_hz(base, 0.0) == "+0Hz"


def test_prosody_is_hashable_so_it_can_be_cached_or_compared():
    assert Prosody(1.1, 2.0, 1.0) == Prosody(1.1, 2.0, 1.0)
