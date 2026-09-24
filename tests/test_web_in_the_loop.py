"""A slow lookup, end to end through the one loop.

She reaches for the web, says she is checking, and the turn is over — she is
not held. When the page lands it wakes her on its own, in the conversation
that asked, and she answers with it. Afterwards the window holds one line for
the page, not the page.
"""

import asyncio

from src.core.agent.types import AssistantMessage, ToolCall
from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.memory.store import MemoryStore
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import SkillRegistry
from src.core.skills.web.fetch import Page
from src.core.skills.web.surface import WebSkill
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents, speaks


class Config:
    def __init__(self):
        self.consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                              "burst_steps": 3, "correlation_timeout": 5.0}
        self.attention = {"enabled": True, "trigger_words": ["bea"]}
        self.skills = {"web": {"enabled": True, "wait_seconds": 0.05}}


def fetches(url: str) -> AssistantMessage:
    return AssistantMessage(tool_calls=[
        ToolCall(id="w1", name="web_fetch", arguments={"url": url})])


class Brain:
    def __init__(self):
        self.consciousness = None
        self.event_manager = None


async def test_a_slow_page_lets_her_go_and_wakes_her_when_it_lands():
    config = Config()
    bus = PerceptionBus(window=0.0)
    registry = SkillRegistry()
    brain = Brain()
    web = WebSkill(config, bus, expression=None, context=brain)
    web.initialize()
    registry.register(web)

    async def slow_fetch(url):
        await asyncio.sleep(0.3)
        return Page(url=url, title="Meteo", text="A Milano domani piove. " * 200, source="html")

    web.fetcher.fetch = slow_fetch

    events = RecordingEvents()
    llm = FakeLLMClient([fetches("https://meteo.example/milano"),
                         speaks("aspetta, controllo"),
                         speaks("domani piove, porta l'ombrello")])
    mind = Consciousness(
        config=config, llm=llm, bus=bus, expression=FakeExpression(), surfaces=registry,
        history_manager=FakeHistory("s"), event_manager=events,
        soul_getter=lambda: "you are bea", operating_getter=lambda: "speak to talk",
        memory=MemoryStore(":memory:"), profiler=None, attention=Attention(config),
    )
    brain.consciousness = mind
    await web.start()

    bus.put(Perception(
        PerceptionKind.CHAT, "chat:ui", "[ema] bea che tempo fa domani a milano?",
        author=Author(platform="ui", native_id="owner", display_name="ema", is_owner=True),
    ))
    mind.alive = True
    loop = asyncio.create_task(mind.run())
    try:
        deadline = asyncio.get_running_loop().time() + 3
        while len(llm.calls) < 3 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
    finally:
        mind.alive = False
        loop.cancel()
        await asyncio.gather(loop, return_exceptions=True)
        await web.stop()

    assert len(llm.calls) == 3, "the page never woke her"
    _, told_them, woken = llm.calls
    # she was free to say she is checking, and that ended her turn
    assert "Still looking up" in str(told_them[-1]["content"])
    # she was let go: the first turn got the promise, not the page
    fetched = [e[3]["result"] for e in events.events
               if e[3].get("tool") == "web_fetch"]
    assert len(fetched) == 1 and fetched[0].startswith("Still looking up")
    # the second turn is the page arriving, where she was asked
    frame = woken[-1]["content"]
    assert "is back" in frame and "A Milano domani piove" in frame
    assert "[via web]" in frame  # asked on stage, answered on stage

    replayed = " ".join(str(m["content"]) for m in mind.sliding_window.replay())
    assert "(you read https://meteo.example/milano)" in replayed
    assert "A Milano domani piove. A Milano" not in replayed
