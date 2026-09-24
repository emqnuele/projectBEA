"""A long page cut down to what she can use, found without a model.

The start of the page always comes first: on 24 september she asked a page
"what does it say" and was handed four stray fragments from the middle of it,
and all she could find to say was that she had opened it.
"""

from pathlib import Path

from src.core.skills.web.passages import pick


def page(*paragraphs: str) -> str:
    return "\n\n".join(paragraphs)


INTRO = "This guide explains how the town museum works and what it holds."
FILLER = [f"Paragraph {i} talks about harbours, boats and the sea." for i in range(50)]


# --- the start always comes first ------------------------------------------------


def test_a_general_question_gets_the_start_of_the_page_not_fragments():
    architecture = (Path(__file__).resolve().parents[1] / "docs" / "architecture.md").read_text()
    got = pick(architecture, "cosa c'è scritto, descrizione del progetto", 6000)

    assert got.text.startswith("# Architecture")
    assert "How ProjectBEA is actually put together" in got.text
    # the budget is used, not a third of it
    assert len(got.text) > 5000
    assert got.matched == 0


def test_the_start_comes_first_and_the_answer_after_it():
    text = page(INTRO, *FILLER, "Tickets cost 12 euros and the museum opens at nine.", *FILLER)
    got = pick(text, "how much do tickets cost?", 700)
    assert got.text.startswith(INTRO)
    assert "12 euros" in got.text
    assert got.matched == 1
    assert got.text.index(INTRO) < got.text.index("12 euros")


def test_a_first_paragraph_longer_than_its_share_is_cut_not_dropped():
    got = pick(page("A " * 2000, *FILLER), "boats", 1000)
    assert got.text.startswith("A A A")
    assert "…" in got.text


def test_budget_the_matches_leave_carries_the_start_on():
    text = page(*[f"Paragraph {i} is plain." for i in range(100)])
    got = pick(text, "volcano eruption", 600)
    assert got.matched == 0
    # well past the start's own share (about six of these)
    assert "Paragraph 15 is plain." in got.text
    assert "…" not in got.text


# --- the answer, when there is a question ------------------------------------------


def test_an_italian_question_finds_an_italian_answer_across_inflections():
    text = page(INTRO, *FILLER, "Domani a Milano piove tutto il giorno, con 14 gradi.", *FILLER)
    got = pick(text, "quanti gradi ci sono domani a milano?", 600)
    assert "piove tutto il giorno" in got.text


def test_the_heading_a_match_sits_under_comes_with_it():
    text = page(INTRO, *FILLER, "## Opening hours", "Open from nine to five.", *FILLER)
    got = pick(text, "opening hours", 700)
    assert "## Opening hours\n\nOpen from nine to five." in got.text


def test_matches_come_back_in_page_order_with_the_gaps_marked():
    text = page(INTRO, *FILLER, "Lions sleep all day.", *FILLER, "Lions hunt at night.")
    got = pick(text, "lions", 700)
    assert got.text.index("sleep") < got.text.index("hunt")
    assert "\n\n…\n\n" in got.text


def test_the_budget_is_respected_gap_markers_included():
    text = page(INTRO, *[f"Lions number {i} roar loudly at dawn." if i % 3 == 0 else "Grass."
                         for i in range(300)])
    for limit in (120, 300, 1000, 5000):
        assert len(pick(text, "lions roar", limit).text) <= limit


def test_a_question_made_only_of_words_about_the_page_matches_nothing():
    got = pick(page(INTRO, *FILLER), "what does this page say, give me a summary", 500)
    assert got.matched == 0
    assert got.text.startswith(INTRO)


def test_an_empty_page_is_empty():
    assert pick("   ", "anything", 500).text == ""
