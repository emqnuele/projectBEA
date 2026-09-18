"""The one language resolver: what it accepts, and what it refuses to guess."""

from src.core.language import (
    AUTO,
    LANGUAGES,
    directive,
    endonym,
    named,
    options,
    resolve,
    speaks_first,
    whisper_code,
    write_in,
)

# --- resolving --------------------------------------------------------------


def test_a_bare_code_is_itself():
    assert resolve("it") == "it"
    assert resolve("en") == "en"
    assert resolve("ja") == "ja"


def test_the_dashboards_own_japanese_is_translated():
    """The picker has shipped `jp` for months; whisper refuses it outright."""
    assert resolve("jp") == "ja"


def test_a_regional_tag_keeps_its_language():
    """Voice ids and browser locales both arrive carrying a region."""
    assert resolve("it-IT") == "it"
    assert resolve("en-US") == "en"
    assert resolve("pt-BR") == "pt"
    assert resolve("ja_JP") == "ja"


def test_an_endonym_from_the_setup_menu_resolves():
    """The wizard's voice menu is keyed by what a language calls itself."""
    assert resolve("Italiano") == "it"
    assert resolve("日本語") == "ja"
    assert resolve("English (US)") == "en"
    assert resolve("English (UK)") == "en"


def test_case_and_padding_do_not_matter():
    assert resolve("  IT  ") == "it"
    assert resolve("ITALIANO") == "it"


def test_nothing_at_all_means_detect():
    assert resolve("") == AUTO
    assert resolve(None) == AUTO
    assert resolve("   ") == AUTO
    assert resolve("auto") == AUTO


def test_a_language_we_do_not_know_degrades_to_detection():
    """A typo in config.json costs detection, never her voice."""
    assert resolve("klingon") == AUTO
    assert resolve("xx-YY") == AUTO


def test_every_declared_language_resolves_to_itself():
    for code in LANGUAGES:
        assert resolve(code) == code


# --- names ------------------------------------------------------------------


def test_named_gives_the_language_and_auto_gives_nothing():
    assert named("it").endonym == "Italiano"
    assert named("jp").english_name == "Japanese"
    assert named("auto") is None
    assert named("klingon") is None


def test_endonym_of_auto_is_empty_rather_than_a_guess():
    assert endonym("auto") == ""
    assert endonym("ja") == "日本語"


def test_options_lead_with_detection():
    first, *rest = options()
    assert first[0] == AUTO
    assert [code for code, _ in rest] == list(LANGUAGES)


# --- the transcriber --------------------------------------------------------


def test_whisper_gets_a_code_it_knows():
    assert whisper_code("jp") == "ja"
    assert whisper_code("it-IT") == "it"


def test_whisper_gets_none_rather_than_the_word_auto():
    """Every transcriber reads a missing language as detect, and rejects `auto`."""
    assert whisper_code("auto") is None
    assert whisper_code("") is None
    assert whisper_code("klingon") is None


# --- the prompt -------------------------------------------------------------


def test_the_directive_always_says_to_mirror():
    for code in ("auto", "en", "it", "ja"):
        assert "language you were addressed in" in directive(code)


def test_the_directive_is_the_same_whatever_language_is_configured():
    """The only rule an always-present prompt can carry is the always-true one."""
    assert directive("it") == directive("ja") == directive("auto")
    # naming a fallback here too leaves the model deciding which sentence it is
    # in; which language she opens in is told per turn instead
    assert "Italiano" not in directive("it")


def test_the_opening_line_names_the_configured_language():
    assert "日本語" in speaks_first("jp")
    assert "Italiano" in speaks_first("it-IT")
    assert "Nobody has written to you" in speaks_first("en")


def test_detection_gives_no_opening_line_to_fall_back_on():
    assert speaks_first("auto") == ""
    assert speaks_first("klingon") == ""


def test_background_passes_are_told_which_language_to_write_in():
    assert "Japanese" in write_in("jp")
    assert "language the conversation is in" in write_in("auto")
