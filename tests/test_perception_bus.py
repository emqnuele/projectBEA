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


async def test_what_queued_while_she_was_busy_does_not_wait_the_gap_again():
    # she was mid-answer: the line has sat there, quiet, for longer than the gap
    bus = PerceptionBus(window=0.3)
    bus.put(_chat("arrived while she was talking"))
    await asyncio.sleep(0.4)

    started = time.monotonic()
    batch = await asyncio.wait_for(bus.drain(), timeout=2.0)

    assert [p.content for p in batch] == ["arrived while she was talking"]
    assert time.monotonic() - started < 0.1, "a quiet gap was waited out twice"


async def test_everything_that_queued_up_is_one_batch():
    bus = PerceptionBus(window=0.3)
    bus.put(_chat("hey"))
    bus.put(_chat("come stai"))
    await asyncio.sleep(0.4)

    batch = await asyncio.wait_for(bus.drain(), timeout=2.0)
    assert [p.content for p in batch] == ["hey", "come stai"]


async def test_a_line_that_arrives_inside_the_gap_still_holds_the_batch_open():
    bus = PerceptionBus(window=0.3)
    bus.put(_chat("hey"))

    async def later():
        await asyncio.sleep(0.2)
        bus.put(_chat("come stai"))

    asyncio.create_task(later())
    started = time.monotonic()
    batch = await asyncio.wait_for(bus.drain(), timeout=2.0)

    assert [p.content for p in batch] == ["hey", "come stai"]
    # closed a gap after the second line, not after the first
    assert time.monotonic() - started >= 0.45
