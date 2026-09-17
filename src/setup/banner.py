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
from typing import List, Optional, Sequence, Tuple

from rich.console import Console, Group, RenderableType
from rich.text import Text

# the brand accent from the dashboard, run up to the cyan end of itself
GRADIENT: Tuple[str, str] = ("#3d7dff", "#7ef0ff")

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


def _ramp(steps: int, ends: Tuple[str, str] = GRADIENT) -> List[str]:
    """`steps` hex colours from one end of the gradient to the other."""
    start = tuple(int(ends[0][i:i + 2], 16) for i in (1, 3, 5))
    stop = tuple(int(ends[1][i:i + 2], 16) for i in (1, 3, 5))
    if steps <= 1:
        return [ends[0]]
    out = []
    for step in range(steps):
        fraction = step / (steps - 1)
        channels = [round(a + (b - a) * fraction) for a, b in zip(start, stop, strict=True)]
        out.append("#{:02x}{:02x}{:02x}".format(*channels))
    return out


def _block(console: Optional[Console]) -> Optional[str]:
    """The character to draw with, or None when this console has no unicode."""
    from src.setup.tui import supports_unicode

    return "█" if supports_unicode(console) else None


def art(console: Optional[Console] = None, text: str = WORDMARK) -> List[Text]:
    """The wordmark as coloured lines, left to right along the gradient."""
    block = _block(console) or "#"
    colours = _ramp(max(width(text), 1))
    lines: List[Text] = []
    for row in rows(text):
        line = Text("  ")
        for column, char in enumerate(row):
            if char == "#":
                line.append(block, style=colours[min(column, len(colours) - 1)])
            else:
                line.append(" ")
        lines.append(line)
    return lines


def fits(console: Console, text: str = WORDMARK) -> bool:
    return console.width >= width(text) + 4


def plain(console: Optional[Console] = None) -> Text:
    """The one-line fallback: the name, in the casing the project writes it."""
    colours = _ramp(len("projectBEA"))
    line = Text("  ")
    for index, char in enumerate("projectBEA"):
        line.append(char, style=f"bold {colours[index]}")
    return line


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
