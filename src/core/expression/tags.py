"""Direction written inside a spoken line.

She picks one mood for a turn, and a turn is often longer than one feeling. A
line that starts amused and ends annoyed had, until now, one face for both
halves — and the face changed a beat before the first word rather than at the
moment the line turns.

So the direction travels inside the text, where she can put it exactly where it
belongs:

    <mood:smug> nice try. <do:shrug> genuinely, well done.

Two tags, both optional, both stripped before anything is synthesised. `mood`
changes her face from that point on; `do` plays a behaviour. The name inside a
tag is free text: what she writes is matched to the nearest thing she actually
has, so there is no list to memorise and no way to name something that does not
exist.

Pure: text in, beats out. Nothing here knows what a face or a clip is.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List


class BeatKind(str, Enum):
    SAY = "say"
    MOOD = "mood"
    DO = "do"


@dataclass(frozen=True)
class Beat:
    """One thing to do, in the order she wrote it."""

    kind: BeatKind
    value: str


# the two kinds that are direction rather than speech, taken off the enum so the
# parser, the manual she reads and the tool schema cannot end up naming
# different tags
DIRECTIONS: tuple = tuple(kind.value for kind in BeatKind if kind is not BeatKind.SAY)

# the name is deliberately permissive — it is matched, not looked up, so
# `<mood:quietly pleased>` is as valid as `<mood:love>`
_TAG = re.compile(rf"<({'|'.join(DIRECTIONS)}):([A-Za-z0-9 _-]{{1,40}})>", re.IGNORECASE)

# anything else tag-shaped that reached the text: a typo'd direction, a stray
# html-ish span. Must start with a letter, so "a < b" and "<3" survive.
_TAG_SHAPED = re.compile(r"<[A-Za-z][^<>]{0,80}>")

# a direction the model started and never closed. It only reaches here on a line
# that has already ended, so there is nothing left to wait for and the choice is
# between dropping it and reading `<mood:sm` out loud.
_TAG_UNCLOSED = re.compile(r"<[A-Za-z][^<>]{0,80}$")

# past this many characters with no `>`, a lone `<` is just a less-than sign.
# Without a ceiling a line containing "5 < 6" would never finish streaming.
MAX_TAG_CHARS = 48


def _clean(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip().lower()


def parse(text: str) -> List[Beat]:
    """Split a line into speech and direction, keeping the original order."""
    beats: List[Beat] = []
    cursor = 0

    for match in _TAG.finditer(text):
        said = text[cursor:match.start()].strip()
        if said:
            beats.append(Beat(BeatKind.SAY, said))
        name = _clean(match.group(2))
        if name:
            beats.append(Beat(BeatKind[match.group(1).upper()], name))
        cursor = match.end()

    tail = text[cursor:].strip()
    if tail:
        beats.append(Beat(BeatKind.SAY, tail))
    return beats


def strip(text: str) -> str:
    """What is left to say once every direction is taken out.

    Also removes anything merely tag-shaped: a direction she misspelled would
    otherwise be read out loud, which is the one failure the audience notices.
    """
    out = _TAG.sub(" ", text or "")
    out = _TAG_SHAPED.sub(" ", out)
    out = _TAG_UNCLOSED.sub(" ", out)
    return re.sub(r"[ \t]+", " ", out).strip()


def visible_len(text: str) -> int:
    """How much of this would actually be spoken.

    The length that matters for chunking: a piece that is all direction and two
    words is not a sentence worth its own synthesis, however long it looks.
    """
    return len(strip(text))


def open_tag(text: str) -> bool:
    """Whether the text ends inside a direction that has not closed yet.

    Cutting here would send half a tag to the engine and leave the other half
    to be read out as words.
    """
    start = text.rfind("<")
    if start == -1 or text.rfind(">") > start:
        return False
    rest = text[start + 1:]
    if len(rest) >= MAX_TAG_CHARS:
        return False
    # `<` followed by anything that cannot begin a tag is a less-than sign
    return rest == "" or rest[0].isalpha()


def direction_help() -> str:
    """How to write direction, generated from the tags this file understands.

    Lives here rather than in the manual because the manual is a file people
    edit: a tag renamed in the parser and not in the file is a tag she keeps
    writing and nobody keeps reading.
    """
    mood, do = BeatKind.MOOD.value, BeatKind.DO.value
    return f"""\
The mood you pass to `speak` is the face you start the line with. You can change it
again *mid-line*, and move, by writing direction into the message itself — it is
stripped before anything is spoken:

    <{mood}:smug> nice try. <{do}:shrug> genuinely, well done.

- `<{mood}:word>` — your face from that word on. Any word for a feeling works: the
  nearest one you actually have is used.
- `<{do}:word>` — a behaviour, if your body has any. Describe what you are doing
  rather than guessing a file name. Nothing plays if you have nothing like it.

Put one where the line actually turns. One on every sentence reads as twitching."""
