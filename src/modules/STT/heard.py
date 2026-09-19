"""The language of the last turn that was long enough to have settled one.

`config.language` answers "what is she pinned to", and `auto` — the default —
answers "work it out from the audio". That second answer is a good one for a
sentence and a terrible one for a word: measured on real italian speech cut to
length, half a second of it came back as french at p=0.80, eight tenths as
spanish, and three tenths as `Thank you for watching.` It only settles past
about a second.

A call is mostly turns shorter than that. "sì", "no", "aspetta", "che?" are
most of what anybody says while somebody else is talking, and every one of them
was a fresh coin toss — so a conversation in one language arrived as a
transcript in five.

Nothing here is a better detector. It is the observation that a call does not
change language between two sentences: a turn too short to be asked borrows the
answer from the last turn that was long enough to be worth asking. Shared by
all three transcribers, because the problem is in the audio rather than in any
one engine.
"""

import time
import wave
from typing import Callable, Optional

from src.core import language as language_module

# under this much audio, the question is not worth putting
MIN_DETECT_SECONDS = 1.2

# and how long the answer from a turn that *was* long enough stays good for.
# Long enough to cover a conversation, short enough that tomorrow's call starts
# by listening rather than by assuming.
HEARD_FOR_SECONDS = 300.0

# how sure a detector has to be before its answer is worth keeping. High,
# because failing to keep a right answer costs one borrowed pin and keeping a
# wrong one costs the rest of the call.
CONFIDENT = 0.85


def clip_seconds(path: str) -> float:
    """How long the audio is, or 0.0 when it cannot be told from the header.

    The header alone on purpose: everything that reaches here is about to be
    decoded by something else anyway, and decoding it twice to find out whether
    it is worth asking a question about is the wrong trade. Whatever the bot
    sends is a wav it wrote itself.
    """
    try:
        with wave.open(path) as clip:
            rate = clip.getframerate()
            return clip.getnframes() / float(rate) if rate else 0.0
    except Exception:
        return 0.0


class HeardLanguage:
    """What the last real sentence was in, for the turns too short to say."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._code: Optional[str] = None
        self._at = 0.0
        self._clock = clock

    @property
    def borrowed(self) -> Optional[str]:
        """The remembered language, while it is still recent enough to use."""
        if self._code is None or self._clock() - self._at > HEARD_FOR_SECONDS:
            return None
        return self._code

    def pin_for(self, configured: Optional[str], seconds: float) -> Optional[str]:
        """What to send as the language, or None to let the engine detect it.

        A configured pin always wins: someone who has said which language this
        install is in has answered the question for every turn in it. An
        unknown duration counts as long enough — better to ask and be told than
        to pin an hour of audio to whatever the last thing heard was.
        """
        if configured:
            return configured
        if seconds <= 0 or seconds >= MIN_DETECT_SECONDS:
            return None
        return self.borrowed

    def remember(self, reported: Optional[str], seconds: float,
                 probability: float = 1.0) -> None:
        """Files what a turn turned out to be in, if it is worth filing.

        `reported` is whatever the engine called it — a code, or a name like
        `italian`, which is what the hosted ones answer with. Anything this
        engine cannot place is not remembered rather than remembered wrongly.
        """
        if seconds < MIN_DETECT_SECONDS or probability < CONFIDENT:
            return
        code = language_module.resolve(reported)
        if code == language_module.AUTO:
            return
        self._code, self._at = code, self._clock()
