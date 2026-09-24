"""Three messages typed in a row are one thing said, and get one answer.

The batch used to close on a stopwatch started by the first perception: 0.3
seconds, against the ~1 second a person leaves between two typed lines. So
"hey" / "come stai" / "tutto bene?" arrived as three batches, and she answered
three times. It closes on a quiet gap now — nothing new for a while — which is
what the setting has always claimed to be.
"""

import asyncio

import pytest

from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Perception, PerceptionKind

TYPING = 0.12   # what a test is willing to call "a pause between two lines"
MODEL = 0.25    # a turn wide enough that a loaded runner still lands inside it


def bus(**kwargs) -> PerceptionBus:
    return PerceptionBus(window=0.03, text_window=TYPING, max_window=1.0, **kwargs)


def typed(i: int) -> Perception:
    return Perception(kind=PerceptionKind.CHAT, surface="chat:telegram",
                      content=f"line {i}", salience=0.9)


def spoken(i: int) -> Perception:
    return Perception(kind=PerceptionKind.VOICE, surface="voice:discord",
                      content=f"heard {i}", salience=0.9)


async def send(channel: PerceptionBus, items, gap: float) -> None:
    for item in items:
        channel.put(item)
        await asyncio.sleep(gap)


# --- the batch ----------------------------------------------------------------


@pytest.mark.parametrize("path", ["drain", "wait_or_idle"])
async def test_three_lines_typed_in_a_row_are_one_batch(path):
    """And it must not depend on whether the monologue is switched on."""
    channel = bus()
    asyncio.create_task(send(channel, [typed(1), typed(2), typed(3)], TYPING / 2))
    await asyncio.sleep(0)

    batch = await (channel.drain() if path == "drain"
                   else channel.wait_or_idle(30.0))
    assert [p.content for p in batch] == ["line 1", "line 2", "line 3"]


async def test_a_line_that_arrives_after_the_gap_is_its_own_turn():
    """Waiting forever is the opposite failure: a thought two seconds later is
    a new thought, and she should already have answered the first one."""
    channel = bus()
    asyncio.create_task(send(channel, [typed(1), typed(2)], TYPING * 3))
    await asyncio.sleep(0)
    assert [p.content for p in await channel.drain()] == ["line 1"]


async def test_the_batch_is_ordered_by_when_things_happened():
    """Two surfaces deposit in whatever order their transports woke up in."""
    channel = bus()
    later, earlier = typed(2), typed(1)
    later.ts, earlier.ts = 200.0, 100.0
    channel.put(later)
    channel.put(earlier)
    assert [p.ts for p in await channel.drain()] == [100.0, 200.0]


# --- the gap belongs to the sense ---------------------------------------------


async def test_a_voice_line_is_not_kept_waiting_for_a_typist():
    """A second of dead air in a call is a second she took to answer."""
    channel = bus()
    channel.put(spoken(1))
    started = asyncio.get_running_loop().time()
    await channel.drain()
    assert asyncio.get_running_loop().time() - started < TYPING


async def test_one_voice_line_in_a_typed_batch_sets_the_pace():
    channel = bus()
    channel.put(typed(1))
    channel.put(spoken(1))
    started = asyncio.get_running_loop().time()
    batch = await channel.drain()
    assert len(batch) == 2
    assert asyncio.get_running_loop().time() - started < TYPING


# --- and it cannot be held open forever ---------------------------------------


async def test_a_chat_that_never_stops_does_not_hold_the_turn():
    channel = PerceptionBus(window=0.05, text_window=0.2, max_window=0.5)

    async def forever():
        for i in range(100):
            channel.put(typed(i))
            await asyncio.sleep(0.05)

    task = asyncio.create_task(forever())
    await asyncio.sleep(0)
    started = asyncio.get_running_loop().time()
    batch = await channel.drain()
    elapsed = asyncio.get_running_loop().time() - started
    task.cancel()

    assert elapsed < 1.0
    assert 5 <= len(batch) <= 15


async def test_silence_still_becomes_an_idle_perception():
    assert (await bus().wait_or_idle(0.05))[0].kind is PerceptionKind.IDLE


async def test_texture_alone_never_counts_as_something_happening():
    channel = bus()
    heartbeat = Perception(kind=PerceptionKind.GAME, surface="game:mc",
                           content="(still playing)", salience=0.1,
                           meta={"noise": True})

    async def beat():
        for _ in range(5):
            channel.put(heartbeat)
            await asyncio.sleep(0.02)

    asyncio.create_task(beat())
    assert (await channel.wait_or_idle(0.2))[0].kind is PerceptionKind.IDLE


async def test_a_window_of_zero_still_takes_what_is_already_there():
    channel = PerceptionBus(window=0.0, text_window=0.0)
    channel.put(typed(1))
    channel.put(typed(2))
    assert len(await channel.drain()) == 2


# --- mid-turn, the gap still holds --------------------------------------------


def _clock():
    return asyncio.get_running_loop().time()


async def test_mid_turn_a_line_still_being_typed_waits_for_the_gap():
    channel = bus()
    channel.put(typed(1))
    asyncio.get_running_loop().call_later(TYPING / 2, channel.put, typed(2))
    started = _clock()
    arrived = await channel.steer(wait_for_typing=True)

    assert [p.content for p in arrived] == ["line 1", "line 2"]
    assert _clock() - started >= TYPING


async def test_mid_turn_a_line_already_quiet_does_not_wait():
    channel = bus()
    channel.put(typed(1))
    await asyncio.sleep(TYPING * 1.5)
    started = _clock()
    assert len(await channel.steer(wait_for_typing=True)) == 1
    assert _clock() - started < TYPING / 2


async def test_mid_turn_nothing_waits_in_a_call():
    channel = bus()
    channel.put(typed(1))
    started = _clock()
    assert len(await channel.steer(wait_for_typing=False)) == 1
    assert _clock() - started < TYPING / 2


async def test_mid_turn_something_live_is_never_kept_waiting_for_a_typist():
    channel = bus()
    channel.put(typed(1))
    channel.put(spoken(1))
    started = _clock()
    assert len(await channel.steer(wait_for_typing=True)) == 2
    assert _clock() - started < TYPING / 2


async def test_mid_turn_something_live_ends_the_wait_when_it_lands():
    channel = bus()
    channel.put(typed(1))
    asyncio.get_running_loop().call_later(TYPING / 4, channel.put, spoken(1))
    started = _clock()
    assert len(await channel.steer(wait_for_typing=True)) == 2
    assert _clock() - started < TYPING * 0.75


async def test_mid_turn_texture_does_not_end_the_wait():
    channel = bus()
    heartbeat = Perception(kind=PerceptionKind.GAME, surface="game:mc",
                           content="(still playing)", salience=0.1,
                           meta={"noise": True})
    channel.put(typed(1))
    asyncio.get_running_loop().call_later(TYPING / 4, channel.put, heartbeat)
    started = _clock()
    assert len(await channel.steer(wait_for_typing=True)) == 2
    assert _clock() - started >= TYPING


async def test_mid_turn_a_typist_who_never_stops_cannot_hold_the_step():
    channel = PerceptionBus(window=0.05, text_window=0.2, max_window=0.5)

    async def forever():
        for i in range(100):
            channel.put(typed(i))
            await asyncio.sleep(0.05)

    task = asyncio.create_task(forever())
    await asyncio.sleep(0)
    started = _clock()
    await channel.steer(wait_for_typing=True)
    task.cancel()
    assert _clock() - started < 1.0


async def test_mid_turn_nothing_waiting_means_no_wait():
    channel = bus()
    started = _clock()
    assert await channel.steer(wait_for_typing=True) == []
    assert _clock() - started < TYPING / 2


# --- the knobs ----------------------------------------------------------------


def test_the_gaps_are_settings_someone_can_turn():
    from src.core.settings_schema import section

    keys = {f.key for f in section("consciousness").settings}
    assert {"window", "text_window", "max_window"} <= keys


def test_the_defaults_reach_an_existing_install():
    from src.core.config import BrainConfig

    consciousness = BrainConfig().consciousness
    assert consciousness["text_window"] > consciousness["window"]
    assert consciousness["max_window"] > consciousness["text_window"]


# --- end to end ---------------------------------------------------------------


class Written:
    """A text platform that records what she sent, and when."""

    name = "chat:telegram"
    skill_name = "telegram"
    platform = "telegram"
    active = True
    context_section = None

    def __init__(self):
        self.sent = []

    def tools(self):
        return []

    def live_state(self):
        return None

    def context_for(self, batch):
        return None

    async def start(self):
        pass

    async def stop(self):
        pass

    def message_count(self, text):
        return len([line for line in text.split("\n") if line.strip()])

    async def deliver(self, channel_id, text, reply_to=None):
        self.sent.append(text)
        return [text]

    async def react(self, *args):
        return True


def _mind(channel, platform, llm=None):
    from src.core.agent.types import AssistantMessage, ToolCall
    from src.core.attention.gate import Attention
    from src.core.consciousness import Consciousness
    from src.core.memory.store import MemoryStore
    from src.core.skills.base import SkillRegistry
    from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents

    class Config:
        consciousness = {"enabled": True, "idle_after": 3600.0, "burst_steps": 6,
                         "correlation_timeout": 5.0, "stream_speech": False,
                         "turn_log": False, "window_persist_after_turn": False}
        attention = {"enabled": True, "trigger_words": ["bea"]}
        skills: dict = {}
        language = ""

    class OneAnswerEach(FakeLLMClient):
        """Answers every frame it has not seen, then has nothing to add."""

        def __init__(self):
            super().__init__()
            self.frames = 0

        async def complete(self, messages, tools=None, response_format=None):
            self.calls.append([dict(m) for m in messages])
            self.tools_seen.append([t["function"]["name"] for t in (tools or [])])
            await asyncio.sleep(MODEL)
            frames = sum(1 for m in messages if m.get("role") == "user"
                         and str(m.get("content", "")).startswith("["))
            if frames <= self.frames:
                return AssistantMessage(content="nothing more to add")
            self.frames = frames
            return AssistantMessage(tool_calls=[ToolCall(
                id=f"c{frames}", name="send_message",
                arguments={"platform": "telegram", "channel": "99",
                           "text": f"reply {frames}"})])

    surfaces = SkillRegistry()
    surfaces.register(platform)
    config = Config()
    return Consciousness(
        config=config, llm=llm or OneAnswerEach(), bus=channel, expression=FakeExpression(),
        surfaces=surfaces, history_manager=FakeHistory(),
        event_manager=RecordingEvents(), soul_getter=lambda: "soul",
        operating_getter=lambda: "rules", memory=MemoryStore(":memory:"),
        profiler=None, attention=Attention(config),
    )


def dm(text: str, message_id: int) -> Perception:
    from src.core.perception.types import Author

    return Perception(
        kind=PerceptionKind.CHAT, surface="chat:telegram",
        content=f"[ema] (telegram dm, channel_id=99): {text}", salience=0.9,
        meta={"channel_id": "99", "message_id": str(message_id), "is_dm": True,
              "conversation_key": "telegram:99", "mentions_self": True},
        author=Author(platform="telegram", native_id="1", display_name="ema"),
    )


async def test_hey_come_stai_tutto_bene_gets_one_reply():
    channel = bus()
    platform = Written()
    mind = _mind(channel, platform)
    mind.alive = True
    loop = asyncio.create_task(mind.run())

    for i, text in enumerate(["hey", "come stai", "tutto bene?"]):
        channel.put(dm(text, i))
        await asyncio.sleep(TYPING / 2)
    await asyncio.sleep(TYPING + MODEL * 4)

    mind.alive = False
    loop.cancel()
    try:
        await loop
    except asyncio.CancelledError:
        pass

    assert platform.sent == ["reply 1"], f"she answered {len(platform.sent)} times"


class ReadsEverything:
    """A model that answers every line it has not answered yet, then stops.

    Built on first use, so the fakes are only imported where `_mind` imports them.
    """

    def __new__(cls):
        import re

        from src.core.agent.types import AssistantMessage, ToolCall
        from tests.fakes import FakeLLMClient

        class Model(FakeLLMClient):
            def __init__(self):
                super().__init__()
                self.answered: set = set()

            async def complete(self, messages, tools=None, response_format=None):
                self.calls.append([dict(m) for m in messages])
                await asyncio.sleep(MODEL)
                seen = set()
                for m in messages:
                    if m.get("role") == "user":
                        seen |= set(re.findall(r"line (\d+)", str(m.get("content", ""))))
                new = sorted(seen - self.answered, key=int)
                if not new:
                    return AssistantMessage(content="")
                self.answered |= set(new)
                return AssistantMessage(tool_calls=[ToolCall(
                    id="c" + "_".join(new), name="send_message",
                    arguments={"platform": "telegram", "channel": "99",
                               "text": "reply to " + "+".join(new)})])

        return Model()


async def _typed_into(offsets, llm=None):
    """Runs the loop while `line 1`, `line 2`, ... arrive at `offsets` seconds."""
    channel = bus()
    platform = Written()
    mind = _mind(channel, platform, llm=llm or ReadsEverything())
    mind.alive = True
    loop = asyncio.create_task(mind.run())
    elapsed = 0.0
    for i, at in enumerate(offsets, start=1):
        await asyncio.sleep(at - elapsed)
        elapsed = at
        channel.put(dm(f"line {i}", i))
    await asyncio.sleep(TYPING + MODEL * 8)
    mind.alive = False
    loop.cancel()
    await asyncio.gather(loop, return_exceptions=True)
    return mind, platform


async def test_a_line_that_lands_after_she_answered_is_answered_in_the_same_turn():
    """It used to wait for the whole turn to end, then open a turn of its own:
    one more model call, and every step she had left in front of the reply."""
    mind, platform = await _typed_into([0.0, TYPING + MODEL / 2])

    assert platform.sent == ["reply to 1", "reply to 2"]
    assert len(mind.llm.calls) == 3, "a turn of its own costs a fourth call"


async def test_lines_still_being_typed_at_a_step_boundary_get_one_reply():
    """The quiet gap holds mid-turn too: two lines a person is still typing
    when a step ends are one thing said, not two replies."""
    second = TYPING + MODEL * 0.8   # just before the first step ends
    mind, platform = await _typed_into([0.0, second, second + TYPING / 2])

    assert platform.sent == ["reply to 1", "reply to 2+3"]
    assert len(mind.llm.calls) == 3


async def test_what_arrives_during_her_last_step_still_becomes_the_next_turn():
    """Nothing reads the bus once she has stopped: that line is a turn of its own."""
    mind, platform = await _typed_into([0.0, TYPING + MODEL * 1.5])

    assert platform.sent == ["reply to 1", "reply to 2"]
    assert len(mind.llm.calls) == 4


async def test_something_from_elsewhere_still_steers_the_turn_in_flight():
    """A voice line while she is writing a telegram reply is a barge-in, and
    reading it late is how she answers a question the room has moved past."""
    channel = bus()
    mind = _mind(channel, Written())
    mind._sent = [{"platform": "telegram", "channel": "99", "text": "reply 1"}]

    channel.put(spoken(1))
    channel.put(dm("e comunque", 4))

    steering = await mind._steering()
    assert [p.content for p in steering] == [spoken(1).content, dm("e comunque", 4).content]


async def test_in_a_call_an_answered_conversation_still_waits_for_the_next_turn():
    """The call keeps the steering it had: nothing waits for a typist, and a
    line from a conversation she has answered goes back on the bus."""
    channel = bus()
    mind = _mind(channel, Written())
    mind._batch = [spoken(1)]
    mind._sent = [{"platform": "telegram", "channel": "99", "text": "reply 1"}]

    channel.put(dm("e comunque", 4))
    started = asyncio.get_running_loop().time()
    steering = await mind._steering()

    assert asyncio.get_running_loop().time() - started < TYPING / 2
    assert steering == []
    assert len(channel.drain_nowait()) == 1


async def test_what_is_not_written_keeps_the_rule_it_had():
    """Only a written line is answered twice in a turn: a voice line after
    she has spoken is still the next turn's, as it always was."""
    channel = bus()
    mind = _mind(channel, Written())
    mind._said = {"mood": "neutral", "message": "ciao"}

    channel.put(spoken(2))
    assert await mind._steering() == []
    assert len(channel.drain_nowait()) == 1


def test_a_line_after_her_reply_is_framed_as_the_next_thing_said():
    channel = PerceptionBus(window=0.0)
    mind = _mind(channel, Written())
    header = mind._frame([(dm("ciao", 1), 1.0)], steering=True,
                         after_reply=True)["content"]
    assert header.startswith("[NEW MESSAGE — arrived after you already replied")
    assert "do not send a separate reply" not in header.lower()


# --- a line she was shown mid-turn is not left unanswered ---------------------


def _script(*steps):
    """A model that plays `steps` in order, one per call, with a model's pace."""
    from src.core.agent.types import AssistantMessage, ToolCall
    from tests.fakes import FakeLLMClient

    replies = []
    for step in steps:
        if isinstance(step, str):
            replies.append(AssistantMessage(content=step))
        else:
            name, arguments = step
            replies.append(AssistantMessage(tool_calls=[
                ToolCall(id=f"c{len(replies)}", name=name, arguments=arguments)]))

    class Scripted(FakeLLMClient):
        async def complete(self, messages, tools=None, response_format=None):
            await asyncio.sleep(MODEL)
            return await super().complete(messages, tools, response_format)

    return Scripted(replies)


def _send(text):
    return ("send_message", {"platform": "telegram", "channel": "99", "text": text})


async def test_a_line_she_saw_mid_turn_and_wrote_her_answer_to_as_plain_text_is_rescued():
    """Plain text is her thinking: the answer to the line she was shown has to
    reach them, or it is lost — it will not come back as a turn of its own."""
    llm = _script(_send("reply 1"), "certo, sto bene", _send("reply 2"))
    mind, platform = await _typed_into([0.0, TYPING + MODEL / 2], llm=llm)

    assert platform.sent == ["reply 1", "reply 2"]
    assert any(m.get("content") == mind._NO_TOOL_NUDGE for m in llm.calls[-1])


async def test_choosing_silence_for_a_line_seen_mid_turn_is_respected():
    llm = _script(_send("reply 1"), ("say_nothing", {}))
    mind, platform = await _typed_into([0.0, TYPING + MODEL / 2], llm=llm)

    assert platform.sent == ["reply 1"]
    assert len(llm.calls) == 2


def test_the_steering_header_asks_her_to_fold_it_in():
    channel = PerceptionBus(window=0.0)
    mind = _mind(channel, Written())
    header = mind._frame([(dm("ciao", 1), 1.0)], steering=True)["content"]
    assert "do not send a separate reply" in header.lower()
