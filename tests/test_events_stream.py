"""Live event fan-out: the dashboard stops polling."""

import asyncio

from src.core.agent.types import Usage
from src.core.events import QUEUE_LIMIT, EventCategory, EventManager


def manager(**kwargs) -> EventManager:
    return EventManager(**kwargs)


def test_events_are_kept_and_returned():
    m = manager()
    m.publish(EventCategory.SYSTEM, "test", "something happened")
    assert [e["message"] for e in m.get_events()] == ["something happened"]


def test_the_ring_buffer_has_a_ceiling():
    m = manager(max_history=3)
    for i in range(10):
        m.publish(EventCategory.SYSTEM, "test", f"event {i}")
    assert len(m.events) == 3
    assert m.events[-1].message == "event 9"


async def test_a_subscriber_receives_what_happens_next():
    m = manager()
    queue = m.subscribe(backlog=0)
    m.publish(EventCategory.OUTPUT, "bea", "eccomi")
    assert (await asyncio.wait_for(queue.get(), 1.0))["message"] == "eccomi"


async def test_a_subscriber_gets_the_recent_backlog():
    """Connecting mid-session should show what just happened, not a blank screen."""
    m = manager()
    for i in range(5):
        m.publish(EventCategory.SYSTEM, "test", f"event {i}")
    queue = m.subscribe(backlog=3)
    got = [queue.get_nowait()["message"] for _ in range(3)]
    assert got == ["event 2", "event 3", "event 4"]


async def test_every_subscriber_sees_every_event():
    m = manager()
    a, b = m.subscribe(backlog=0), m.subscribe(backlog=0)
    m.publish(EventCategory.SYSTEM, "test", "broadcast")
    assert a.get_nowait()["message"] == "broadcast"
    assert b.get_nowait()["message"] == "broadcast"


async def test_unsubscribing_stops_the_feed():
    m = manager()
    queue = m.subscribe(backlog=0)
    m.unsubscribe(queue)
    m.publish(EventCategory.SYSTEM, "test", "nobody hears this")
    assert queue.empty()
    assert m.subscriber_count == 0


async def test_a_stalled_subscriber_is_dropped_not_tolerated():
    """A browser tab that stopped reading must not slow down the brain."""
    m = manager()
    m.subscribe(backlog=0)
    for i in range(QUEUE_LIMIT + 5):
        m.publish(EventCategory.SYSTEM, "test", f"event {i}")
    assert m.subscriber_count == 0


async def test_publishing_with_no_subscribers_is_fine():
    m = manager()
    m.publish(EventCategory.SYSTEM, "test", "alone")
    assert len(m.events) == 1


def test_metadata_travels_with_the_event():
    m = manager()
    m.publish(EventCategory.SYSTEM, "attention", "note", metadata={"score": 0.42})
    assert m.get_events()[0]["metadata"] == {"score": 0.42}


# --- what a turn cost -------------------------------------------------------


def test_usage_adds_up():
    total = Usage(10, 5) + Usage(3, 2)
    assert (total.prompt_tokens, total.completion_tokens, total.total) == (13, 7, 20)


def test_a_provider_that_reports_nothing_costs_zero():
    assert Usage().total == 0
