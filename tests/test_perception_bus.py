"""The bus can be fed from any thread without losing the reader's wake-up."""

import asyncio
import threading
import time

from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Perception, PerceptionKind


def _chat(text: str) -> Perception:
    return Perception(PerceptionKind.CHAT, "chat:ui", text)


async def test_a_perception_put_from_a_worker_thread_wakes_the_drain():
    """A plain thread, not `to_thread`: finishing that wakes the loop by itself
    and would hide a put that never did."""
    bus = PerceptionBus(window=0.0)
    draining = asyncio.create_task(bus.drain())
    # let the drain start waiting, so it owns the loop the put must land on
    await asyncio.sleep(0)

    def later() -> None:
        # long enough that the loop is asleep in its selector when this lands
        time.sleep(0.1)
        bus.put(_chat("from a thread"))

    started = time.monotonic()
    threading.Thread(target=later).start()
    batch = await asyncio.wait_for(draining, timeout=2.0)

    assert [p.content for p in batch] == ["from a thread"]
    assert time.monotonic() - started < 1.0


async def test_a_perception_put_on_the_loop_is_queued_directly():
    bus = PerceptionBus(window=0.0)
    bus.put(_chat("on the loop"))

    batch = await asyncio.wait_for(bus.drain(), timeout=1.0)
    assert [p.content for p in batch] == ["on the loop"]
