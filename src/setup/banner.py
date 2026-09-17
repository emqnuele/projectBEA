"""The wordmark, in the only typeface a terminal has: its own character cell.

Every command someone runs before she exists — the installer, the wizard, the
doctor — opens with this. It is one screenful of "you are in the right place",
and it costs a 5x5 bitmap per letter.

It degrades twice, on purpose. A console that cannot print a block character
draws the same letters in `#`, and a window too narrow for the art gets the
name on one line instead. Neither is a failure worth a line of code at the
call site.
"""

import os
import time
from typing import List, Optional, Sequence

from rich.console import Console, Group, RenderableType
from rich.text import Text

# one colour, deliberately: the wordmark is a name, not a light show, and a
# single bright ink is the one thing every terminal theme renders the same
INK = "bold white"

TAGLINE = "She talks, plays, and remembers you."

# 5 rows, 5 columns, one space between letters. Only the ten letters the
# wordmark needs — a full alphabet here would be nine unused glyphs.
FONT = {
    "P": ("####", "#   #", "####", "#", "#"),
    "R": ("####", "#   #", "####", "#  #", "#   #"),
    "O": (" ### ", "#   #", "#   #", "#   #", " ### "),
    "J": ("  ###", "   # ", "   # ", "#  # ", " ##  "),
    "E": ("#####", "#", "#### ", "#", "#####"),
    "C": (" ####", "#", "#", "#", " ####"),
    "T": ("#####", "  #  ", "  #  ", "  #  ", "  #  "),
    "B": ("#### ", "#   #", "#### ", "#   #", "#### "),
    "A": (" ### ", "#   #", "#####", "#   #", "#   #"),
    " ": ("", "", "", "", ""),
}

WORDMARK = "PROJECT BEA"
HEIGHT = 5
CELL = 5
GAP = 1


def width(text: str = WORDMARK) -> int:
    """How many columns the art needs, indent excluded."""
    return len(text) * (CELL + GAP) - GAP


def rows(text: str = WORDMARK) -> List[str]:
    """The art, as `HEIGHT` lines of `#` and spaces."""
    lines = []
    for row in range(HEIGHT):
        cells = [FONT.get(letter, FONT[" "])[row].ljust(CELL)[:CELL] for letter in text]
        lines.append((" " * GAP).join(cells).rstrip())
    return lines


def _block(console: Optional[Console]) -> Optional[str]:
    """The character to draw with, or None when this console has no unicode."""
    from src.setup.tui import supports_unicode

    return "█" if supports_unicode(console) else None


def art(console: Optional[Console] = None, text: str = WORDMARK) -> List[Text]:
    """The wordmark, one line per row of the font."""
    block = _block(console) or "#"
    return [Text("  " + row.replace("#", block), style=INK) for row in rows(text)]


def fits(console: Console, text: str = WORDMARK) -> bool:
    return console.width >= width(text) + 4


def plain(console: Optional[Console] = None) -> Text:
    """The one-line fallback: the name, in the casing the project writes it."""
    return Text("  projectBEA", style=INK)


def show(console: Console, subtitle: str = TAGLINE, *, animate: bool = True) -> None:
    """Prints the wordmark. The animation is a nicety, never a wait worth having."""
    console.print()
    lines: Sequence[RenderableType]
    if fits(console):
        lines = art(console)
    else:
        lines = [plain(console)]

    if animate and console.is_terminal and not os.getenv("BEA_NO_TUI"):
        for line in lines:
            console.print(line)
            time.sleep(0.04)
    else:
        console.print(Group(*lines))

    if subtitle:
        console.print(Text(f"  {subtitle}", style="dim"))
    console.print()
