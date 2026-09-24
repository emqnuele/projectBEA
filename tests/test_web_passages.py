"""The paragraphs of a long page that are about the question, found without a model."""

from src.core.skills.web.passages import pick


def page(*paragraphs: str) -> str:
    return "\n\n".join(paragraphs)


FILLER = [f"Paragraph {i} talks about harbours, boats and the sea." for i in range(50)]


def test_the_paragraph_that_answers_is_found_and_the_rest_left_out():
    text = page(*FILLER, "Tickets cost 12 euros and the museum opens at nine.", *FILLER)
    got = pick(text, "how much do tickets cost?", 500)
    assert "12 euros" in got
    assert "harbours" not in got


def test_an_italian_question_finds_an_italian_answer_across_inflections():
    text = page(*FILLER, "Domani a Milano piove tutto il giorno, con 14 gradi.", *FILLER)
    got = pick(text, "quanti gradi ci sono domani a milano?", 500)
    assert "piove tutto il giorno" in got


def test_the_heading_a_match_sits_under_comes_with_it():
    text = page("# Guide", *FILLER, "## Opening hours", "Open from nine to five.", *FILLER)
    got = pick(text, "opening hours", 500)
    assert got.startswith("## Opening hours")
    assert "nine to five" in got


def test_matches_come_back_in_page_order_with_the_gaps_marked():
    text = page("Lions sleep all day.", *FILLER, "Lions hunt at night.")
    got = pick(text, "lions", 500)
    assert got.index("sleep") < got.index("hunt")
    assert "…" in got


def test_the_budget_is_respected_gap_markers_included():
    text = page(*[f"Lions number {i} roar loudly at dawn." if i % 3 == 0 else "Grass."
                  for i in range(300)])
    for limit in (120, 300, 1000):
        assert len(pick(text, "lions roar", limit)) <= limit


def test_a_single_match_longer_than_the_budget_is_cut_not_dropped():
    text = page(*FILLER, "Lions " + "roar " * 500)
    got = pick(text, "lions", 200)
    assert got.startswith("Lions roar")
    assert len(got) <= 200


def test_nothing_in_common_is_nothing_rather_than_a_guess():
    assert pick(page(*FILLER), "volcano eruption", 500) is None


def test_a_question_made_only_of_small_words_is_no_question():
    assert pick(page(*FILLER), "what is the", 500) is None
