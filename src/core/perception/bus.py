import asyncio
import time
from typing import List, Optional

from src.core.perception.types import Perception, PerceptionKind
from src.utils.logger import get_logger

logger = get_logger("bea.perception.bus")


class PerceptionBus:
    """The single sensory channel feeding the one consciousness.

    Every surface (chat, voice, game, future twitch/telegram) pushes `Perception`
    objects here. The consciousness loop drains them. This replaces the ad-hoc
    per-channel buffering (interaction_buffer, pending_transcripts, flush timers).
    """

    def __init__(self, window: float = 0.3):
        self.window = window
        self._queue: "asyncio.Queue[Perception]" = asyncio.Queue()

    def put(self, perception: Perception) -> None:
        """Thread/async-safe-ish enqueue (call from the running loop)."""
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
        """Waits for at least one perception, then aggregates within `window`.

        Coalesces a short burst (e.g. several speakers at once) into one batch so
        the consciousness reasons over them together instead of one at a time.
        """
        window = self.window if window is None else window
        first = await self._queue.get()
        items = [first]

        deadline = time.time() + window
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                items.append(await asyncio.wait_for(self._queue.get(), timeout=remaining))
            except asyncio.TimeoutError:
                break

        items.sort(key=lambda p: p.ts)
        return items

    async def wait_or_idle(self, idle_after: float) -> List[Perception]:
        """Drains perceptions; if `idle_after` seconds pass with none, emits an IDLE.

        This replaces the monologue idle timer: 'nothing happened' becomes a
        first-class perception the consciousness can react to (start a monologue).
        """
        try:
            first = await asyncio.wait_for(self._queue.get(), timeout=idle_after)
        except asyncio.TimeoutError:
            return [Perception(kind=PerceptionKind.IDLE, surface="idle", content="(nothing is happening)", salience=0.1)]

        items = [first]
        items.extend(self.drain_nowait())
        items.sort(key=lambda p: p.ts)
        return items
