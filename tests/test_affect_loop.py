"""Does a mood survive the loop, and does it reach the next prompt?

The pieces are tested on their own. What this pins is the path between them:
the batch that provoked a line has to still be in scope when `speak` runs, or
the person who caused it is lost and the whole thing blames nobody.
"""

import asyncio
import random

import pytest

from src.core.affect.state import AffectState
from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.memory.store import MemoryStore
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import SkillRegistry
from tests.fakes import (
    FakeExpression,
    FakeHistory,
    FakeLLMClient,
    RecordingEvents,
    speaks,
)


class Config:
    def __init__(self):
        self.consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                              "burst_steps": 3, "history_limit": 30,
                              "correlation_timeout": 5.0}
        # quiet hours off: whether this suite passes must not depend on the
        # hour it is run at
        self.attention = {"enabled": True, "trigger_words": ["bea"],
                          "cooldown_seconds": 0, "quiet_hours": [0, 0]}
        self.affect = {"enabled": True, "half_life_minutes": 25,
                       "person_half_life_hours": 60, "memory_ttl_hours": 6}
        self.skills = {}


@pytest.fixture
def store():
    s = MemoryStore(":memory:")
    yield s
    s.close()


class Mind:
    """The real loop, with fakes at every edge."""

    def __init__(self, store, script=None, affect=True):
        config = Config()
        rng = random.Random()
        rng.uniform = lambda a, b: 0.0
        self.llm = FakeLLMClient(script or [])
        self.consciousness = Consciousness(
            config=config, llm=self.llm, bus=PerceptionBus(window=0.0),
            expression=FakeExpression(), surfaces=SkillRegistry(),
            history_manager=FakeHistory(), event_manager=RecordingEvents(),
            soul_getter=lambda: "soul", operating_getter=lambda: "rules",
            attention=Attention(config, rng=rng),
            affect=AffectState(config, store, events=RecordingEvents()) if affect else None,
        )
        self.consciousness.context = [self.consciousness._system_message([])]

    async def hears(self, *perceptions, timeout: float = 1.0):
        """Puts them on the bus and lets the loop chew through them."""
        mind = self.consciousness
        mind.alive = True
        task = asyncio.create_task(mind.run())
        for p in perceptions:
            mind.bus.put(p)

        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while mind.bus._queue.qsize() and loop.time() < deadline:
            await asyncio.sleep(0.005)
        await asyncio.sleep(0.02)

        mind.alive = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def said(text="bea sei una noia", name="marco", native="1") -> Perception:
    return Perception(
        kind=PerceptionKind.CHAT, surface="discord:text", content=f"[{name}] {text}",
        author=Author(platform="discord", native_id=native, display_name=name),
    )


def regular(store, identity="discord:1", name="marco"):
    for session in ("a", "b", "c"):
        store.roster.record(identity=identity, display_name=name,
                            platform="discord", session_id=session)
    entry = store.roster.get(identity)
    card = store.people.create_from_entry(entry, reason="a regular")
    store.roster.set_promoted(identity, card.person_id)
    return card


# --- through the loop -------------------------------------------------------


async def test_a_mood_builds_up_over_a_couple_of_turns(store):
    mind = Mind(store, [speaks("ma sta zitto", mood="angry")] * 3)
    for _ in range(3):
        await mind.hears(said())

    assert mind.consciousness.affect.current.valence < 0
    assert mind.consciousness.affect.render() != ""


async def test_the_mood_is_in_the_prompt_of_the_next_turn(store):
    mind = Mind(store, [speaks("ma sta zitto", mood="angry")] * 4)
    for _ in range(4):
        await mind.hears(said())

    assert "[HOW YOU FEEL]" in mind.llm.last_system_prompt


async def test_a_calm_mind_says_nothing_about_how_it_feels(store):
    mind = Mind(store, [speaks("ciao", mood="neutral")] * 3)
    for _ in range(3):
        await mind.hears(said())

    assert "[HOW YOU FEEL]" not in mind.llm.last_system_prompt


async def test_the_person_who_provoked_the_line_is_the_one_blamed(store):
    card = regular(store)
    mind = Mind(store, [speaks("ma sta zitto", mood="angry")])
    await mind.hears(said("bea il tuo stream fa schifo"))

    assert store.people.get(card.person_id).warmth < 0
    assert "marco" in store.hot.render()
    assert "il tuo stream fa schifo" in store.hot.render()


async def test_a_line_nobody_provoked_blames_nobody(store):
    card = regular(store)
    mind = Mind(store, [speaks("che palle", mood="angry")])
    await mind.hears(Perception(PerceptionKind.IDLE, "idle", "(nothing is happening)"))

    assert mind.consciousness.affect.current.valence < 0
    assert store.people.get(card.person_id).warmth == 0.0


async def test_a_busy_room_is_nobody_s_fault(store):
    card = regular(store)
    mind = Mind(store, [speaks("ma sta zitto", mood="angry")])
    await mind.hears(said("bea sei noiosa"), said("bea concordo", name="lucia", native="2"))

    assert store.people.get(card.person_id).warmth == 0.0


async def test_switching_it_off_leaves_the_prompt_exactly_as_it_was(store):
    mind = Mind(store, [speaks("ma sta zitto", mood="angry")] * 4)
    mind.consciousness.affect.config.affect["enabled"] = False
    for _ in range(4):
        await mind.hears(said())

    assert "[HOW YOU FEEL]" not in mind.llm.last_system_prompt
    assert store.hot.active() == []


async def test_a_mind_with_no_affect_at_all_still_speaks(store):
    """The whole thing is optional: nothing may depend on it being wired."""
    mind = Mind(store, [speaks("ciao")], affect=False)
    await mind.hears(said())

    assert mind.consciousness.expression.spoken == [("neutral", "ciao", "local")]


async def test_a_line_is_never_amplified_by_its_own_mood(store):
    """The voice is handed how she felt when she decided, not after.

    Read after, the mood of the line would count twice — once as the line's own
    colour, again as the standing mood amplifying it — and the first sharp
    remark would sound nearly like twenty minutes of being furious.
    """
    mind = Mind(store, [speaks("ma sta zitto", mood="angry")])
    await mind.hears(said())

    assert [f.strength for f in mind.consciousness.expression.felt] == [0.0]
    assert mind.consciousness.affect.current.strength > 0.0


async def test_the_second_line_carries_what_the_first_one_did(store):
    mind = Mind(store, [speaks("ma sta zitto", mood="angry")] * 2)
    for _ in range(2):
        await mind.hears(said())

    first, second = mind.consciousness.expression.felt
    assert first.strength == 0.0
    assert second.strength > 0.0
