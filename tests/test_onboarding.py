"""The first five minutes: six questions and a persona.

The CLI wizard covers the plumbing — provider, key, voice, which platforms.
What it never asks is who she is, so the shipped persona is what almost
everyone ends up running forever.

The model helps, but it does not get to decide the shape: it answers in JSON
and the markdown is assembled here. A model writing free-form markdown produces
a different structure every time, which is how the operating manual became
unmaintainable in the first place.
"""

import pytest

from src.core.onboarding import (
    QUESTIONS,
    build_soul,
    needed,
    parse_draft,
)

ANSWERS = {
    "name": "Luna",
    "what": "a streamer",
    "adjectives": "sarcastica, curiosa, competitiva",
    "loves": "i gatti e vincere",
    "hates": "chi spiega le cose ovvie",
    "voice": "short and sharp",
    "owner": "Ema, il suo streamer",
    "language": "italiano",
}


# --- the questions -----------------------------------------------------------


def test_there_are_few_enough_questions_that_someone_finishes_them():
    assert 4 <= len(QUESTIONS) <= 8


def test_the_first_one_is_her_name():
    assert QUESTIONS[0].key == "name"


def test_every_question_can_be_rendered_without_asking_the_backend_twice():
    for q in QUESTIONS:
        assert q.label
        assert q.placeholder or q.options
        assert q.type in {"text", "textarea", "select"}


def test_only_the_name_is_required():
    assert [q.key for q in QUESTIONS if q.required] == ["name"]


def test_the_name_defaults_to_the_one_we_ship():
    assert QUESTIONS[0].default == "Bea"


# --- the template, which is also the fallback --------------------------------


def test_a_soul_is_built_from_the_answers_alone():
    soul = build_soul(ANSWERS)
    assert "a streamer" in soul
    assert "sarcastica" in soul
    assert "i gatti e vincere" in soul


def test_it_has_the_shape_every_other_soul_has():
    soul = build_soul(ANSWERS)
    for heading in ("## Identity", "## Voice", "## Constants"):
        assert heading in soul


def test_the_name_is_a_placeholder_so_renaming_still_works():
    """Baking the name in is how the shipped soul stopped following a rename."""
    assert "{name}" in build_soul(ANSWERS)


def test_it_survives_answers_that_are_mostly_missing():
    soul = build_soul({"name": "Kai"})
    assert "## Identity" in soul
    assert "Kai" in soul or "{name}" in soul


def test_it_survives_no_answers_at_all():
    assert "## Identity" in build_soul({})


def test_what_she_cannot_stand_makes_it_in():
    assert "chi spiega le cose ovvie" in build_soul(ANSWERS)


# --- what the model is allowed to give back ----------------------------------


def test_a_good_draft_becomes_the_usual_shape():
    soul = parse_draft({
        "identity": ["Main character energy.", "Allergic to being corrected."],
        "voice": ["Short and sharp."],
        "constants": ["Never break character."],
    }, ANSWERS)
    assert "Main character energy." in soul
    assert "## Voice" in soul
    assert "{name}" in soul


def test_a_draft_missing_a_section_still_produces_a_soul():
    soul = parse_draft({"identity": ["Something."]}, ANSWERS)
    assert "## Voice" in soul


def test_a_draft_that_is_not_a_dict_falls_back_to_the_template():
    assert "sarcastica" in parse_draft("nonsense", ANSWERS)


def test_an_empty_draft_falls_back_to_the_template():
    assert "sarcastica" in parse_draft({}, ANSWERS)


def test_a_draft_that_is_all_empty_strings_falls_back():
    assert "sarcastica" in parse_draft({"identity": ["", "  "]}, ANSWERS)


def test_a_model_that_writes_a_paragraph_instead_of_a_list_is_accepted():
    soul = parse_draft({"identity": "One long line about her.", "voice": ["Sharp."]}, ANSWERS)
    assert "One long line about her." in soul


def test_a_runaway_draft_is_cut_to_something_readable():
    soul = parse_draft({"identity": ["x" * 5000] * 20, "voice": ["y"]}, ANSWERS)
    assert len(soul) < 20_000


def test_markdown_the_model_snuck_in_does_not_break_the_headings():
    soul = parse_draft({"identity": ["## Identity\nsomething"], "voice": ["ok"]}, ANSWERS)
    assert soul.count("## Identity") == 1


# --- asking the model --------------------------------------------------------


async def test_the_model_is_asked_and_its_answer_is_used():
    from tests.fakes import FakeLLMClient

    from src.core.onboarding import draft_soul

    llm = FakeLLMClient(json_script=[{"identity": ["Sharp and rude."], "voice": ["Short."]}])
    soul = await draft_soul(llm, ANSWERS)
    assert "Sharp and rude." in soul


async def test_the_answers_reach_the_model():
    from tests.fakes import FakeLLMClient

    from src.core.onboarding import draft_soul

    llm = FakeLLMClient(json_script=[{"identity": ["x"]}])
    await draft_soul(llm, ANSWERS)
    assert "sarcastica" in llm.json_calls[0]


async def test_a_model_that_fails_still_gives_you_a_persona():
    """Onboarding must never dead-end: the answers alone are enough."""
    from tests.fakes import FakeLLMClient

    from src.core.onboarding import draft_soul

    class Broken(FakeLLMClient):
        async def complete_json(self, *a, **k):
            raise RuntimeError("the model is having a day")

    soul = await draft_soul(Broken(), ANSWERS)
    assert "sarcastica" in soul


# --- is it needed? -----------------------------------------------------------


def test_it_is_needed_when_the_soul_is_still_the_one_we_ship():
    assert needed(customised=False, completed=False) is True


def test_it_is_not_needed_once_the_soul_has_been_written():
    assert needed(customised=True, completed=False) is False


def test_it_is_not_needed_once_it_has_been_skipped():
    assert needed(customised=False, completed=True) is False


@pytest.mark.parametrize("customised,completed", [(True, True), (False, True), (True, False)])
def test_it_is_only_needed_in_the_one_case(customised, completed):
    assert needed(customised=customised, completed=completed) is False
