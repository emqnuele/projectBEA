"""The menus the wizard and the doctor are driven with.

One rule holds the whole file together: **there is always the other way**.
Every widget here reads the arrow keys when it is talking to a terminal, and
falls back to the numbered prompt it replaced when it is not — a pipe, CI, the
docker setup container, `BEA_NO_TUI=1`. A first-run wizard that only works on a
tty is a first-run wizard that cannot be scripted, and that was never the deal.

The drawing is deliberately thin: one highlighted row, the hint of whatever is
highlighted, and a footer saying which keys do something. Nothing here knows
what any of the answers mean.
"""

import sys
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.prompt import Prompt
from rich.text import Text

from src.setup import keys as keyboard

# (value, label, hint) — the hint is shown only for the highlighted row
Option = Tuple[str, str, str]

MOVE_HINT = "↑↓ move · enter select"
TOGGLE_HINT = "↑↓ move · space toggle · enter confirm"
YES_NO_HINT = "←→ or y/n · enter confirm"

# the two characters that are not ascii, and what to use where they cannot be
# printed — a cp1252 console raises on them rather than showing a box
_FANCY = {"pointer": "❯", "checked": "◉", "unchecked": "○"}
_PLAIN = {"pointer": ">", "checked": "(x)", "unchecked": "( )"}


def supports_unicode(console: Optional[Console] = None) -> bool:
    """Whether this console can print the pointer without raising."""
    stream = getattr(console, "file", None) or sys.stdout
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        "❯◉○".encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def glyphs(console: Optional[Console] = None) -> dict:
    return _FANCY if supports_unicode(console) else _PLAIN


def interactive(console: Console, keys: Optional[Iterator[str]] = None) -> bool:
    """Whether to draw a live menu. An injected key source always counts."""
    if keys is not None:
        return True
    return bool(console.is_terminal and keyboard.usable())


# --- one of many -------------------------------------------------------------


def select(console: Console, question: str, options: Sequence[Option],
           default: Optional[str] = None, *,
           keys: Optional[Iterator[str]] = None) -> str:
    """One option's value, chosen with the arrows or typed as a number."""
    if not options:
        raise ValueError("a menu with nothing in it")
    index = _index_of(options, default)
    if not interactive(console, keys):
        return _numbered(console, question, options, index)

    source = keys if keys is not None else keyboard.keys()
    marks = glyphs(console)
    with Live(console=console, auto_refresh=False, transient=True) as live:
        while True:
            live.update(_menu(console, question, options, index, marks, MOVE_HINT),
                        refresh=True)
            key = next(source, keyboard.ENTER)
            moved = _move(key, index, len(options))
            if moved is not None:
                index = moved
                continue
            if key == keyboard.ENTER:
                break
            jumped = _digit(key, len(options))
            if jumped is not None:
                index = jumped
                break

    _echo(console, question, options[index][1], marks)
    return options[index][0]


def multiselect(console: Console, question: str, options: Sequence[Option],
                selected: Iterable[str] = (), *,
                keys: Optional[Iterator[str]] = None) -> List[str]:
    """Any number of the options, in the order they are offered.

    The fallback asks one yes/no per option, which is what the wizard did
    before this existed — the same questions, one screen instead of five.
    """
    chosen = {value for value in selected}
    if not interactive(console, keys):
        return [value for value, label, _ in options
                if _confirm_fallback(console, f"  {label}", value in chosen)]

    index = 0
    source = keys if keys is not None else keyboard.keys()
    marks = glyphs(console)
    with Live(console=console, auto_refresh=False, transient=True) as live:
        while True:
            live.update(_menu(console, question, options, index, marks, TOGGLE_HINT,
                              chosen=chosen), refresh=True)
            key = next(source, keyboard.ENTER)
            moved = _move(key, index, len(options))
            if moved is not None:
                index = moved
                continue
            if key in (keyboard.SPACE, keyboard.RIGHT, keyboard.LEFT):
                value = options[index][0]
                chosen.symmetric_difference_update({value})
                continue
            if key == keyboard.ENTER:
                break
            jumped = _digit(key, len(options))
            if jumped is not None:
                index = jumped
                chosen.symmetric_difference_update({options[jumped][0]})

    picked = [value for value, _, _ in options if value in chosen]
    labels = {value: label for value, label, _ in options}
    _echo(console, question, ", ".join(labels[value] for value in picked) or "none", marks)
    return picked


def confirm(console: Console, question: str, default: bool = True, *,
            keys: Optional[Iterator[str]] = None) -> bool:
    """Yes or no, as a pair you move between. `y` and `n` still work."""
    if not interactive(console, keys):
        return _confirm_fallback(console, question, default)

    answer = default
    source = keys if keys is not None else keyboard.keys()
    with Live(console=console, auto_refresh=False, transient=True) as live:
        while True:
            live.update(_yes_no(question, answer), refresh=True)
            key = next(source, keyboard.ENTER)
            if key in (keyboard.LEFT, keyboard.RIGHT, keyboard.TAB, keyboard.UP,
                       keyboard.DOWN):
                answer = not answer
                continue
            if isinstance(key, str) and key.lower() in ("y", "n"):
                answer = key.lower() == "y"
                break
            if key == keyboard.ENTER:
                break

    console.print(Text.assemble(("  ✓ ", "green"), (question.strip(), "dim"), "  ",
                                ("yes" if answer else "no", "bold")))
    return answer


# --- drawing -----------------------------------------------------------------


def _menu(console: Console, question: str, options: Sequence[Option], index: int,
          marks: dict, footer: str, chosen: Optional[set] = None) -> RenderableType:
    rows: List[RenderableType] = [
        Text.assemble(("  ", ""), (question, "bold"), ("   ", ""), (footer, "dim"))
    ]
    first, last = _window(index, len(options), _room(console, len(options)))
    if first > 0:
        rows.append(Text("      …", style="dim"))
    for position in range(first, last):
        rows.append(_row(options[position], position == index, marks, chosen))
    if last < len(options):
        rows.append(Text("      …", style="dim"))

    hint = options[index][2]
    rows.append(Text(f"    {hint}" if hint else "", style="dim"))
    return Group(*rows)


def _row(option: Option, current: bool, marks: dict, chosen: Optional[set]) -> Text:
    value, label, _ = option
    box = ""
    if chosen is not None:
        box = (marks["checked"] if value in chosen else marks["unchecked"]) + " "
    pointer = marks["pointer"] if current else " " * len(marks["pointer"])
    style = "bold cyan" if current else ""
    return Text.assemble(("  ", ""), (pointer, "bold cyan"), (" ", ""),
                         (box, "cyan" if chosen and value in chosen else "dim"),
                         (label, style))


def _yes_no(question: str, answer: bool) -> RenderableType:
    yes = ("  yes  ", "bold black on cyan" if answer else "dim")
    no = ("  no  ", "dim" if answer else "bold black on cyan")
    return Group(
        Text.assemble(("  ", ""), (question, "bold"), ("   ", ""), (YES_NO_HINT, "dim")),
        Text.assemble(("  ", ""), yes, ("  ", ""), no),
    )


def _echo(console: Console, question: str, answer: str, marks: dict) -> None:
    """What is left on screen after the live menu is torn down."""
    console.print(Text.assemble(("  ✓ ", "green"), (question.strip(), "dim"), "  ",
                                (answer, "bold")))


def _room(console: Console, count: int) -> int:
    """How many rows the menu may use, so a long list still fits a short window."""
    height = console.size.height if console.is_terminal else count + 4
    return max(3, min(count, height - 5))


def _window(index: int, count: int, room: int) -> Tuple[int, int]:
    """The slice of a long list to draw, keeping the cursor inside it."""
    if room >= count:
        return 0, count
    first = min(max(0, index - room // 2), count - room)
    return first, first + room


# --- keys --------------------------------------------------------------------


def _move(key: str, index: int, count: int) -> Optional[int]:
    """The new index for a movement key, or None when it was not one."""
    if key in (keyboard.UP, "k"):
        return (index - 1) % count
    if key in (keyboard.DOWN, "j"):
        return (index + 1) % count
    if key == keyboard.HOME:
        return 0
    if key == keyboard.END:
        return count - 1
    return None


def _digit(key: str, count: int) -> Optional[int]:
    """The index a typed number picks, for the fingers that learned the old menu."""
    if isinstance(key, str) and key.isdigit() and key != "0":
        index = int(key) - 1
        if index < count:
            return index
    return None


def _index_of(options: Sequence[Option], default: Optional[str]) -> int:
    for position, (value, _, _) in enumerate(options):
        if value == default:
            return position
    return 0


# --- the way that works without a keyboard -----------------------------------


def _numbered(console: Console, question: str, options: Sequence[Option],
              index: int) -> str:
    """The menu this file replaced, kept for everywhere it cannot draw."""
    for position, (_, label, hint) in enumerate(options, 1):
        mark = "[cyan]•[/cyan]" if position - 1 == index else " "
        console.print(f"  [bold cyan]{position}[/] {mark} [bold]{label}[/]")
        if hint:
            console.print(f"        [dim]{hint}[/]")
    console.print()

    answer = Prompt.ask(
        f"  {question}",
        choices=[str(i) for i in range(1, len(options) + 1)],
        default=str(index + 1),
        show_choices=False,
    )
    return options[int(answer) - 1][0]


def _confirm_fallback(console: Console, question: str, default: bool) -> bool:
    from rich.prompt import Confirm

    return Confirm.ask(question, default=default, console=console)
