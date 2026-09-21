"""Everything the bus carries reaches the durable log.

The stream is the truth. A perception is written down as soon as it leaves the
bus — before the attention gate, before the model, before anything decides it
was worth a turn — because what she is asked about tomorrow is what happened,
not what she chose to answer. Only two things are left out on purpose: the
synthetic idle tick, and the texture a surface has already marked as noise.
"""

import asyncio

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
    settle,
    speaks,
    stays_silent,
)

SESSION = "session_now"


class Config:
    def __init__(self, **consciousness):
        self.consciousness = {
            "enabled": True, "idle_after": 3600.0, "window": 0.0,
            "burst_steps": 3, "correlation_timeout": 5.0,
        }
        self.consciousness.update(consciousness)
        self.attention = {"enabled": True, "trigger_words": ["bea"]}
        self.skills = {}


def build(llm=None, memory=None):
    config = Config()
    bus = PerceptionBus(window=0.0)
    memory = memory or MemoryStore(":memory:")
    mind = Consciousness(
        config=config, llm=llm or FakeLLMClient([stays_silent()]), bus=bus,
        expression=FakeExpression(), surfaces=SkillRegistry(),
        history_manager=FakeHistory(SESSION), event_manager=RecordingEvents(),
        soul_getter=lambda: "you are bea", operating_getter=lambda: "speak to talk",
        memory=memory, profiler=None, attention=Attention(config),
    )
    return mind, bus, memory


async def one_turn(mind, timeout: float = 2.0) -> None:
    mind.alive = True
    task = asyncio.create_task(mind.run())
    deadline = asyncio.get_event_loop().time() + timeout
    while not mind.llm.calls and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.05)
    mind.alive = False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await settle()


async def only_drain(mind, ticks: int = 20) -> None:
    """Lets the loop take the bus without waiting for a model call."""
    mind.alive = True
    task = asyncio.create_task(mind.run())
    for _ in range(ticks):
        await asyncio.sleep(0.005)
    mind.alive = False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await settle()


def rows(memory):
    return memory.db.query("SELECT * FROM messages ORDER BY id")


def marco() -> Perception:
    return Perception(
        PerceptionKind.CHAT, "telegram", "[marco] bea ricordi la pizza?", salience=0.9,
        meta={"channel_id": "55"},
        author=Author(platform="telegram", native_id="7", display_name="marco"),
    )


def died() -> Perception:
    return Perception(PerceptionKind.GAME, "game:mc",
                      "You died to a Skeleton at -120 64 33", salience=0.9)


# --- nothing that happened is dropped ----------------------------------------


async def test_a_game_event_with_nobody_behind_it_is_written_down():
    mind, bus, memory = build()
    bus.put(died())
    await one_turn(mind)

    world = [r for r in rows(memory) if r["role"] == "world"]
    assert len(world) == 1
    assert world[0]["content"] == "You died to a Skeleton at -120 64 33"
    assert world[0]["kind"] == "game"
    assert world[0]["surface"] == "game:mc"


async def test_someone_talking_keeps_their_identity():
    mind, bus, memory = build()
    bus.put(marco())
    await one_turn(mind)

    said = [r for r in rows(memory) if r["role"] == "user"]
    assert len(said) == 1
    assert said[0]["author_identity"] == "telegram:7"
    assert said[0]["conversation_key"] == "telegram:55"
    assert said[0]["kind"] == "chat"


async def test_the_stream_is_tagged_with_the_session_it_belongs_to():
    mind, bus, memory = build()
    bus.put(marco())
    await one_turn(mind)

    assert {r["session_id"] for r in rows(memory)} == {SESSION}


async def test_the_idle_tick_is_not_a_memory():
    mind, bus, memory = build()
    bus.put(Perception(PerceptionKind.IDLE, "idle", "(nothing is happening)"))
    await only_drain(mind)

    assert rows(memory) == []


async def test_texture_marked_as_noise_is_not_a_memory():
    mind, bus, memory = build()
    bus.put(Perception(PerceptionKind.GAME, "game:mc", "hp=20 food=18",
                       meta={"noise": True}))
    await only_drain(mind)

    assert rows(memory) == []


async def test_what_she_says_out_loud_is_written_down():
    mind, bus, memory = build(FakeLLMClient([speaks("certo che me la ricordo")]))
    bus.put(marco())
    await one_turn(mind)

    hers = [r for r in rows(memory) if r["role"] == "bea"]
    assert len(hers) == 1
    assert hers[0]["content"] == "certo che me la ricordo"


async def test_a_perception_is_written_down_once():
    mind, bus, memory = build()
    bus.put(marco())
    await one_turn(mind)

    assert len([r for r in rows(memory) if r["role"] == "user"]) == 1


# --- asleep is not absent -----------------------------------------------------


async def test_what_arrives_while_she_sleeps_is_still_written_down():
    mind, bus, memory = build()
    mind.sleeping = True
    bus.put(marco())
    await only_drain(mind)

    assert [r["content"] for r in rows(memory)] == ["[marco] bea ricordi la pizza?"]


async def test_what_arrives_while_she_sleeps_does_not_enter_her_context():
    mind, bus, memory = build()
    mind.sleeping = True
    bus.put(marco())
    await only_drain(mind)

    assert mind.sliding_window.entry_count() == 0


# --- reading it back ----------------------------------------------------------


async def test_the_session_stream_comes_back_in_order():
    mind, bus, memory = build(FakeLLMClient([speaks("si, la pizza")]))
    bus.put(marco())
    await one_turn(mind)

    stream = memory.conversations.stream(SESSION)
    assert [r["role"] for r in stream] == ["user", "bea"]
