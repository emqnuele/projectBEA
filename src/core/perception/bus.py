import asyncio
import time
from typing import List, Optional

from src.core.perception.types import Perception, PerceptionKind
from src.utils.logger import get_logger

logger = get_logger("bea.perception.bus")


def _running_loop() -> Optional[asyncio.AbstractEventLoop]:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


class PerceptionBus:
    """The single sensory channel feeding the one consciousness.

    Every surface (chat, voice, game, future twitch/telegram) pushes `Perception`
    objects here. The consciousness loop drains them. This replaces the ad-hoc
    per-channel buffering (interaction_buffer, pending_transcripts, flush timers).

    One batch, one frame, one turn — and the batch is what this file decides.
    It closes on a **quiet gap**: nothing new for `window` seconds, rather than
    `window` seconds after the first thing arrived. Somebody typing "hey" /
    "come stai" / "tutto bene?" pauses about a second between lines and means
    one thing by all three; a stopwatch started by the first of them hands the
    loop one line at a time and she answers three times.
    """

    def __init__(self, window: float = 0.3, max_window: float = 0.0,
                 text_window: float = 0.0):
        # the gap a live sense waits for one more of its own: a voice line, a
        # game event, a donation. Short, because a second of dead air in a call
        # is a second she took to answer.
        self.window = window
        # the gap written text waits. Longer, because the pause between two
        # typed lines is a person still typing, not a person who has finished.
        self.text_window = text_window if text_window > 0 else window
        # and the ceiling on the whole batch, so a busy chat cannot hold the
        # turn open for as long as it keeps talking
        self.max_window = max_window if max_window > 0 else max(window, self.text_window) * 10
        self._queue: "asyncio.Queue[Perception]" = asyncio.Queue()
        # the loop that drains the queue, once it has started to
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def put(self, perception: Perception) -> None:
        """Enqueues from the loop or from any other thread."""
        loop = self._loop
        if loop is not None and not loop.is_closed() and loop is not _running_loop():
            loop.call_soon_threadsafe(self._queue.put_nowait, perception)
        else:
            self._queue.put_nowait(perception)
        logger.debug(f"perceived [{perception.kind}] from {perception.surface}: {perception.content[:60]}")

    def drain_nowait(self) -> List[Perception]:
        """Returns everything currently queued without waiting (steering input)."""
        items: List[Perception] = []
        while True:
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return items

    async def drain(self, window: Optional[float] = None) -> List[Perception]:
        """Waits for at least one perception, then for the senses to go quiet."""
        self._loop = asyncio.get_running_loop()
        first = await self._queue.get()
        return await self.settle([first], window)

    async def settle(self, items: List[Perception],
                     window: Optional[float] = None) -> List[Perception]:
        """Keeps taking until nothing new has arrived for a gap, or `max_window`.

        Every arrival pushes the deadline out, so the batch closes when the
        person stops rather than on a clock they never saw. The gap is set by
        the most impatient thing in the batch: one voice line among three typed
        ones means she answers at voice speed.
        """
        gap = self._gap(items) if window is None else window
        if gap <= 0:
            items.extend(self.drain_nowait())
            items.sort(key=lambda p: p.ts)
            return items

        ceiling = time.monotonic() + self.max_window
        while True:
            remaining = min(gap, ceiling - time.monotonic())
            if remaining <= 0:
                break
            try:
                arrived = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            items.append(arrived)
            if window is None:
                gap = min(gap, self._gap([arrived]))

        items.sort(key=lambda p: p.ts)
        return items

    def _gap(self, items: List[Perception]) -> float:
        """How long this batch waits for one more thing to arrive."""
        gaps = [self.text_window if p.kind is PerceptionKind.CHAT else self.window
                for p in items]
        return min(gaps) if gaps else self.window

    async def wait_or_idle(self, idle_after: float) -> List[Perception]:
        """Drains perceptions; if `idle_after` seconds pass with none, emits an IDLE.

        This replaces the monologue idle timer: 'nothing happened' becomes a
        first-class perception the consciousness can react to (start a monologue).

        A surface that heartbeats marks its texture `noise`, and texture is not
        something happening: counting it would reset the deadline forever and
        she would never notice the silence at all. The game body heartbeats
        every few seconds, so this is the difference between a mind that can
        start on its own while playing and one that cannot.

        Past the timeout it settles exactly like `drain`: the batch must not
        depend on whether the monologue happens to be switched on.
        """
        self._loop = asyncio.get_running_loop()
        deadline = time.monotonic() + idle_after
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return [self._idle()]
            try:
                first = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return [self._idle()]

            items = await self.settle([first])
            if all((p.meta or {}).get("noise") for p in items):
                continue
            return items

    @staticmethod
    def _idle() -> Perception:
        return Perception(kind=PerceptionKind.IDLE, surface="idle",
                          content="(nothing is happening)", salience=0.1)
