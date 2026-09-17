"""The menus the wizard is driven with.

Two promises: an arrow key does what it says on every platform, and every
widget still answers when there is no keyboard at all — CI, a pipe and the
docker setup container all reach the numbered prompt underneath.
"""

import io
import os
import sys
from types import SimpleNamespace

import pytest
from rich.console import Console

from src.setup import keys as keyboard
from src.setup import tui

OPTIONS = [
    ("alpha", "Alpha", "the first one"),
    ("beta", "Beta", "the second"),
    ("gamma", "Gamma", ""),
]


def console() -> Console:
    """A console that renders into a string and calls itself a terminal."""
    return Console(file=io.StringIO(), force_terminal=True, width=80, height=24)


def press(*names):
    return iter(names)


# --- reading the keyboard ----------------------------------------------------


def test_the_characters_that_have_a_name_get_one():
    assert keyboard._named("\r") == keyboard.ENTER
    assert keyboard._named("\n") == keyboard.ENTER
    assert keyboard._named(" ") == keyboard.SPACE
    assert keyboard._named("\t") == keyboard.TAB
    assert keyboard._named("q") == "q"


def test_ctrl_c_is_an_interrupt_and_not_a_character():
    """Raw mode swallows the signal on some terminals; the byte must still stop us."""
    with pytest.raises(KeyboardInterrupt):
        keyboard._named("\x03")
    with pytest.raises(EOFError):
        keyboard._named("\x04")


@pytest.mark.skipif(sys.platform == "win32", reason="the windows path is msvcrt")
@pytest.mark.parametrize("sequence, expected", [
    (b"\x1b[A", keyboard.UP),
    (b"\x1b[B", keyboard.DOWN),
    (b"\x1b[C", keyboard.RIGHT),
    (b"\x1b[D", keyboard.LEFT),
    (b"\x1bOA", keyboard.UP),
    (b"\x1b[H", keyboard.HOME),
    (b"\r", keyboard.ENTER),
    (b" ", keyboard.SPACE),
    (b"3", "3"),
])
def test_a_keypress_arrives_as_a_name(sequence, expected):
    """Through a real pty: the escape decoding is the part that breaks."""
    master, slave = os.openpty()
    reader = os.fdopen(slave, "r")
    try:
        os.write(master, sequence)
        assert keyboard.read_key(reader) == expected
    finally:
        reader.close()
        os.close(master)


@pytest.mark.skipif(sys.platform == "win32", reason="the windows path is msvcrt")
def test_escape_on_its_own_is_escape_and_does_not_hang():
    master, slave = os.openpty()
    reader = os.fdopen(slave, "r")
    try:
        os.write(master, b"\x1b")
        assert keyboard.read_key(reader) == keyboard.ESCAPE
    finally:
        reader.close()
        os.close(master)


def test_there_is_no_keyboard_when_the_environment_says_so(monkeypatch):
    monkeypatch.setenv("BEA_NO_TUI", "1")
    assert not keyboard.usable()


def test_there_is_no_keyboard_on_a_dumb_terminal(monkeypatch):
    monkeypatch.delenv("BEA_NO_TUI", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    assert not keyboard.usable()


# --- choosing one ------------------------------------------------------------


def test_the_arrows_move_the_selection():
    assert tui.select(console(), "Pick", OPTIONS, "alpha",
                      keys=press(keyboard.DOWN, keyboard.ENTER)) == "beta"


def test_the_selection_starts_on_the_default():
    assert tui.select(console(), "Pick", OPTIONS, "gamma",
                      keys=press(keyboard.ENTER)) == "gamma"


def test_moving_up_from_the_top_wraps_to_the_bottom():
    assert tui.select(console(), "Pick", OPTIONS, "alpha",
                      keys=press(keyboard.UP, keyboard.ENTER)) == "gamma"


def test_a_typed_number_still_picks_its_option():
    """The wizard asked for numbers for a year; fingers remember."""
    assert tui.select(console(), "Pick", OPTIONS, "alpha", keys=press("2")) == "beta"


def test_a_number_nothing_is_numbered_with_is_ignored():
    assert tui.select(console(), "Pick", OPTIONS, "alpha",
                      keys=press("9", keyboard.ENTER)) == "alpha"


def test_what_was_chosen_is_left_on_screen():
    screen = console()
    tui.select(screen, "Provider", OPTIONS, "alpha", keys=press(keyboard.ENTER))
    assert "Alpha" in screen.file.getvalue()


def test_an_empty_menu_is_a_programming_error():
    with pytest.raises(ValueError):
        tui.select(console(), "Pick", [], None, keys=press(keyboard.ENTER))


# --- choosing several --------------------------------------------------------


def test_space_ticks_the_row_the_cursor_is_on():
    picked = tui.multiselect(console(), "Surfaces", OPTIONS,
                             keys=press(keyboard.SPACE, keyboard.DOWN,
                                        keyboard.SPACE, keyboard.ENTER))
    assert picked == ["alpha", "beta"]


def test_space_twice_leaves_it_unticked():
    picked = tui.multiselect(console(), "Surfaces", OPTIONS,
                             keys=press(keyboard.SPACE, keyboard.SPACE, keyboard.ENTER))
    assert picked == []


def test_what_was_already_on_starts_ticked():
    picked = tui.multiselect(console(), "Surfaces", OPTIONS, selected=["gamma"],
                             keys=press(keyboard.ENTER))
    assert picked == ["gamma"]


def test_the_ticked_rows_come_back_in_the_order_they_are_offered():
    picked = tui.multiselect(console(), "Surfaces", OPTIONS,
                             keys=press(keyboard.END, keyboard.SPACE,
                                        keyboard.HOME, keyboard.SPACE, keyboard.ENTER))
    assert picked == ["alpha", "gamma"]


# --- yes and no --------------------------------------------------------------


def test_enter_takes_the_default():
    assert tui.confirm(console(), "Sure?", True, keys=press(keyboard.ENTER)) is True
    assert tui.confirm(console(), "Sure?", False, keys=press(keyboard.ENTER)) is False


def test_the_arrows_move_between_yes_and_no():
    assert tui.confirm(console(), "Sure?", True,
                       keys=press(keyboard.RIGHT, keyboard.ENTER)) is False


def test_typing_y_or_n_answers_immediately():
    assert tui.confirm(console(), "Sure?", False, keys=press("y")) is True
    assert tui.confirm(console(), "Sure?", True, keys=press("N")) is False


# --- the way that works without a keyboard -----------------------------------


def test_without_a_terminal_the_numbered_prompt_answers(monkeypatch):
    """A pipe, CI, the docker setup container. Nothing may need a tty to finish."""
    asked = {}

    def fake_ask(question, **kwargs):
        asked.update(kwargs)
        return "2"

    monkeypatch.setattr(tui.Prompt, "ask", staticmethod(fake_ask))
    quiet = Console(file=io.StringIO(), width=80)  # not a terminal

    assert tui.select(quiet, "Pick", OPTIONS, "alpha") == "beta"
    assert asked["default"] == "1", "the default option is still the default answer"


def test_without_a_terminal_every_option_is_printed(monkeypatch):
    monkeypatch.setattr(tui.Prompt, "ask", staticmethod(lambda *a, **k: "1"))
    quiet = Console(file=io.StringIO(), width=80)

    tui.select(quiet, "Pick", OPTIONS, "alpha")
    printed = quiet.file.getvalue()
    for _, label, _ in OPTIONS:
        assert label in printed


def test_without_a_terminal_a_multiselect_asks_one_question_each(monkeypatch):
    from rich import prompt as rich_prompt

    answers = iter([True, False, True])
    monkeypatch.setattr(rich_prompt.Confirm, "ask", staticmethod(lambda *a, **k: next(answers)))
    quiet = Console(file=io.StringIO(), width=80)

    assert tui.multiselect(quiet, "Surfaces", OPTIONS) == ["alpha", "gamma"]


def test_a_live_menu_is_refused_when_the_keyboard_cannot_be_read(monkeypatch):
    monkeypatch.setattr(keyboard, "usable", lambda *a, **k: False)
    assert not tui.interactive(console())


# --- a list longer than the window -------------------------------------------


def test_a_long_list_is_windowed_around_the_cursor():
    first, last = tui._window(index=8, count=20, room=5)
    assert last - first == 5
    assert first <= 8 < last


def test_a_short_list_is_shown_whole():
    assert tui._window(index=0, count=3, room=10) == (0, 3)


def test_the_window_never_runs_past_the_end():
    first, last = tui._window(index=19, count=20, room=5)
    assert (first, last) == (15, 20)


def test_a_console_that_cannot_print_the_pointer_gets_an_ascii_one():
    """A legacy windows console raises on `❯` rather than showing a box."""
    cp1252 = SimpleNamespace(file=SimpleNamespace(encoding="cp1252"))
    assert tui.glyphs(cp1252)["pointer"] == ">"
    assert not tui.supports_unicode(cp1252)


def test_a_console_that_can_print_it_gets_the_pointer():
    assert tui.glyphs(SimpleNamespace(file=SimpleNamespace(encoding="utf-8")))["pointer"] == "❯"
