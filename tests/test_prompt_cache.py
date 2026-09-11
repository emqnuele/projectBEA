"""The prompt is two halves, and the split is what makes caching possible.

Providers charge less for the longest prefix of a request they have seen before.
Her soul and her operating manual are thousands of tokens that never change
inside a session — but one volatile line above them (the date, a retrieved
memory, how she happens to feel) means there is no repeated prefix at all, and
every turn pays full price. Nothing about the turn looks any different when that
happens, which is exactly why it needs a test.
"""

import asyncio
import random
from datetime import datetime

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.events import EventCategory
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import Skill, SkillRegistry
from src.modules.llm.openai_compat import _usage
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents, speaks

NOON = datetime(2026, 6, 15, 12, 0).timestamp()


class Config:
    def __init__(self):
        self.consciousness = {
            "enabled": True, "idle_after": 3600.0, "window": 0.0,
            "burst_steps": 3, "history_limit": 30, "correlation_timeout": 5.0,
        }
        self.attention = {
            "enabled": True, "cooldown_seconds": 0, "interject_threshold": 0.45,
            "quiet_hours": [3, 9], "trigger_words": ["bea"], "hot_names": [],
            "self_ids": [], "digest_max_lines": 8,
        }
        self.skills = {}


class Recalling(Skill):
    """A skill whose contribution is different every turn, like real retrieval."""

    name = "memory"

    def __init__(self):
        self.active = True
        self.turns = 0

    def context_for(self, batch):
        self.turns += 1
        return f"[WHAT YOU REMEMBER]\nrecollection number {self.turns}"

    def live_state(self):
        return None

    @property
    def context_section(self):
        return "[HOW MEMORY WORKS]\nyou remember things"


def build(llm, skills=()):
    config = Config()
    bus = PerceptionBus(window=0.0)
    rng = random.Random()
    rng.uniform = lambda a, b: 0.0
    registry = SkillRegistry()
    for skill in skills:
        registry.register(skill)
    events = RecordingEvents()
    mind = Consciousness(
        config=config, llm=llm, bus=bus, expression=FakeExpression(),
        surfaces=registry, history_manager=FakeHistory(), event_manager=events,
        soul_getter=lambda: "you are bea", operating_getter=lambda: "call speak to talk",
        attention=Attention(config, rng=rng, clock=lambda: NOON),
    )
    mind.context = [mind._system_message()]
    return mind, bus, events


def chat(text: str) -> Perception:
    return Perception(
        PerceptionKind.CHAT, "discord:text", f"[marco] {text}", salience=0.5,
        author=Author(platform="discord", native_id="4711", display_name="marco"),
    )


async def run_turns(mind, bus, lines) -> None:
    mind.alive = True
    task = asyncio.create_task(mind.run())
    try:
        for line in lines:
            bus.put(chat(line))
            for _ in range(40):
                await asyncio.sleep(0.005)
                if not bus._queue.qsize():
                    break
        await asyncio.sleep(0.02)
    finally:
        mind.alive = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# --- the split ---------------------------------------------------------------


async def test_the_stable_half_is_byte_identical_between_two_turns():
    """The whole point: without this there is no prefix left to cache."""
    llm = FakeLLMClient([speaks("uno"), speaks("due")])
    mind, bus, _ = build(llm, skills=[Recalling()])

    await run_turns(mind, bus, ["ciao bea", "ancora tu bea"])

    assert llm.call_count == 2
    assert llm.calls[0][0] == llm.calls[1][0]


def test_the_date_is_not_in_the_stable_half():
    """It sat at the very top and turned the cache off once a day, silently."""
    mind, _, _ = build(FakeLLMClient())
    assert "CURRENT DATE" not in mind._system_message()["content"]
    assert "CURRENT DATE" in mind._briefing([])["content"]


def test_a_retrieval_belongs_to_the_briefing_and_not_to_the_prompt():
    mind, _, _ = build(FakeLLMClient(), skills=[Recalling()])
    stable = mind._system_message()["content"]

    assert "[HOW MEMORY WORKS]" in stable, "a static rule is stable"
    assert "recollection number" not in stable, "a per-turn retrieval is not"


# --- the briefing is only ever about now -------------------------------------


async def test_what_she_was_told_this_turn_is_gone_by_the_next_one():
    """A memory retrieved for one question must not answer the next."""
    llm = FakeLLMClient([speaks("uno"), speaks("due")])
    mind, bus, _ = build(llm, skills=[Recalling()])

    await run_turns(mind, bus, ["ciao bea", "ancora tu bea"])

    second = "\n".join(m.get("content", "") for m in llm.calls[1])
    assert "recollection number 2" in second
    assert "recollection number 1" not in second


async def test_the_briefing_sits_directly_above_what_it_describes():
    llm = FakeLLMClient([speaks("eccomi")])
    mind, bus, _ = build(llm, skills=[Recalling()])

    await run_turns(mind, bus, ["ciao bea"])

    roles = [m.get("role") for m in llm.calls[0]]
    contents = [m.get("content", "") for m in llm.calls[0]]
    assert roles[0] == "system"
    assert "[PERCEPTIONS]" in contents[-1]
    assert "CURRENT DATE" in contents[-2], "the briefing is the message before the frame"


async def test_the_context_does_not_grow_a_briefing_per_turn():
    llm = FakeLLMClient([speaks("uno"), speaks("due"), speaks("tre")])
    mind, bus, _ = build(llm, skills=[Recalling()])

    await run_turns(mind, bus, ["ciao bea", "ancora bea", "e ancora bea"])

    briefings = [m for m in mind.context if "CURRENT DATE" in m.get("content", "")]
    assert briefings == []


async def test_a_turn_that_raises_does_not_leave_its_briefing_behind():
    llm = FakeLLMClient()
    llm.fail_with = RuntimeError("the provider fell over")
    mind, bus, _ = build(llm, skills=[Recalling()])

    await run_turns(mind, bus, ["ciao bea"])

    assert [m for m in mind.context if "CURRENT DATE" in m.get("content", "")] == []


# --- reporting ---------------------------------------------------------------


async def test_what_the_cache_covered_reaches_the_dashboard():
    """A cache that stops working is invisible unless the number is published."""
    llm = FakeLLMClient([speaks("eccomi")])
    mind, bus, events = build(llm)
    llm.script[0].usage.prompt_tokens = 1000
    llm.script[0].usage.cached_tokens = 900

    await run_turns(mind, bus, ["ciao bea"])

    cost = [e for e in events.of_category(EventCategory.SYSTEM) if e[1] == "cost"]
    assert cost, "a turn always reports what it cost"
    assert cost[-1][3]["cached_tokens"] == 900
    assert "90% cached" in cost[-1][2]


# --- reading it off a provider -----------------------------------------------


def usage_block(**fields):
    return type("Usage", (), fields)()


def test_the_cached_figure_is_read_from_the_shape_openai_sends():
    raw = usage_block(prompt_tokens=1200, completion_tokens=40,
                      prompt_tokens_details=usage_block(cached_tokens=1024))
    assert _usage(raw).cached_tokens == 1024


def test_the_cached_figure_is_read_from_the_shape_openrouter_sends():
    raw = usage_block(prompt_tokens=1200, completion_tokens=40, cached_tokens=1024)
    assert _usage(raw).cached_tokens == 1024


def test_a_provider_that_reports_nothing_costs_nothing_to_read():
    assert _usage(None).cached_tokens == 0
    assert _usage(usage_block(prompt_tokens=10, completion_tokens=2)).cached_tokens == 0
