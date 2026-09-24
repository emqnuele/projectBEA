"""A turn that dies says what killed it, and the loop lives on.

A timeout's message is the empty string, so the log used to read
"Consciousness loop error: " and nothing else, and the dashboard said nothing
at all: from the outside she had simply gone quiet.
"""

import asyncio

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.events import EventCategory
from src.core.memory.store import MemoryStore
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import SkillRegistry
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents, speaks


class Config:
    def __init__(self):
        self.consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                              "burst_steps": 3, "correlation_timeout": 5.0}
        self.attention = {"enabled": True, "trigger_words": ["bea"]}
        self.skills = {}


def ema(text: str) -> Perception:
    return Perception(PerceptionKind.CHAT, "chat:ui", f"[ema] {text}",
                      author=Author(platform="ui", native_id="owner", display_name="ema",
                                    is_owner=True))


class FailsOnce(FakeLLMClient):
    async def complete(self, messages, tools=None, response_format=None):
        if not self.calls:
            self.calls.append(messages)
            raise asyncio.TimeoutError()
        return await super().complete(messages, tools, response_format)


async def test_a_timed_out_turn_is_named_and_the_next_one_is_answered():
    config = Config()
    bus = PerceptionBus(window=0.0)
    events = RecordingEvents()
    llm = FailsOnce([speaks("eccomi")])
    mind = Consciousness(
        config=config, llm=llm, bus=bus, expression=FakeExpression(), surfaces=SkillRegistry(),
        history_manager=FakeHistory("s"), event_manager=events,
        soul_getter=lambda: "you are bea", operating_getter=lambda: "speak to talk",
        memory=MemoryStore(":memory:"), profiler=None, attention=Attention(config),
    )
    bus.put(ema("ao fetcha quel sito"))
    mind.alive = True
    loop = asyncio.create_task(mind.run())
    try:
        deadline = asyncio.get_running_loop().time() + 3
        while not events.of_category(EventCategory.ERROR) \
                and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        bus.put(ema("quindi che ne pensi"))
        while len(llm.calls) < 2 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
    finally:
        mind.alive = False
        loop.cancel()
        await asyncio.gather(loop, return_exceptions=True)

    errors = [e[2] for e in events.of_category(EventCategory.ERROR)]
    assert any("TimeoutError" in message for message in errors)
    assert len(llm.calls) == 2, "the loop did not survive the failed turn"
