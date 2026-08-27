"""End-to-end: the gate inside the real loop.

With the game running and nobody talking she must stop deliberating; a message
that names her must always get through.
"""

import asyncio
import random
from datetime import datetime

import pytest

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import SkillRegistry
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents, speaks


class Config:
    def __init__(self, **attention):
        self.consciousness = {
            "enabled": True, "idle_after": 3600.0, "window": 0.0,
            "burst_steps": 3, "history_limit": 30, "correlation_timeout": 5.0,
        }
        self.attention = {
            "enabled": True, "cooldown_seconds": 20, "interject_threshold": 0.45,
            "quiet_hours": [3, 9], "trigger_words": ["bea"], "hot_names": [],
            "self_ids": [], "digest_max_lines": 8,
        }
        self.attention.update(attention)
        self.skills = {}


# noon: quiet hours are wall-clock, so an unpinned clock made these tests fail
# between 03:00 and 09:00 and pass the rest of the day
NOON = datetime(2026, 6, 15, 12, 0).timestamp()


def build(llm, **attention):
    config = Config(**attention)
    bus = PerceptionBus(window=0.0)
    rng = random.Random()
    rng.uniform = lambda a, b: 0.0
    events = RecordingEvents()
    mind = Consciousness(
        config=config, llm=llm, bus=bus, expression=FakeExpression(),
        surfaces=SkillRegistry(), history_manager=FakeHistory(), event_manager=events,
        soul_getter=lambda: "you are bea", operating_getter=lambda: "call speak to talk",
        attention=Attention(config, rng=rng, clock=lambda: NOON),
    )
    mind.context = [mind._system_message([])]
    return mind, bus, events


def game_noise() -> Perception:
    return Perception(PerceptionKind.GAME, "game:mc", "(still playing)",
                      salience=0.15, meta={"noise": True})


def chat(text: str, name: str = "marco") -> Perception:
    return Perception(
        PerceptionKind.CHAT, "discord:text", f"[{name}] {text}", salience=0.5,
        author=Author(platform="discord", native_id="4711", display_name=name),
    )


async def run_until_quiet(mind, bus, timeout: float = 1.0) -> None:
    """Runs the loop until the bus is drained and nothing more is happening."""
    mind.alive = True
    task = asyncio.create_task(mind.run())
    deadline = asyncio.get_event_loop().time() + timeout
    while bus._queue.qsize() and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.02)
    mind.alive = False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_a_silent_game_session_costs_nothing():
    """60 heartbeats — ten minutes of play with nobody talking — and zero calls."""
    llm = FakeLLMClient()
    mind, bus, _ = build(llm)
    for _ in range(60):
        bus.put(game_noise())

    await run_until_quiet(mind, bus)
    assert llm.call_count == 0


async def test_being_named_always_gets_through():
    llm = FakeLLMClient([speaks("che vuoi")])
    mind, bus, _ = build(llm)
    bus.put(chat("ciao bea"))

    await run_until_quiet(mind, bus)
    assert llm.call_count == 1
    assert mind.expression.spoken == [("normal", "che vuoi", "local")]


async def test_a_named_message_buried_in_game_noise_still_lands():
    llm = FakeLLMClient([speaks("eccomi")])
    mind, bus, _ = build(llm)
    for _ in range(30):
        bus.put(game_noise())
    bus.put(chat("bea guarda qui"))
    for _ in range(30):
        bus.put(game_noise())

    await run_until_quiet(mind, bus)
    assert llm.call_count == 1


async def test_small_talk_in_a_quiet_room_never_reaches_the_model():
    llm = FakeLLMClient()
    mind, bus, _ = build(llm)
    for i in range(2):
        bus.put(chat(f"tanto per parlare {i}"))

    await run_until_quiet(mind, bus)
    assert llm.call_count == 0


async def test_she_chimes_into_a_lively_room_then_settles_down():
    """Presence, not commentary: she joins a busy conversation once, and having
    spoken she goes back to listening unless something else pulls her in."""
    llm = FakeLLMClient([speaks("comunque")])
    mind, bus, _ = build(llm)

    for i in range(6):
        bus.put(chat(f"messaggio {i}"))
        await run_until_quiet(mind, bus)
    assert llm.call_count == 1

    for i in range(6):
        bus.put(chat(f"altro messaggio {i}"))
        await run_until_quiet(mind, bus)
    assert llm.call_count == 1


async def test_what_she_missed_shows_up_in_her_next_context():
    llm = FakeLLMClient([speaks("ok")])
    mind, bus, _ = build(llm)
    bus.put(chat("una cosa qualunque"))
    await run_until_quiet(mind, bus)

    bus.put(chat("bea?"))
    await run_until_quiet(mind, bus)

    assert "WHILE YOU WERE BUSY" in llm.last_system_prompt
    assert "una cosa qualunque" in llm.last_system_prompt


async def test_the_ignored_message_is_not_replayed_forever():
    llm = FakeLLMClient([speaks("uno"), speaks("due")])
    mind, bus, _ = build(llm)
    bus.put(chat("roba di sfondo"))
    await run_until_quiet(mind, bus)

    bus.put(chat("bea?"))
    await run_until_quiet(mind, bus)
    bus.put(chat("bea??"))
    await run_until_quiet(mind, bus)

    assert "roba di sfondo" not in llm.last_system_prompt


async def test_an_awaited_caller_is_freed_even_when_ignored():
    """An HTTP caller must never hang because the gate filtered its perception."""
    llm = FakeLLMClient()
    mind, bus, _ = build(llm)
    cid, future = mind.register_correlation("local")

    p = chat("niente di che")
    p.meta["correlation_id"] = cid
    bus.put(p)

    await run_until_quiet(mind, bus)
    assert future.done()
    assert future.result() == {"mood": "normal", "message": ""}
    assert llm.call_count == 0


async def test_speaking_starts_the_cooldown():
    llm = FakeLLMClient([speaks("eccomi")])
    mind, bus, _ = build(llm)
    bus.put(chat("bea!"))
    await run_until_quiet(mind, bus)
    assert mind.attention.seconds_since_spoke() is not None
    assert mind.attention.seconds_since_spoke() < 5.0


async def test_every_decision_is_published_for_the_dashboard():
    llm = FakeLLMClient([speaks("ok")])
    mind, bus, events = build(llm)
    verdicts = []
    mind.attention._on_verdict = lambda p, v: verdicts.append(v)

    bus.put(chat("ciao bea"))
    await run_until_quiet(mind, bus)

    assert [v.reason for v in verdicts] == ["addressed:name"]


@pytest.mark.parametrize("enabled", [True, False])
async def test_the_gate_can_be_switched_off(enabled):
    llm = FakeLLMClient([speaks("a"), speaks("b"), speaks("c")])
    mind, bus, _ = build(llm, enabled=enabled)
    bus.put(chat("una cosa noiosa"))

    await run_until_quiet(mind, bus)
    assert llm.call_count == (0 if enabled else 1)


# --- what a turn cost --------------------------------------------------------


async def test_the_cost_of_a_turn_is_published():
    """The whole point of the gate is spending fewer of these; you cannot tune
    what you cannot see."""
    from src.core.agent.types import Usage

    reply = speaks("eccomi")
    reply.usage = Usage(prompt_tokens=1200, completion_tokens=40)
    llm = FakeLLMClient([reply])
    mind, bus, events = build(llm)
    bus.put(chat("ciao bea"))

    await run_until_quiet(mind, bus)
    costs = [e for e in events.events if e[1] == "cost"]
    assert len(costs) == 1
    assert costs[0][3]["tokens"] == 1240
    assert costs[0][3]["steps"] == 1


async def test_the_session_total_accumulates():
    from src.core.agent.types import Usage

    replies = []
    for _ in range(2):
        r = speaks("ok")
        r.usage = Usage(prompt_tokens=100, completion_tokens=10)
        replies.append(r)

    llm = FakeLLMClient(replies)
    mind, bus, _ = build(llm)
    bus.put(chat("bea?"))
    await run_until_quiet(mind, bus)
    bus.put(chat("bea??"))
    await run_until_quiet(mind, bus)

    assert mind.total_tokens == 220
    assert mind.total_calls == 2


async def test_an_ignored_batch_costs_nothing_and_reports_nothing():
    llm = FakeLLMClient()
    mind, bus, events = build(llm)
    bus.put(chat("niente di che"))

    await run_until_quiet(mind, bus)
    assert [e for e in events.events if e[1] == "cost"] == []
    assert mind.total_tokens == 0
