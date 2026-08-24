"""A day, not an event loop: when she starts something on her own."""

import datetime
import random
import time

import pytest

from src.core.memory.store import MemoryStore
from src.core.mind.spontaneous import SpontaneousPresence

# 14:00 local: outside quiet hours in any timezone
AFTERNOON = datetime.datetime(2026, 6, 15, 14, 0, 0).timestamp()


class Config:
    def __init__(self, **rhythm):
        self.rhythm = {
            "spontaneous_enabled": True,
            "spontaneous_probability": 1.0,   # always, unless a test says otherwise
            "spontaneous_min_silence": 3600,
            "spontaneous_min_activity": 3,
        }
        self.rhythm.update(rhythm)
        self.attention = {"quiet_hours": [3, 9]}


class FakeConversations:
    def __init__(self):
        self.opened = []

    async def turn_now(self, key, perceptions, *, first=True, initiative=False):
        self.opened.append((key, initiative))


@pytest.fixture
def setup():
    store = MemoryStore(":memory:")
    yield store, FakeConversations()
    store.close()


def presence(setup, roll=0.0, clock=None, **rhythm) -> SpontaneousPresence:
    store, conversations = setup
    rng = random.Random()
    rng.random = lambda: roll
    return SpontaneousPresence(
        config=Config(**rhythm), memory=store, conversations=conversations,
        rng=rng, clock=clock or (lambda: AFTERNOON),
    )


def chatter(store, key="discord:1", count=5, ago=60.0, now=None):
    now = now or AFTERNOON
    for i in range(count):
        store.conversations.add(conversation_key=key, role="user",
                                content=f"messaggio {i}", ts=now - ago)


# --- eligibility (pure given its inputs) -------------------------------------


def test_a_live_room_she_has_been_quiet_in_is_eligible(setup):
    p = presence(setup)
    assert p.is_eligible(hour=14, seconds_since_bea=7200, activity=5) is True


def test_she_never_starts_during_quiet_hours(setup):
    p = presence(setup)
    assert p.is_eligible(hour=4, seconds_since_bea=7200, activity=50) is False


def test_a_dead_room_is_not_worth_opening(setup):
    """Talking into a channel nobody has touched is a bot with a timer."""
    p = presence(setup)
    assert p.is_eligible(hour=14, seconds_since_bea=7200, activity=0) is False


def test_having_just_spoken_is_not_presence(setup):
    p = presence(setup)
    assert p.is_eligible(hour=14, seconds_since_bea=60, activity=10) is False


def test_never_having_spoken_there_counts_as_silence(setup):
    p = presence(setup)
    assert p.is_eligible(hour=14, seconds_since_bea=None, activity=5) is True


# --- the pass ----------------------------------------------------------------


async def test_she_opens_a_live_quiet_conversation(setup):
    store, conversations = setup
    chatter(store, count=5)

    assert await presence(setup).run_once() == 1
    assert conversations.opened == [("discord:1", True)]


async def test_she_stays_out_of_a_dead_conversation(setup):
    store, conversations = setup
    chatter(store, count=1)

    assert await presence(setup).run_once() == 0
    assert conversations.opened == []


async def test_she_does_not_follow_up_on_herself(setup):
    store, conversations = setup
    chatter(store, count=5)
    store.conversations.add(conversation_key="discord:1", role="bea", content="detto io")

    assert await presence(setup).run_once() == 0


async def test_even_when_eligible_she_usually_does_not(setup):
    """Presence is occasional. Every-time would be a scheduled post."""
    store, conversations = setup
    chatter(store, count=5)

    assert await presence(setup, roll=0.9, spontaneous_probability=0.15).run_once() == 0
    assert conversations.opened == []


async def test_the_stage_is_never_opened_this_way(setup):
    """Talking to a room she is standing in is the live loop's business."""
    store, conversations = setup
    chatter(store, key="stage", count=10)

    assert await presence(setup).run_once() == 0


async def test_a_conversation_nobody_has_touched_in_days_is_left_alone(setup):
    store, conversations = setup
    chatter(store, count=5, now=AFTERNOON - 7 * 86400, ago=0)

    assert await presence(setup).run_once() == 0


async def test_several_live_conversations_are_all_considered(setup):
    store, conversations = setup
    chatter(store, key="discord:1", count=5)
    chatter(store, key="telegram:-100", count=5)

    assert await presence(setup).run_once() == 2
    assert {key for key, _ in conversations.opened} == {"discord:1", "telegram:-100"}


async def test_switching_it_off_stops_it_entirely(setup):
    store, conversations = setup
    chatter(store, count=5)

    assert await presence(setup, spontaneous_enabled=False).run_once() == 0


async def test_nothing_recorded_means_nothing_to_open(setup):
    assert await presence(setup).run_once() == 0


async def test_a_broken_read_does_not_take_the_pass_down(setup):
    store, conversations = setup
    chatter(store, count=5)
    p = presence(setup)
    p.memory.conversations.seconds_since_bea_spoke = _boom

    assert await p.run_once() == 0


def _boom(*args, **kwargs):
    raise RuntimeError("db is gone")


# --- the real clock ----------------------------------------------------------


async def test_the_hour_comes_from_the_injected_clock(setup):
    store, conversations = setup
    chatter(store, count=5, now=time.time())
    night = datetime.datetime(2026, 6, 15, 4, 0, 0).timestamp()

    p = SpontaneousPresence(
        config=Config(), memory=store, conversations=conversations,
        rng=random.Random(), clock=lambda: night,
    )
    assert await p.run_once() == 0
