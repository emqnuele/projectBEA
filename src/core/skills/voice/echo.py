"""Her own voice, come back round.

Nothing in a call stops the room from hearing her. A listener on speakers has
her coming out of them and going straight back into their microphone, and the
bot receives that as something they said — the gate agrees, because it *is* a
voice, and the transcriber agrees, because it is a voice saying words.

Discord's own client cancels most of it most of the time, which is exactly the
kind of guarantee that holds until somebody turns their volume up. What it
costs when it stops holding is a loop with nothing in it to stop: she says a
line, the line comes back as a thing somebody said to her, she answers it, and
the answer comes back too. An apology is the worst of them, because an apology
is what she reaches for when a turn makes no sense to her — so the loop feeds
itself, forty of them in a row, while the person in the call was talking about
something else entirely.

This is not echo cancellation; the audio is long gone by the time anything here
runs. It is the text end of the same problem, and the text end is enough: a
transcript that is mostly a run of something she said a moment ago did not come
out of the room.
"""

import unicodedata
from difflib import SequenceMatcher
from typing import Iterable

# How much of what was heard has to be a run of what she just said. Compared
# character by character rather than word by word, because the transcriber gets
# the edges of an echo wrong — "Could you say it again?" comes back as "could
# you say that again" — and because a script written without spaces has no
# words to compare. Measured against real echoes off a speaker at -20 dB, which
# match at 0.85 and up; two people saying "sì, esatto" a minute apart, which is
# the false positive worth fearing, sits well under it.
MATCH = 0.72

# Under this much text there is nothing to be sure about. "sì", "ok", "aspetta"
# are things she says and things people say back, and dropping a real one costs
# the turn while letting one through costs nothing.
MIN_CHARS = 12


def normalize(text: str) -> str:
    """Letters and digits, lowercase, single-spaced. Punctuation is noise here."""
    kept = [
        character.lower() if unicodedata.category(character)[0] in "LN" else " "
        for character in unicodedata.normalize("NFKC", text or "")
    ]
    return " ".join("".join(kept).split())


def overlap(heard: str, said: str) -> float:
    """How much of `heard` is made of runs of `said`, from 0 to 1."""
    if not heard or not said:
        return 0.0
    matcher = SequenceMatcher(None, said, heard, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched / len(heard)


def is_echo(transcript: str, spoken: Iterable[str], threshold: float = MATCH) -> bool:
    """Whether this transcript is her own voice rather than somebody else's.

    `spoken` is what she has said recently and nothing older: the same sentence
    said again ten minutes later is somebody quoting her, which is a real thing
    for her to hear.
    """
    heard = normalize(transcript)
    if len(heard) < MIN_CHARS:
        return False
    return any(overlap(heard, normalize(said)) >= threshold for said in spoken)
