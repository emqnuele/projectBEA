"""One turn at a time per conversation, several conversations at once."""

import asyncio

from src.core.mind.scheduler import ConversationScheduler


def recorder():
    """A turn function that records every run and can be made slow."""
    log = []

    async def turn(first, key="k", delay=0.0):
        log.append((key, first))
        if delay:
            await asyncio.sleep(delay)

    turn.log = log
    return turn


async def test_a_lone_turn_just_runs():
    s = ConversationScheduler()
    turn = recorder()
    assert await s.submit("a", turn) is True
    assert turn.log == [("k", True)]


async def test_a_turn_knows_it_is_the_first():
    s = ConversationScheduler()
    seen = []
    await s.submit("a", lambda first: _note(seen, first))
    assert seen == [True]


async def test_sequential_turns_in_one_channel_are_all_firsts():
    s = ConversationScheduler()
    seen = []
    await s.submit("a", lambda first: _note(seen, first))
    await s.submit("a", lambda first: _note(seen, first))
    assert seen == [True, True]


async def test_messages_arriving_mid_turn_are_folded_into_one_answer():
    """Three messages in a row must not produce three replies."""
    s = ConversationScheduler()
    runs = []

    async def slow(first):
        runs.append(first)
        await asyncio.sleep(0.02)

    task = asyncio.create_task(s.submit("a", slow))
    await asyncio.sleep(0.005)
    assert await s.submit("a", slow) is False
    assert await s.submit("a", slow) is False
    await task

    # one first pass, then a single coalescing re-run covering both
    assert runs == [True, False]


async def test_coalescing_stops_at_the_cap():
    s = ConversationScheduler(max_coalesced_runs=2)
    runs = []

    async def slow(first):
        runs.append(first)
        await asyncio.sleep(0.01)
        # keep flooding while the turn is running
        await s.submit("a", slow)

    await s.submit("a", slow)
    assert len(runs) == 2


async def test_different_channels_run_in_parallel():
    s = ConversationScheduler()
    order = []

    async def slow(first):
        order.append("a-start")
        await asyncio.sleep(0.02)
        order.append("a-end")

    async def quick(first):
        order.append("b")

    task = asyncio.create_task(s.submit("a", slow))
    await asyncio.sleep(0.005)
    await s.submit("b", quick)
    await task

    # b did not wait for a to finish
    assert order == ["a-start", "b", "a-end"]


async def test_order_inside_a_channel_is_always_respected():
    s = ConversationScheduler()
    order = []

    async def make(n):
        async def turn(first):
            order.append(f"{n}-start")
            await asyncio.sleep(0.01)
            order.append(f"{n}-end")
        return turn

    await s.submit("a", await make(1))
    await s.submit("a", await make(2))
    assert order == ["1-start", "1-end", "2-start", "2-end"]


async def test_a_failing_turn_releases_the_channel():
    s = ConversationScheduler()

    async def boom(first):
        raise RuntimeError("model down")

    try:
        await s.submit("a", boom)
    except RuntimeError:
        pass
    assert s.is_running("a") is False
    # the channel is usable again
    assert await s.submit("a", lambda first: _noop()) is True


async def test_a_running_channel_is_reported():
    s = ConversationScheduler()

    async def slow(first):
        assert s.is_running("a") is True
        assert s.active_keys == ["a"]
        await asyncio.sleep(0)

    await s.submit("a", slow)
    assert s.is_running("a") is False
    assert s.active_keys == []


async def test_draining_waits_for_the_turns_in_flight():
    s = ConversationScheduler()
    done = []

    async def slow(first):
        await asyncio.sleep(0.02)
        done.append(1)

    asyncio.create_task(s.submit("a", slow))
    await asyncio.sleep(0.005)
    await s.drain(timeout=1.0)
    assert done == [1]


async def test_draining_gives_up_after_the_timeout():
    s = ConversationScheduler()

    async def forever(first):
        await asyncio.sleep(5)

    task = asyncio.create_task(s.submit("a", forever))
    await asyncio.sleep(0.005)
    await s.drain(timeout=0.05)
    task.cancel()


async def _note(bucket, first):
    bucket.append(first)


async def _noop():
    return None
