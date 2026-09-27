"""While somebody waits on her answer, her face says she is working on it."""

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.memory.store import MemoryStore
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import SkillRegistry
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents, speaks, stays_silent


class Config:
    def __init__(self):
        self.consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                              "burst_steps": 3, "correlation_timeout": 5.0}
        self.attention = {"enabled": True, "trigger_words": ["bea"]}
        self.skills = {}


def mind_with(expression, script):
    config = Config()
    return Consciousness(
        config=config, llm=FakeLLMClient(script), bus=PerceptionBus(window=0.0),
        expression=expression, surfaces=SkillRegistry(), history_manager=FakeHistory("s"),
        event_manager=RecordingEvents(), soul_getter=lambda: "you are bea",
        operating_getter=lambda: "speak to talk", memory=MemoryStore(":memory:"),
        profiler=None, attention=Attention(config),
    )


def chat(text):
    return Perception(PerceptionKind.CHAT, "chat:ui", f"[marco] {text}",
                      author=Author(platform="ui", native_id="marco", display_name="marco"))


async def test_a_turn_somebody_waits_on_thinks_first_and_stops_after():
    expression = FakeExpression()
    mind = mind_with(expression, [speaks("eccomi")])

    await mind._run_turn([chat("bea ci sei?")])

    assert expression.thinking == [True, False]


async def test_her_own_idle_tick_does_not_put_on_a_thinking_face():
    expression = FakeExpression()
    mind = mind_with(expression, [stays_silent()])

    await mind._run_turn([Perception(PerceptionKind.IDLE, "loop", "")])

    assert expression.thinking == []


async def test_a_turn_that_fails_still_takes_the_thinking_face_off():
    class Fails(FakeLLMClient):
        async def complete(self, messages, tools=None, response_format=None):
            raise RuntimeError("the provider went away")

    expression = FakeExpression()
    config = Config()
    mind = Consciousness(
        config=config, llm=Fails([]), bus=PerceptionBus(window=0.0), expression=expression,
        surfaces=SkillRegistry(), history_manager=FakeHistory("s"), event_manager=RecordingEvents(),
        soul_getter=lambda: "you are bea", operating_getter=lambda: "speak to talk",
        memory=MemoryStore(":memory:"), profiler=None, attention=Attention(config),
    )

    try:
        await mind._run_turn([chat("bea?")])
    except RuntimeError:
        pass

    assert expression.thinking == [True, False]
