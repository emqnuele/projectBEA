"""A turn that reached nobody gets its one rescue, whatever went wrong.

Plain text is private thinking and a tool that failed is not an answer: both
end with a person waiting on a reply that never came. The difference used to
matter — reaching for a tool counted as having acted, so a call that came back
`ERROR: unknown tool` spent the rescue and she simply went quiet.
"""

from src.core.agent.types import AssistantMessage, ToolCall
from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.events import EventCategory
from src.core.memory.store import MemoryStore
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import SkillRegistry
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents


class Config:
    def __init__(self):
        self.consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                              "burst_steps": 2, "correlation_timeout": 5.0,
                              "stream_speech": False, "turn_log": False,
                              "window_persist_after_turn": False}
        self.attention = {"enabled": True, "trigger_words": ["bea"]}
        self.skills = {}
        self.language = ""


def mind(*script) -> Consciousness:
    config = Config()
    return Consciousness(
        config=config, llm=FakeLLMClient(script=list(script)),
        bus=PerceptionBus(window=0.0), expression=FakeExpression(),
        surfaces=SkillRegistry(), history_manager=FakeHistory(),
        event_manager=RecordingEvents(), soul_getter=lambda: "soul",
        operating_getter=lambda: "rules", memory=MemoryStore(":memory:"),
        profiler=None, attention=Attention(config),
    )


def heard(text: str = "bea esci dalla call") -> Perception:
    return Perception(
        kind=PerceptionKind.VOICE, surface="voice:discord",
        content=f"[ema] (voice): {text}", salience=0.9, meta={"mentions_self": True},
        author=Author(platform="discord", native_id="1", display_name="ema"),
    )


def ghost(name: str = "discord_leave_voice") -> AssistantMessage:
    """A tool call for something the schema does not carry."""
    return AssistantMessage(tool_calls=[ToolCall(id="c1", name=name, arguments={})])


def speaks(message: str) -> AssistantMessage:
    return AssistantMessage(tool_calls=[
        ToolCall(id="c2", name="speak", arguments={"mood": "neutral", "message": message})])


async def run(mind_: Consciousness) -> None:
    import asyncio

    mind_.alive = True
    task = asyncio.create_task(mind_.run())
    mind_.bus.put(heard())
    await asyncio.sleep(0.2)
    mind_.alive = False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# --- the rescue ---------------------------------------------------------------


async def test_a_tool_that_does_not_exist_still_earns_the_rescue():
    m = mind(ghost(), AssistantMessage(content="hm"), speaks("va bene, ciao"))
    await run(m)
    assert m._said is not None
    assert m._said["message"] == "va bene, ciao"


async def test_a_tool_that_failed_still_earns_the_rescue():
    m = mind(
        AssistantMessage(tool_calls=[ToolCall("c1", "send_message", {
            "platform": "nowhere", "channel": "1", "text": "ciao"})]),
        AssistantMessage(content="hm"),
        speaks("allora te lo dico a voce"),
    )
    await run(m)
    assert m._said is not None


async def test_a_tool_that_worked_does_not_trip_it():
    """One answer, not two: she said something, so nothing is missing."""
    m = mind(speaks("eccomi"), AssistantMessage(content="done"))
    await run(m)
    assert m.llm.call_count == 1
    assert m._said["message"] == "eccomi"


async def test_choosing_silence_is_an_answer():
    m = mind(AssistantMessage(tool_calls=[
        ToolCall("c1", "stay_silent", {"reason": "niente da dire"})]))
    await run(m)
    assert m.llm.call_count == 1


# --- what the log says about it -----------------------------------------------


async def test_a_failed_tool_is_reported_as_a_failure():
    m = mind(ghost(), AssistantMessage(content="hm"), speaks("ok"))
    await run(m)
    errors = [e for e in m.events.events if e[0] is EventCategory.ERROR]
    assert errors, "a tool that did not exist was logged as if it had worked"
    assert "unknown tool" in errors[0][2]
    assert "discord_leave_voice" in errors[0][2]


async def test_a_tool_that_worked_carries_its_observation():
    m = mind(speaks("eccomi"))
    await run(m)
    calls = [e for e in m.events.events if e[0] is EventCategory.TOOL]
    assert calls[0][3]["tool"] == "speak"
    assert calls[0][3]["result"] == "Spoken."


async def test_the_rescue_is_counted_in_what_the_turn_cost():
    """It is a model call like any other; reporting one fewer hides it."""
    m = mind(ghost(), AssistantMessage(content="hm"), speaks("ok"))
    await run(m)
    cost = [e for e in m.events.events if e[1] == "cost"]
    assert cost, "no cost was published"
    assert cost[0][3]["steps"] == m.llm.call_count


# --- and what she was thinking while she did it ------------------------------


async def test_the_monologue_is_kept_with_the_turn():
    import datetime

    from src.core.mind.turnlog import TurnLog

    m = mind(AssistantMessage(content="uff, che palle"), speaks("eccomi"))
    m.turns = TurnLog(str(__import__("tempfile").mkdtemp()), 1)
    await run(m)

    day = datetime.datetime.now().strftime("%Y-%m-%d")
    written = [__import__("json").loads(line)
               for line in m.turns.path_for(day).read_text().splitlines() if line]
    assert written[0]["thought"] == ["uff, che palle"]
    assert written[0]["spoke"]["message"] == "eccomi"
