"""A line she is saying while it is still being written.

Until now a spoken turn existed all at once: the model finished the whole line,
then it was synthesised, then it was heard. Each of those waited for the one
before it to finish completely, so the delay before the first sound was the sum
of all three — and it grew with how much she had to say, which is the opposite
of how talking works.

This is the pipeline that takes them apart. Text arrives in pieces, a chunker
cuts it where a person would breathe, one task synthesises the next piece while
another plays the current one, and the direction she wrote inline keeps its place
in the queue so her face changes on the word she meant it to.

    say(text) -> chunker -> [beats] -> render -> [ready] -> play -> the room

`ready` is deliberately tiny. Rendering further ahead buys nothing — playback is
the slow half — and every piece rendered ahead is one more thing paid for and
thrown away when somebody talks over her.

The sink is whatever turns a piece into sound and puts a face on her; `Expression`
is the only one, and it is passed in rather than imported so this file stays
about ordering and nothing else.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from src.core.expression.chunking import SpeechChunker
from src.core.expression.tags import Beat, BeatKind, parse
from src.utils.logger import get_logger
from src.utils.sanitize import clean_model_output

logger = get_logger("bea.expression.live")

# how many pieces may be synthesised ahead of the one being played
LOOKAHEAD = 1


@dataclass
class Rendered:
    """A beat with whatever the engine made of it, waiting its turn."""

    beat: Beat
    parts: List[Tuple[Any, int]] = field(default_factory=list)


class LiveLine:
    """One spoken line, delivered as it is written.

    The caller feeds it text — all at once, or a few characters at a time — and
    closes it when the line is finished. Everything in between is ordering: what
    she says, what her face does and what her body does all leave through the
    same queue, in the order she wrote them.
    """

    def __init__(self, sink, mood: str, *, route: str = "local", feeling=None):
        self.sink = sink
        self.mood = mood
        self.route = route
        self.feeling = feeling
        self.prosody = sink.prosody_for(mood, feeling)

        # the whole line when the caller already has it, so the words on screen
        # can be typed once instead of restarting at every sentence
        self.caption: Optional[str] = None

        # room for the sink to keep track of one line: the call needs an
        # utterance id, a sequence number and the shape of the mouth so far
        self.state: dict = {}

        # the line stopped being worth finishing — the room moved on
        self.abandoned = False

        # a whole piece of it turned out to be the model's own scaffolding
        self.tainted = False

        self._chunker = SpeechChunker()
        self._beats: "asyncio.Queue[Optional[Beat]]" = asyncio.Queue()
        self._ready: "asyncio.Queue[Optional[Rendered]]" = asyncio.Queue(maxsize=LOOKAHEAD)
        self._tasks: List[asyncio.Task] = []
        self._written: List[str] = []
        self._spoken: List[str] = []
        self._closed = False
        self._cancelled = False

    # --- what the caller drives ---------------------------------------------

    def start(self) -> None:
        """Open the pipeline. Idempotent, so a caller may just feed and close."""
        if self._tasks:
            return
        self.sink.line_opened(self)
        self._tasks = [
            asyncio.create_task(self._render(), name="live-render"),
            asyncio.create_task(self._play(), name="live-play"),
        ]

    def say(self, text: str) -> None:
        """Take more of the line. Whatever is ready to speak leaves at once."""
        if self._closed or self.tainted or not text:
            return
        self.start()
        self._written.append(text)
        for piece in self._chunker.push(text):
            self._enqueue(piece)

    def close_input(self) -> None:
        """No more text is coming: flush what is left and let the queue drain."""
        if self._closed:
            return
        self._closed = True
        self.start()
        for piece in self._chunker.flush():
            self._enqueue(piece)
        self._beats.put_nowait(None)

    async def close(self) -> Any:
        """Finish the line and wait for the room to have heard all of it."""
        self.close_input()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        return await self.sink.line_closed(self)

    async def cancel(self) -> None:
        """Somebody talked over her: stop, and stop paying for the rest."""
        self._cancelled = True
        self._closed = True
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # --- what the sink reads ------------------------------------------------

    @property
    def written(self) -> str:
        """Everything she was given to say, direction included."""
        return "".join(self._written)

    @property
    def spoken(self) -> str:
        """The pieces that actually reached the room, in order."""
        return " ".join(self._spoken)

    @property
    def started(self) -> bool:
        return bool(self._tasks)

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def spoiled(self) -> bool:
        """Scaffolding reached the line, and nothing has been heard yet.

        A stream is cleaned one piece at a time, which cannot see a `<think>`
        that closes two sentences later. When a whole piece turns out to be
        nothing but that, the line is thrown away and the caller says the
        finished message instead — which can be cleaned all at once. Nothing is
        lost while she has not been heard; once she has, this is over.
        """
        return self.tainted and not self._spoken

    # --- internals ----------------------------------------------------------

    def _enqueue(self, piece: str) -> None:
        """One chunk of writing becomes speech and direction, in written order."""
        for beat in parse(piece):
            if beat.kind is BeatKind.SAY:
                # the last gate before the engine: a cheap model leaks its own
                # scaffolding, and a chunk of that would be read out loud
                text = clean_model_output(beat.value)
                if not text:
                    # a whole piece of scaffolding means an opening tag whose
                    # end has not arrived, so the next piece is the inside of it
                    # — and the inside carries no tag to recognise it by. She
                    # stops here rather than read a reasoning chain out loud.
                    self.tainted = True
                    return
                beat = Beat(BeatKind.SAY, text)
            self._beats.put_nowait(beat)

    async def _render(self) -> None:
        """Turns the next piece into sound while the current one is playing."""
        try:
            while True:
                beat = await self._beats.get()
                if beat is None:
                    break
                if beat.kind is not BeatKind.SAY:
                    await self._ready.put(Rendered(beat))
                    continue
                try:
                    parts = await self.sink.render(self, beat.value, self.prosody)
                except Exception as e:
                    # one failed piece costs that piece, never the rest of the line
                    logger.error(f"Could not synthesise {beat.value!r}: {e}")
                    continue
                if parts is None:
                    self.abandoned = True
                    break
                if parts:
                    await self._ready.put(Rendered(beat, parts))
        except asyncio.CancelledError:
            # the player is being cancelled alongside this: it needs no sentinel
            raise
        except Exception as e:
            logger.error(f"The line stopped rendering: {e}")
        # whatever ended the loop, the player is waiting on this
        await self._ready.put(None)

    async def _play(self) -> None:
        """Plays what is ready, in the order it was written."""
        async with self.sink.playback_lock(self):
            while True:
                item = await self._ready.get()
                if item is None:
                    return
                if item.beat.kind is BeatKind.SAY:
                    await self.sink.play(self, item)
                    self._spoken.append(item.beat.value)
                elif item.beat.kind is BeatKind.MOOD:
                    self.sink.wear(self, item.beat.value)
                elif item.beat.kind is BeatKind.DO:
                    self.sink.behave(self, item.beat.value)
