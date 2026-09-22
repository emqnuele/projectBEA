"""A turn nobody heard gets its rescue - whatever else the turn accomplished.

The 23:50:43 Discord silence: STT delivered the line, the model called
`objective_started` (a plan tool: it succeeds, it delivers nothing) and then
wrote its answer as plain text. `_reached_someone()` counted the successful
tool as "somebody was reached", the one rescue never fired, and the turn
ended mute with nothing in the log to say so.

These tests pin the whole matrix: side effects never stand in for an answer,
a final written as plain text always earns the rescue, an explicit answer or
an audience-reaching tool suppresses it, and a turn where she only acted -
even with a lively inner monologue - gets no rescue (no chatter, no call).
"""

import asyncio

from src.core.agent.tools import Tool
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
        self.consciousness = {"idle_after": 3600.0, "window": 0.0, "burst_steps": 6,
                              "correlation_timeout": 5.0, "stream_speech": False,
                              "turn_log": False, "window_persist_after_turn": False}
        self.attention = {"enabled": True, "trigger_words": ["bea"]}
        self.skills = {}
        self.language = ""


class SideEffectSkill:
    """A skill whose tool does something but says nothing: the plan."""

    name = "plan"
    skill_name = None
    active = True
    context_section = None
    platform = ""

    def tools(self):
        return [Tool(
            "objective_started", "Mark the objective you are on now.",
            {"type": "object", "properties": {"objective": {"type": "integer"}},
             "required": ["objective"]},
            lambda **kw: "You're on #5: talk to ema about you and ask him questions.",
        )]

    def live_state(self):
        return None

    def context_for(self, batch):
        return None


class AudienceSkill:
    """A skill tool that writes to an audience, declared `reaches=True`."""

    name = "mc"
    skill_name = None
    active = True
    context_section = None
    platform = ""

    def __init__(self, result="Sent to the game chat."):
        self.result = result

    def tools(self):
        return [Tool(
            "mc_chat", "Type a message in the game chat.",
            {"type": "object", "properties": {"message": {"type": "string"}},
             "required": ["message"]},
            lambda **kw: self.result, reaches=True,
        )]

    def live_state(self):
        return None

    def context_for(self, batch):
        return None


def mind(*script, surfaces=None) -> Consciousness:
    config = Config()
    return Consciousness(
        config=config, llm=FakeLLMClient(script=list(script)),
        bus=PerceptionBus(window=0.0), expression=FakeExpression(),
        surfaces=surfaces or SkillRegistry(), history_manager=FakeHistory(),
        event_manager=RecordingEvents(), soul_getter=lambda: "soul",
        operating_getter=lambda: "rules", memory=MemoryStore(":memory:"),
        profiler=None, attention=Attention(config),
    )


def surfaces_with(*skills) -> SkillRegistry:
    reg = SkillRegistry()
    for s in skills:
        reg.register(s)
    return reg


def heard(text: str = "bea come va") -> Perception:
    return Perception(
        kind=PerceptionKind.VOICE, surface="voice:discord",
        content=f"[ema] (voice): {text}", salience=0.9, meta={"mentions_self": True},
        author=Author(platform="discord", native_id="1", display_name="ema"),
    )


def side_effect() -> AssistantMessage:
    return AssistantMessage(
        content="Right, Ema is here, let me mark the objective.",
        tool_calls=[ToolCall(id="c1", name="objective_started",
                             arguments={"objective": 5})])


def speaks(message: str) -> AssistantMessage:
    return AssistantMessage(tool_calls=[
        ToolCall(id="c2", name="speak", arguments={"mood": "neutral", "message": message})])


async def run(mind_: Consciousness) -> None:
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


# --- the incident -----------------------------------------------------------


async def test_side_tool_then_plain_text_gets_the_rescue():
    """The 23:50:43 silence: a successful side tool must not stand in for
    an answer the model wrote as plain text."""
    reg = surfaces_with(SideEffectSkill())
    m = mind(side_effect(),
             AssistantMessage(content="So, Ema, what's your deal?"),
             speaks("So, Ema, what's your deal?"),
             surfaces=reg)
    await run(m)
    assert m._said is not None
    assert m._said["message"] == "So, Ema, what's your deal?"
    assert m.llm.call_count == 3


async def test_think_aloud_then_side_tool_alone_gets_no_rescue():
    """Thinking out loud before acting is thinking, not an answer: a turn of
    pure action with an empty final must not cost an extra model call."""
    reg = surfaces_with(SideEffectSkill())
    m = mind(side_effect(), AssistantMessage(content=None), surfaces=reg)
    await run(m)
    assert m._said is None
    assert m.llm.call_count == 2


async def test_plain_text_alone_still_gets_the_rescue():
    m = mind(AssistantMessage(content="ciao a voce?"),
             speaks("ciao a voce?"))
    await run(m)
    assert m._said is not None
    assert m.llm.call_count == 2


async def test_side_tool_alone_gets_no_rescue():
    """She acted and kept quiet: her right, no chatter, no extra call."""
    script = [AssistantMessage(
        content=None,
        tool_calls=[ToolCall(id="c1", name="objective_started",
                             arguments={"objective": 5})]),
        AssistantMessage(content=None)]
    reg = surfaces_with(SideEffectSkill())
    m = mind(*script, surfaces=reg)
    await run(m)
    assert m._said is None
    assert m._rescued is False
    assert m.llm.call_count == 2


# --- audience-reaching tools ------------------------------------------------


async def test_audience_tool_success_suppresses_the_rescue():
    reg = surfaces_with(SideEffectSkill(), AudienceSkill())
    m = mind(AssistantMessage(
        content=None,
        tool_calls=[ToolCall(id="c1", name="mc_chat",
                             arguments={"message": "ciao a tutti"})]),
        AssistantMessage(content=None),
        surfaces=reg)
    await run(m)
    assert m._rescued is False
    assert m.llm.call_count == 2


async def test_audience_tool_failure_with_side_success_still_gets_rescue():
    """A broken answer is not an answer, even when other tools worked."""
    reg = surfaces_with(SideEffectSkill(), AudienceSkill(result="FAILED: nothing was sent."))
    m = mind(side_effect(),
             AssistantMessage(
                 content=None,
                 tool_calls=[ToolCall(id="c2", name="mc_chat",
                                      arguments={"message": "ciao"})]),
             AssistantMessage(content="ci riprovo"),
             speaks("ci riprovo a voce"),
             surfaces=reg)
    await run(m)
    assert m._said is not None


# --- diagnostics ------------------------------------------------------------


async def test_rescue_is_logged_and_recorded():
    import datetime

    from src.core.mind.turnlog import TurnLog

    reg = surfaces_with(SideEffectSkill())
    m = mind(side_effect(),
             AssistantMessage(content="So, Ema, what's your deal?"),
             speaks("eccomi, scusa il ritardo"),
             surfaces=reg)
    m.turns = TurnLog(str(__import__("tempfile").mkdtemp()), 1)
    await run(m)
    assert m._rescued is True
    day = datetime.datetime.now().strftime("%Y-%m-%d")
    written = [__import__("json").loads(line)
               for line in m.turns.path_for(day).read_text().splitlines() if line]
    assert written[0]["rescued"] is True


async def test_ignored_rescue_is_an_error_event():
    reg = surfaces_with(SideEffectSkill())
    m = mind(side_effect(),
             AssistantMessage(content="nobody will hear this either"),
             AssistantMessage(content="still nobody hears this"),
             surfaces=reg)
    await run(m)
    assert m._said is None
    errors = [e for e in m.events.events if e[0] is EventCategory.ERROR]
    assert any("even after the one rescue" in e[2] for e in errors)


# --- the declaration itself -------------------------------------------------


def test_audience_declaration_is_wired():
    """`reaches` is declared where the audience is, not guessed at rescue time.

    `speak` speaks to the room and `discord_summon` DMs an invite: both must
    suppress the rescue. `discord_leave_voice` only moves the body, so it
    must not.
    """
    from src.core.mind.tools import MindTools
    from src.core.skills.voice.surface import VoiceSurface

    mind_box = MindTools(surfaces_with(), speak=lambda **k: "",
                         stay_silent=lambda **k: "")
    assert mind_box.registry().get("speak").reaches is True

    voice = VoiceSurface.__new__(VoiceSurface)
    voice.active = True
    voice.voice_channel = None
    tools = {t.name: t for t in voice.tools()}
    assert tools["discord_summon"].reaches is True
    assert tools["discord_send_message"].reaches is True
    assert "discord_leave_voice" not in tools

    voice.voice_channel = "123"
    tools = {t.name: t for t in voice.tools()}
    assert tools["discord_leave_voice"].reaches is False
