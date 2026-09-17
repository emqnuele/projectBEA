"""The wordmark. It is only a picture, but it is the first thing anyone sees,
and it must not be the thing that crashes the installer on a narrow window or
a console that speaks cp1252."""

import io
import re
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from src.setup import banner


class Utf8(io.StringIO):
    """A StringIO that answers the encoding question, as a real stdout does."""

    encoding = "utf-8"


def screen(width: int = 100, **kwargs) -> Console:
    return Console(file=Utf8(), force_terminal=True, width=width, **kwargs)


def text_of(console: Console) -> str:
    """What was printed, without the colour. Every letter carries its own
    gradient step, so the raw buffer has an escape between each of them."""
    return re.sub(r"\x1b\[[0-9;]*m", "", console.file.getvalue())


def test_every_letter_of_the_wordmark_has_a_glyph():
    """A missing one draws a blank column, silently."""
    for letter in banner.WORDMARK:
        assert letter in banner.FONT, letter


def test_the_art_is_as_tall_as_it_says_it_is():
    assert len(banner.rows()) == banner.HEIGHT
    assert len(banner.art(screen())) == banner.HEIGHT


def test_the_declared_width_is_the_width_it_draws():
    """The fallback decision is made from this number; a wrong one wraps."""
    assert max(len(row) for row in banner.rows()) <= banner.width()


def test_the_gradient_runs_from_one_end_to_the_other():
    ramp = banner._ramp(5)
    assert ramp[0] == banner.GRADIENT[0]
    assert ramp[-1] == banner.GRADIENT[1]
    assert len(ramp) == 5


def test_a_single_step_gradient_is_the_first_colour():
    assert banner._ramp(1) == [banner.GRADIENT[0]]


def test_a_wide_console_gets_the_art():
    console = screen(100)
    banner.show(console, animate=False)
    assert "█" in text_of(console)


def test_a_narrow_console_gets_the_name_on_one_line():
    """The art would wrap, and a wrapped wordmark reads as a broken install."""
    console = screen(40)
    banner.show(console, animate=False)
    printed = text_of(console)
    assert "█" not in printed
    assert "projectBEA" in printed


def test_the_tagline_is_printed_under_it():
    console = screen(100)
    banner.show(console, "Checking this machine.", animate=False)
    assert "Checking this machine." in text_of(console)


def test_a_console_without_unicode_draws_the_same_letters_in_ascii():
    cp1252 = SimpleNamespace(file=SimpleNamespace(encoding="cp1252"))
    drawn = "\n".join(line.plain for line in banner.art(cp1252))
    assert "█" not in drawn
    assert "#" in drawn


def test_the_art_and_the_ascii_have_the_same_shape():
    """Only the ink changes, so a fallback console still gets the wordmark."""
    utf8 = [line.plain.replace("█", "#") for line in
            banner.art(SimpleNamespace(file=SimpleNamespace(encoding="utf-8")))]
    ascii_art = [line.plain for line in
                 banner.art(SimpleNamespace(file=SimpleNamespace(encoding="cp1252")))]
    assert utf8 == ascii_art


# --- the same wordmark in the two installers -------------------------------

# they run before python exists on the machine, so the art is duplicated there;
# duplicated art that nobody compares is art that drifts
def shell_art(path: str, opener: str, closer: str) -> list:
    text = Path(path).read_text(encoding="utf-8")
    body = text.split(opener, 1)[1].split(closer, 1)[0]
    return [line[2:] for line in body.strip("\n").splitlines()]


def test_the_shell_installer_draws_the_same_wordmark():
    assert shell_art("install.sh", "<<'ART'\n", "\nART") == banner.rows()


def test_the_powershell_installer_draws_the_same_wordmark():
    assert shell_art("install.ps1", '$art = @"\n', '\n"@') == banner.rows()
