"""Direction written inside a line: where her face changes, and what she does.

The failure that matters here is not a missed tag. It is a tag that reaches the
engine and gets read out loud, which is why so much of this file is about text
that only looks like direction.
"""

from src.core.expression.tags import Beat, BeatKind, open_tag, parse, strip, visible_len

SAY = BeatKind.SAY
MOOD = BeatKind.MOOD
DO = BeatKind.DO


def test_direction_keeps_the_place_in_the_line_she_put_it_in():
    beats = parse("nice try. <mood:smug> genuinely, well done. <do:shrug>")
    assert beats == [
        Beat(SAY, "nice try."),
        Beat(MOOD, "smug"),
        Beat(SAY, "genuinely, well done."),
        Beat(DO, "shrug"),
    ]


def test_a_line_with_no_direction_is_one_thing_to_say():
    assert parse("just talking, nothing else") == [Beat(SAY, "just talking, nothing else")]


def test_a_name_is_free_text_because_it_is_matched_and_not_looked_up():
    assert parse("<mood:quietly pleased>ok") == [
        Beat(MOOD, "quietly pleased"), Beat(SAY, "ok"),
    ]


def test_the_case_she_wrote_it_in_does_not_matter():
    assert parse("<MOOD:Smug>hm") == [Beat(MOOD, "smug"), Beat(SAY, "hm")]


def test_a_misspelled_direction_is_never_spoken():
    """The one failure the audience notices."""
    assert strip("<moodd:smug> hi there") == "hi there"
    assert strip("<expression:happy>hello") == "hello"


def test_a_less_than_sign_survives_being_stripped():
    assert strip("5 < 6 and 7 > 6") == "5 < 6 and 7 > 6"
    assert strip("<3 you") == "<3 you"


def test_length_is_what_would_be_heard_not_what_was_written():
    assert visible_len("<mood:extremely pleased with herself>hi") == 2


def test_a_direction_that_has_not_closed_yet_is_not_a_place_to_cut():
    assert open_tag("nice try. <mood:sm")
    assert not open_tag("nice try. <mood:smug>")
    assert not open_tag("nice try.")


def test_a_lone_less_than_does_not_stall_the_line_forever():
    """Without a ceiling, one arithmetic comparison would never finish streaming."""
    assert not open_tag("the ping is 5 < " + "and it keeps going on like this " * 3)


def test_a_less_than_followed_by_a_number_is_arithmetic_not_direction():
    assert not open_tag("she scored < 5")
