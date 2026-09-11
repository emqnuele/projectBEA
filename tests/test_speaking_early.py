"""She starts talking while the model is still writing the line.

A spoken turn used to exist all at once: the tool call finished, and only then
did anything reach the engine. Here the words leave as they are written, which
means the loop has to answer two questions it never had to before — what happens
to a line she opened and then changed her mind about, and what happens when the
words that arrive early turn out not to be words at all.
"""

import asyncio
import datetime
import json

from src.core.agent.types import AssistantMessage, ToolCall
from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import SkillRegistry
from tests.fakes import (
    FakeExpression,
    FakeHistory,
    RecordingEvents,
    StreamingLLMClient,
    settle,
    speaks,
)


class Config:
    def __init__(self, **consciousness):
        self.consciousness = {
            "enabled": True, "idle_after": 3600.0, "window": 0.0,
            "burst_steps": 3, "history_limit": 30, "correlation_timeout": 5.0,
        }
        self.consciousness.update(consciousness)
        self.attention = {"enabled": True, "trigger_words": ["bea"]}
        self.skills = {}


def build(llm, **consciousness):
    config = Config(**consciousness)
    bus = PerceptionBus(window=0.0)
    mind = Consciousness(
        config=config, llm=llm, bus=bus, expression=FakeExpression(),
        surfaces=SkillRegistry(), history_manager=FakeHistory(),
        event_manager=RecordingEvents(),
        soul_getter=lambda: "you are bea", operating_getter=lambda: "call speak to talk",
        attention=Attention(config),
    )
    mind.context = [mind._system_message()]
    return mind, bus


def said_to(mind) -> Perception:
    return Perception(
        PerceptionKind.CHAT, "chat:ui", "[marco] bea dimmi una cosa", salience=0.9,
        author=Author(platform="discord", native_id="1", display_name="marco"),
    )


async def one_turn(mind, bus, timeout: float = 2.0) -> None:
    """Runs the loop until the model has answered what is on the bus.

    Waits on the model having been called and the turn having settled rather
    than on a number of ticks: the whole point of the path under test is that a
    turn now takes many more of them.
    """
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


# --- the line leaves before it is finished -----------------------------------


async def test_the_room_hears_her_before_the_model_has_finished_writing():
    llm = StreamingLLMClient([speaks("Ma tu guarda questa cosa. Non ci posso credere.")])
    mind, bus = build(llm)

    # what had already been handed to the line while the call was still running
    early = []
    llm.after_delta = lambda: early.append(
        "".join(line.written for line in mind.expression.lines)
    )

    bus.put(said_to(mind))
    await one_turn(mind, bus)

    assert mind.expression.lines, "no line was ever opened"
    assert any(snapshot for snapshot in early), "nothing left before the call returned"
    assert early[-1].startswith("Ma tu guarda")


async def test_the_whole_line_is_what_she_ends_up_saying():
    line_text = "Ma tu guarda questa cosa. Non ci posso credere davvero."
    llm = StreamingLLMClient([speaks(line_text)])
    mind, bus = build(llm)

    bus.put(said_to(mind))
    await one_turn(mind, bus)

    line = mind.expression.lines[0]
    assert line.written == line_text
    assert line.closed and not line.cancelled


async def test_the_mood_is_worn_before_the_first_word_of_it():
    llm = StreamingLLMClient([speaks("ma tu guarda questa cosa", mood="angry")])
    mind, bus = build(llm)

    bus.put(said_to(mind))
    await one_turn(mind, bus)

    assert mind.expression.lines[0].mood == "angry"


async def test_a_mood_she_invented_still_lands_on_one_she_has():
    llm = StreamingLLMClient([speaks("ma tu guarda questa cosa", mood="furious")])
    mind, bus = build(llm)

    bus.put(said_to(mind))
    await one_turn(mind, bus)

    assert mind.expression.lines[0].mood == "angry"


async def test_the_line_is_not_also_spoken_a_second_time():
    """The words left through the line; `speak` must not send them again."""
    llm = StreamingLLMClient([speaks("ciao a tutti quanti, come va")])
    mind, bus = build(llm)

    bus.put(said_to(mind))
    await one_turn(mind, bus)

    assert mind.expression.spoken == []
    assert len(mind.expression.lines) == 1


async def test_what_was_said_still_enters_the_history():
    llm = StreamingLLMClient([speaks("ciao a tutti quanti, come va")])
    mind, bus = build(llm)

    bus.put(said_to(mind))
    await one_turn(mind, bus)

    assert [m["content"] for m in mind.history.messages] == ["ciao a tutti quanti, come va"]


# --- lines that should never have been opened --------------------------------


async def test_a_tool_that_says_nothing_out_loud_opens_no_line():
    silent = AssistantMessage(tool_calls=[
        ToolCall(id="c1", name="stay_silent", arguments={"reason": "nothing to say"})
    ])
    llm = StreamingLLMClient([silent])
    mind, bus = build(llm)

    bus.put(said_to(mind))
    await one_turn(mind, bus)

    assert mind.expression.lines == []


async def test_a_line_she_started_and_then_did_not_finish_is_thrown_away():
    """She opened her mouth and the turn ended some other way: a torn-down turn
    must not leave a mouth open and an engine still paying for it."""
    mind, _ = build(StreamingLLMClient())
    mind._live = mind.expression.open_line("angry")

    await mind._drop_unspoken()

    assert mind.expression.lines[0].cancelled
    assert mind._live is None


async def test_dropping_a_line_twice_is_not_an_error():
    """The loop drops one at the end of a step and again when the turn unwinds."""
    mind, _ = build(StreamingLLMClient())
    mind._live = mind.expression.open_line("angry")

    await mind._drop_unspoken()
    await mind._drop_unspoken()

    assert len(mind.expression.lines) == 1


async def test_an_engine_that_cannot_open_a_line_still_speaks_the_turn():
    llm = StreamingLLMClient([speaks("ciao a tutti quanti, come va")])
    mind, bus = build(llm)
    mind.expression.opens_lines = False

    bus.put(said_to(mind))
    await one_turn(mind, bus)

    assert mind.expression.spoken == [("neutral", "ciao a tutti quanti, come va", "local")]


async def test_speaking_early_can_be_switched_off():
    llm = StreamingLLMClient([speaks("ciao a tutti quanti, come va")])
    mind, bus = build(llm, stream_speech=False)

    bus.put(said_to(mind))
    await one_turn(mind, bus)

    assert mind.expression.lines == []
    assert mind.expression.spoken == [("neutral", "ciao a tutti quanti, come va", "local")]


# --- what arrives early is not always words ----------------------------------


async def test_a_line_that_met_scaffolding_is_thrown_away_and_said_properly():
    """A `<think>` that closes two sentences later cannot be seen a piece at a
    time. Nothing was heard yet, so the line goes and the finished message —
    which cleans whole — is spoken the ordinary way instead.
    """
    llm = StreamingLLMClient([speaks("<think>dovrei essere cattiva</think>ovviamente no")])
    mind, bus = build(llm)
    mind.expression.spoils_lines = True

    bus.put(said_to(mind))
    await one_turn(mind, bus)

    assert mind.expression.lines[0].cancelled
    assert mind.expression.spoken == [("neutral", "ovviamente no", "local")]


# --- and what the turn leaves behind -----------------------------------------


async def test_a_turn_writes_itself_down():
    """Twenty minutes later, "what was she actually told?" has an answer."""
    llm = StreamingLLMClient([speaks("ma tu guarda questa cosa", mood="angry")])
    mind, bus = build(llm)

    bus.put(said_to(mind))
    await one_turn(mind, bus)

    written = [json.loads(line) for line in
               mind.turns.path_for(datetime.date.today().isoformat())
               .read_text(encoding="utf-8").splitlines()]

    assert len(written) == 1
    turn = written[0]
    assert turn["spoke"] == {"mood": "angry", "message": "ma tu guarda questa cosa"}
    assert turn["tools"][0]["tool"] == "speak"
    assert "you are bea" in turn["prompt"]
    assert any("bea dimmi una cosa" in line for line in turn["perceptions"])


async def test_a_turn_she_said_nothing_in_is_written_down_too():
    """The silent ones are the turns you most want to be able to read back."""
    silent = AssistantMessage(tool_calls=[
        ToolCall(id="c1", name="stay_silent", arguments={"reason": "nothing to say"})
    ])
    mind, bus = build(StreamingLLMClient([silent]))

    bus.put(said_to(mind))
    await one_turn(mind, bus)

    turn = json.loads(mind.turns.path_for(datetime.date.today().isoformat())
                      .read_text(encoding="utf-8").splitlines()[0])
    assert turn["spoke"] is None
    assert turn["tools"][0]["tool"] == "stay_silent"


async def test_it_can_be_switched_off_entirely():
    mind, _ = build(StreamingLLMClient(), turn_log=False)
    assert mind.turns is None


# --- two tool calls being written at the same time ---------------------------


class InterleavingLLMClient(StreamingLLMClient):
    """A provider that writes two tool calls at once rather than one after it.

    Which is allowed, and is the reason every delta carries the index of the
    call it belongs to. One reader for the whole turn meant the second call's
    JSON was read as more of the first call's message: she said the brace and
    the rest of the line was never spoken at all.
    """

    async def stream_complete(self, messages, tools=None, *, on_tool_delta=None):
        message = await self.complete(messages, tools=tools)
        if on_tool_delta is None or len(message.tool_calls) < 2:
            return message

        first, second = message.tool_calls[0], message.tool_calls[1]
        raw = json.dumps(first.arguments)
        half = raw.index('"message"') + 24

        on_tool_delta(0, first.name, raw[:half])
        on_tool_delta(1, second.name, json.dumps(second.arguments))
        on_tool_delta(0, first.name, raw[half:])
        for _ in range(4):
            await asyncio.sleep(0)
        return message


def speaks_and_remembers(message: str) -> AssistantMessage:
    return AssistantMessage(tool_calls=[
        ToolCall(id="a", name="speak", arguments={"mood": "happy", "message": message}),
        ToolCall(id="b", name="remember", arguments={"fact": "marco likes pasta"}),
    ])


async def test_a_second_tool_call_does_not_end_up_inside_the_line():
    line_text = "Ma tu guarda questa cosa, non ci posso credere davvero."
    llm = InterleavingLLMClient([speaks_and_remembers(line_text)])
    mind, bus = build(llm)

    bus.put(said_to(mind))
    await one_turn(mind, bus)

    assert mind.expression.lines, "no line was ever opened"
    written = mind.expression.lines[0].written
    assert written == line_text, f"the line was corrupted: {written!r}"
    assert "{" not in written and "fact" not in written
