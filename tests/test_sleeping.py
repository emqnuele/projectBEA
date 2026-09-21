"""Falling asleep and waking up have exactly one owner.

`go_to_sleep` used to put her to sleep itself and then start the dream as a
detached task it kept no reference to: the event loop holds only a weak one,
so a dream could be collected halfway through. Worse, the task it queued
while a dream was already running found `_dreaming` back to False by the time
it was scheduled, and ran a whole second consolidation on the spot.
"""

import asyncio
from types import SimpleNamespace

import pytest

from src.core.memory.store import MemoryStore
from src.core.skills.dream.surface import DreamSkill


class Mind:
    """The two calls the dream skill is allowed to make on the consciousness."""

    def __init__(self):
        self.sleeping = False
        self.events = []

    def sleep(self, reason=""):
        self.sleeping = True
        self.events.append(f"sleep({reason})")

    def wake(self):
        self.sleeping = False
        self.events.append("wake")


class Config:
    def __init__(self, **dream):
        self.skills = {"dream": {"enabled": True, **dream}}
        self.language = ""


@pytest.fixture
def memory():
    store = MemoryStore(":memory:")
    yield store
    store.close()


def _skill(memory, mind, dreamer=None) -> DreamSkill:
    context = SimpleNamespace(brain=None, memory=memory, consciousness=mind,
                              skill_registry=None, history_manager=None,
                              model_for=None)
    skill = DreamSkill(Config(), bus=None, expression=None, context=context)
    skill.initialize()
    skill.active = True
    skill.dreamer = dreamer
    return skill


class SlowDreamer:
    """A dream long enough for a second request to land in the middle of it."""

    def __init__(self):
        self.runs = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self):
        self.runs += 1
        self.started.set()
        await self.release.wait()
        return {"ok": True}


async def test_asking_to_sleep_mid_dream_queues_nothing(memory):
    mind = Mind()
    dreamer = SlowDreamer()
    skill = _skill(memory, mind, dreamer)

    first = asyncio.create_task(skill.run_dream())
    await dreamer.started.wait()

    await skill._tool_go_to_sleep("tired")
    assert skill._dream_task is None

    dreamer.release.set()
    await first
    await asyncio.sleep(0)

    assert dreamer.runs == 1
    assert mind.sleeping is False


async def test_going_to_sleep_keeps_hold_of_the_dream(memory):
    mind = Mind()
    dreamer = SlowDreamer()
    skill = _skill(memory, mind, dreamer)

    await skill._tool_go_to_sleep("tired")
    await dreamer.started.wait()

    assert mind.sleeping is True
    assert skill._dream_task is not None and not skill._dream_task.done()

    dreamer.release.set()
    await skill._dream_task
    assert mind.sleeping is False


async def test_a_dream_that_raises_still_wakes_her(memory):
    class Exploding:
        async def run(self):
            raise RuntimeError("the background model is down")

    mind = Mind()
    skill = _skill(memory, mind, Exploding())

    result = await skill.run_dream()

    assert result["ok"] is False
    assert mind.sleeping is False


async def test_the_night_is_remembered_across_a_restart(memory):
    """A restart at 4:30 must not dream the same night twice."""
    mind = Mind()
    skill = _skill(memory, mind, SlowDreamer())

    assert skill._dreamed_tonight() is False
    skill._mark_dreamed_tonight()

    reborn = _skill(memory, Mind(), SlowDreamer())
    assert reborn._dreamed_tonight() is True
