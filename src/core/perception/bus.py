import asyncio
import time
from typing import Callable, List, Optional, Tuple

from src.core.perception.types import Perception, PerceptionKind
from src.utils.logger import get_logger

logger = get_logger("bea.perception.bus")

# how often a held batch looks again at whether it is still held
HOLD_POLL_S = 0.05


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
        # each perception with the moment it arrived: the quiet gap is counted
        # from there, not from whenever the loop got round to looking
        self._queue: "asyncio.Queue[Tuple[float, Perception]]" = asyncio.Queue()
        # the loop that drains the queue, once it has started to
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # a sense that knows more of this batch is on its way: somebody in the
        # call has started talking again, and their words are seconds from
        # being a perception. Asked with the batch; `max_window` still caps it.
        self.holds: List[Callable[[List[Perception]], bool]] = []

    def put(self, perception: Perception) -> None:
        """Enqueues from the loop or from any other thread."""
        entry = (time.monotonic(), perception)
        loop = self._loop
        if loop is not None and not loop.is_closed() and loop is not _running_loop():
            loop.call_soon_threadsafe(self._queue.put_nowait, entry)
        else:
            self._queue.put_nowait(entry)
        logger.debug(f"perceived [{perception.kind}] from {perception.surface}: {perception.content[:60]}")

    def drain_nowait(self) -> List[Perception]:
        """Returns everything currently queued without waiting (steering input)."""
        return [p for _, p in self._waiting()]

    def _waiting(self) -> List[Tuple[float, Perception]]:
        entries: List[Tuple[float, Perception]] = []
        while True:
            try:
                entries.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return entries

    async def drain(self, window: Optional[float] = None) -> List[Perception]:
        """Waits for at least one perception, then for the senses to go quiet."""
        self._loop = asyncio.get_running_loop()
        arrived, first = await self._queue.get()
        return await self.settle([first], window, last=arrived)

    async def settle(self, items: List[Perception], window: Optional[float] = None,
                     last: Optional[float] = None) -> List[Perception]:
        """Keeps taking until nothing new has arrived for a gap, or `max_window`.

        Every arrival pushes the deadline out, so the batch closes when the
        person stops rather than on a clock they never saw. The gap is set by
        the most impatient thing in the batch: one voice line among three typed
        ones means she answers at voice speed.

        The gap runs from the last arrival (`last`, a monotonic reading), not
        from now. What queued up while she was busy answering has already been
        quiet for as long as she was busy, and making it wait a whole gap more
        put up to a second of dead air in front of every reply to it.
        """
        gap = self._gap(items) if window is None else window
        last = time.monotonic() if last is None else last
        # everything already waiting arrived with this batch, however long ago
        for arrived, perception in self._waiting():
            items.append(perception)
            last = max(last, arrived)
            if window is None:
                gap = min(gap, self._gap([perception]))
        if gap <= 0:
            items.sort(key=lambda p: p.ts)
            return items

        ceiling = time.monotonic() + self.max_window
        while True:
            now = time.monotonic()
            until_ceiling = ceiling - now
            if until_ceiling <= 0:
                break
            remaining = min(last + gap - now, until_ceiling)
            if remaining <= 0:
                # the gap is over, but the rest of what somebody is saying is not
                if not self._held(items):
                    break
                remaining = min(HOLD_POLL_S, until_ceiling)
            try:
                arrived, perception = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                continue
            items.append(perception)
            last = max(last, arrived)
            if window is None:
                gap = min(gap, self._gap([perception]))

        items.sort(key=lambda p: p.ts)
        return items

    def _held(self, items: List[Perception]) -> bool:
        for hold in self.holds:
            try:
                if hold(items):
                    return True
            except Exception as e:
                # a broken hold must cost the wait, never the batch
                logger.debug(f"a batch hold failed: {e}")
        return False

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
                arrived, first = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return [self._idle()]

            items = await self.settle([first], last=arrived)
            if all(p.is_noise for p in items):
                continue
            return items

    @staticmethod
    def _idle() -> Perception:
        return Perception(kind=PerceptionKind.IDLE, surface="idle",
                          content="(nothing is happening)", salience=0.1)
