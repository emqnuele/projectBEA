"""Reading one keystroke, on the three operating systems she installs on.

The wizard used to ask for a number because a number is the one thing
`input()` can read portably. Arrows are not harder — they are one escape
sequence and one Windows API — but they have to be decoded in the one place,
because every menu below would otherwise grow its own half of the table.

Nothing here draws anything. `tui.py` does the drawing; this file turns bytes
into a name, and says when there is no keyboard to read from at all.
"""

import os
import sys
from contextlib import contextmanager
from typing import Iterator, Optional, TextIO

UP = "up"
DOWN = "down"
LEFT = "left"
RIGHT = "right"
ENTER = "enter"
SPACE = "space"
ESCAPE = "escape"
TAB = "tab"
HOME = "home"
END = "end"
BACKSPACE = "backspace"

# ctrl-c and ctrl-d, for the terminals that hand them over as bytes instead of
# raising. In cbreak mode the signal still fires, so this is the other half.
_INTERRUPT = "\x03"
_EOF = "\x04"

# `ESC [ A` and the application-keypad `ESC O A` both mean "up"
_ESCAPES = {
    "A": UP, "B": DOWN, "C": RIGHT, "D": LEFT,
    "H": HOME, "F": END,
    "1~": HOME, "4~": END, "7~": HOME, "8~": END,
}

# what the two-byte windows scancodes mean, after the \x00 or \xe0 lead byte
_WINDOWS = {
    "H": UP, "P": DOWN, "M": RIGHT, "K": LEFT, "G": HOME, "O": END,
}


def usable(stream: Optional[TextIO] = None) -> bool:
    """Whether a menu can read this keyboard at all.

    False in CI, in a pipe, in the docker setup container and anywhere
    `BEA_NO_TUI` is set — every one of which still gets the numbered prompt,
    which is what the wizard has always done.
    """
    if os.getenv("BEA_NO_TUI"):
        return False
    if (os.getenv("TERM") or "").lower() == "dumb":
        return False
    try:
        return bool(_stream(stream).isatty() and sys.stdout.isatty())
    except Exception:
        return False


def _stream(stream: Optional[TextIO] = None) -> TextIO:
    """The keyboard to read from. A detached process (pythonw) has none."""
    chosen = stream if stream is not None else sys.stdin
    if chosen is None:
        raise EOFError("there is no standard input to read a key from")
    return chosen


@contextmanager
def raw_mode(stream: Optional[TextIO] = None) -> Iterator[None]:
    """The terminal in cbreak for the life of a menu, and back afterwards.

    Held open across the whole menu rather than taken per keypress: between two
    reads the terminal would otherwise be back in canonical mode, where a key
    pressed a moment too early is echoed on screen and held until enter.

    cbreak, not raw: raw also turns off the newline translation on the way
    *out*, and every line rich prints then stair-steps down the screen.

    `TCSANOW` at both ends, twice deliberately. Going in, tty's own default is
    `TCSAFLUSH`, which throws away whatever was typed before we got here.
    Coming out, the usual `TCSADRAIN` waits for the terminal's output queue to
    empty — which, against a pty nobody is reading, is forever.
    """
    if sys.platform == "win32":
        yield
        return

    import termios
    import tty

    descriptor = _stream(stream).fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor, termios.TCSANOW)
        yield
    finally:
        termios.tcsetattr(descriptor, termios.TCSANOW, previous)


def read_key(stream: Optional[TextIO] = None) -> str:
    """One keypress, as a name from this module or the character itself.

    Raises KeyboardInterrupt on ctrl-c and EOFError on ctrl-d, so a menu never
    has to invent what either of them means.
    """
    if sys.platform == "win32":
        return _windows_key()
    keyboard = _stream(stream)
    with raw_mode(keyboard):
        return _posix_key(keyboard.fileno())


def keys(stream: Optional[TextIO] = None) -> Iterator[str]:
    """Keypresses, for as long as the caller reads them.

    Closing the generator is what puts the terminal back, so a menu closes it
    rather than leaving it to the collector.
    """
    if sys.platform == "win32":
        while True:
            yield _windows_key()
        return

    keyboard = _stream(stream)
    with raw_mode(keyboard):
        while True:
            yield _posix_key(keyboard.fileno())


def _named(char: str) -> str:
    if char in ("\r", "\n"):
        return ENTER
    if char == " ":
        return SPACE
    if char == "\t":
        return TAB
    if char in ("\x7f", "\b"):
        return BACKSPACE
    if char == _INTERRUPT:
        raise KeyboardInterrupt
    if char == _EOF:
        raise EOFError
    return char


def _windows_key() -> str:
    # the platform check is the narrowing a type checker needs to read the
    # windows-only module below at all, on the other two platforms
    if sys.platform != "win32":
        raise RuntimeError("the windows key reader on a machine that is not windows")

    import msvcrt

    char = msvcrt.getwch()
    if char in ("\x00", "\xe0"):
        return _WINDOWS.get(msvcrt.getwch(), "")
    return _named(char)


def _posix_key(descriptor: int) -> str:
    """One key off an already-cbreak terminal."""
    char = _one(descriptor)
    if char != "\x1b":
        return _named(char)
    return _escape(descriptor)


def _one(descriptor: int) -> str:
    """One byte, as a character.

    `os.read`, not a file object: a buffered reader is free to wait for a whole
    block, which on a terminal is a key that never arrives.
    """
    raw = os.read(descriptor, 1)
    if not raw:
        raise EOFError
    return raw.decode("utf-8", "replace")


def _escape(descriptor: int) -> str:
    """The rest of an escape sequence, or ESCAPE when the key was ESC itself."""
    import select

    def waiting() -> bool:
        return bool(select.select([descriptor], [], [], 0.05)[0])

    if not waiting():
        return ESCAPE
    kind = _one(descriptor)
    if kind not in ("[", "O"):
        return ESCAPE

    body = ""
    while waiting():
        body += _one(descriptor)
        if body[-1].isalpha() or body[-1] == "~":
            break
    return _ESCAPES.get(body, "")
