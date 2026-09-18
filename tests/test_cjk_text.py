"""Japanese and Chinese are written without spaces, and everything assumed spaces.

Three separate failures with one cause. Speech never reached a seam, so she
said nothing at all until a whole Japanese line had been generated — the
latency work that the rest of `expression/` exists for simply did not apply.
Written messages were never split, so one line arrived as a wall. And the
attention gate could not see her own name in "ベアちゃん", which is the way
people actually say it.
"""

from src.core.expression.chunking import SpeechChunker, split_for_speech
from src.core.expression.humanizer import TextHumanizer
from src.utils.text_match import contains_any_word, contains_any_word_fuzzy
from src.utils.text_utils import sentences

EN = ("Oh please. I hit that shot and you know it. The game is bugged, look at "
      "the ping. Don't gaslight me, I am the best player here.")
IT = ("Ma per favore. Quel colpo l'ho preso e lo sai. Il gioco è buggato, guarda "
      "il ping. Non provare a farmi il gaslighting, sono la migliore qui.")
JA = ("あら、冗談でしょう。今のは当たってたわよ、あなたも分かってるはず。"
      "ゲームがバグってるの、このpingを見なさいよ。私を騙そうとしないで、"
      "ここで一番上手いのは私なんだから。")


def streamed(text: str, step: int = 12):
    """Feed the chunker in deltas, the way a token stream arrives."""
    chunker = SpeechChunker()
    during = []
    for i in range(0, len(text), step):
        during += chunker.push(text[i:i + step])
    return during, chunker.flush()


# --- speech starts before the line is finished ------------------------------


def test_she_starts_speaking_before_a_japanese_line_is_finished():
    """Measured at zero before this: the room heard nothing until the last word."""
    during, _ = streamed(JA)
    assert len(during) >= 2, during


def test_english_and_italian_are_unchanged():
    for text in (EN, IT):
        during, _ = streamed(text)
        assert len(during) == 3, (text[:20], during)


def test_a_japanese_full_stop_is_a_seam():
    assert sentences("あら、冗談でしょう。今のは当たってたわよ。") == \
        ["あら、冗談でしょう。", "今のは当たってたわよ。"]


def test_a_decimal_is_still_one_thought():
    """The space after an ascii full stop is what keeps "3.14" together."""
    assert sentences("pi is 3.14 and that is that.") == ["pi is 3.14 and that is that."]


def test_a_closing_bracket_stays_with_the_sentence_it_closes():
    assert sentences("「そうね。」だから何？") == ["「そうね。」", "だから何？"]


def test_a_breathless_japanese_line_is_still_cut():
    """No full stop and no spaces: it used to come back as one 400-character piece."""
    line = "そうそう" * 120
    pieces = split_for_speech(line)
    assert len(pieces) > 1
    assert "".join(pieces) == line


def test_nothing_is_lost_when_a_japanese_line_is_cut():
    during, rest = streamed(JA)
    assert "".join(during + rest).replace(" ", "") == JA.replace(" ", "")


def test_a_long_english_word_is_still_left_whole():
    """The old reason for not cutting is right in a script that has words."""
    chunker = SpeechChunker(max_chars=20)
    assert chunker.push("Supercalifragilisticexpialidocious") == []


# --- written messages -------------------------------------------------------


def test_a_long_japanese_message_is_split_into_several():
    long_ja = JA * 3
    assert len(TextHumanizer().split(long_ja)) > 1


def test_a_short_line_is_still_one_message():
    assert len(TextHumanizer().split("そうね。")) == 1


# --- she answers to her own name --------------------------------------------


def test_she_hears_her_name_with_a_japanese_honorific():
    """`ちゃん` is a word character, so `(?!\\w)` refused the commonest form."""
    for text in ("ベアちゃん、こんにちは", "ベアさん、今夜の配信は？",
                 "beaちゃん、こんにちは"):
        assert contains_any_word(text, ["bea", "ベア"]), text


def test_a_bare_name_still_works_in_every_script():
    assert contains_any_word("ベア、聞こえてる？", ["ベア"])
    assert contains_any_word("hey bea what's up", ["bea"])
    assert contains_any_word("ciao bea, ci sei?", ["bea"])


def test_a_word_that_merely_starts_with_her_name_is_still_not_her():
    for text in ("beautiful sunset", "beato lui", "that beats everything"):
        assert not contains_any_word(text, ["bea"]), text
        assert not contains_any_word_fuzzy(text, ["bea"]), text


# --- the caption box --------------------------------------------------------


def test_an_ellipsis_ends_a_japanese_thought():
    """No space follows it, so the ascii rule left the two halves as one."""
    assert sentences("待って…分かった") == ["待って…", "分かった"]


def test_an_ellipsis_mid_word_is_still_one_english_thought():
    assert sentences("wait…what") == ["wait…what"]


def test_one_latin_word_does_not_hand_a_japanese_caption_back_to_textwrap():
    """`textwrap` counts characters, so the line came out twice the box wide."""
    from src.utils.text_utils import display_width, wrap_to_width

    lines = wrap_to_width("このpingを見なさいよ、ここで一番上手いのは私なんだから。", 20)
    assert all(display_width(line) <= 20 for line in lines), lines
    assert len(lines) > 1


def test_a_latin_word_in_a_japanese_line_is_not_cut_in_half():
    from src.utils.text_utils import wrap_to_width

    lines = wrap_to_width("私の名前は Supercalifragilistic です", 20)
    assert any("Supercalifragilistic" in line for line in lines), lines


def test_english_wrapping_is_left_exactly_as_it_was():
    import textwrap

    from src.utils.text_utils import wrap_to_width

    text = "Oh please. I hit that shot and you know it, look at the ping."
    assert wrap_to_width(text, 20) == textwrap.wrap(text, width=20)


def test_a_page_of_japanese_is_not_given_spaces_it_never_had():
    from src.utils.text_utils import paginate_text_for_box

    pages, _ = paginate_text_for_box("待って。分かった。", line_width=40, max_lines=4,
                                     base_font_size=40, min_font_size=20, font_step=4)
    assert pages == ["待って。分かった。"]


def test_english_pages_still_read_as_sentences():
    from src.utils.text_utils import paginate_text_for_box

    pages, _ = paginate_text_for_box("One thing. Then another.", line_width=40,
                                     max_lines=4, base_font_size=40,
                                     min_font_size=20, font_step=4)
    assert pages == ["One thing. Then another."]
