"""Whole-word and fuzzy trigger matching."""

import pytest

from src.utils.text_match import (
    contains_any_word,
    contains_any_word_fuzzy,
    first_matching_word,
)

TRIGGERS = ["bea", "beatrice"]


@pytest.mark.parametrize("text", ["bea", "ciao bea", "BEA!", "hey, bea?", "(bea)"])
def test_a_whole_word_matches(text):
    assert contains_any_word(text, TRIGGERS) is True


@pytest.mark.parametrize("text", ["beautiful", "beach day", "beam", "abea", "beas"])
def test_a_substring_does_not_match(text):
    assert contains_any_word(text, TRIGGERS) is False


def test_empty_inputs_never_match():
    assert contains_any_word("", TRIGGERS) is False
    assert contains_any_word("bea", []) is False
    assert contains_any_word("bea", ["", None]) is False


def test_underscores_count_as_word_characters():
    assert contains_any_word("bea_bot", TRIGGERS) is False


def test_first_matching_word_reports_which_one():
    assert first_matching_word("ciao beatrice", TRIGGERS) == "beatrice"
    assert first_matching_word("nothing here", TRIGGERS) == ""


@pytest.mark.parametrize("text", ["beatrcie", "beatrise", "beatricee", "beatriceee"])
def test_fuzzy_tolerates_one_typo(text):
    assert contains_any_word_fuzzy(text, TRIGGERS) is True


def test_fuzzy_still_matches_the_exact_word():
    assert contains_any_word_fuzzy("ciao bea", TRIGGERS) is True


@pytest.mark.parametrize("text", ["beat that", "a bear", "the best", "beach"])
def test_fuzzy_does_not_fire_on_real_words(text):
    assert contains_any_word_fuzzy(text, TRIGGERS) is False


def test_short_targets_are_exact_only():
    # "bea" is 3 chars: one edit away is a different word entirely
    assert contains_any_word_fuzzy("bee", ["bea"]) is False
    assert contains_any_word_fuzzy("bea", ["bea"]) is True


def test_fuzzy_with_no_targets_is_false():
    assert contains_any_word_fuzzy("anything", []) is False


def test_transposition_counts_as_one_edit():
    assert contains_any_word_fuzzy("marco", ["marco"]) is True
    assert contains_any_word_fuzzy("mraco", ["marco"]) is True
