"""one publisher, many bounded queues, safe to publish to from any thread."""

import asyncio
import contextlib
import threading
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger("bea.fanout")


def offer(queue: "asyncio.Queue[Any]", payload: Any) -> None:
    """Puts `payload` on a queue that may be full, making room if it is.

    Used to end a stream: a full queue would otherwise drop the sentinel and
    leave the reader blocked until its keep-alive timeout instead of returning
    at once. The oldest queued item is the right one to lose — the stream is
    over anyway, and the sentinel is the only thing that still matters.
    """
    try:
        queue.put_nowait(payload)
        return
    except asyncio.QueueFull:
        pass
    with contextlib.suppress(asyncio.QueueEmpty):
        queue.get_nowait()
    with contextlib.suppress(asyncio.QueueFull):
        queue.put_nowait(payload)


def _running_loop() -> Optional[asyncio.AbstractEventLoop]:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


class Fanout:
    """a stalled reader is dropped, never waited on."""

    def __init__(self, limit: int, what: str) -> None:
        self._limit = limit
        self._what = what
        # asyncio.Queue is not thread-safe: a put must happen on the reader's loop
        self._subscribers: Dict["asyncio.Queue[Any]", Optional[asyncio.AbstractEventLoop]] = {}
        self._lock = threading.Lock()

    def subscribe(self, backlog: Optional[List[Any]] = None) -> "asyncio.Queue[Any]":
        queue: "asyncio.Queue[Any]" = asyncio.Queue(maxsize=self._limit)
        for payload in backlog or ():
            if queue.full():
                break
            queue.put_nowait(payload)
        with self._lock:
            self._subscribers[queue] = _running_loop()
        return queue

    def unsubscribe(self, queue) -> None:
        with self._lock:
            self._subscribers.pop(queue, None)

    def __len__(self) -> int:
        return len(self._subscribers)

    def publish(self, payload: Any) -> None:
        current = _running_loop()
        with self._lock:
            subscribers = list(self._subscribers.items())
        for queue, loop in subscribers:
            if loop is None or loop is current:
                self._put(queue, payload)
            elif not loop.is_closed():
                loop.call_soon_threadsafe(self._put, queue, payload)

    def _put(self, queue, payload: Any) -> None:
        if queue not in self._subscribers:
            return
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            # a reader that stopped reading must not slow down the publisher
            logger.debug(f"Dropping a stalled {self._what} subscriber.")
            self.unsubscribe(queue)

    def queues(self) -> List["asyncio.Queue[Any]"]:
        with self._lock:
            return list(self._subscribers)
