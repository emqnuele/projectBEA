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

    async def deliver(self, channel_id, text, reply_to=None):
        self.sent.append(text)
        return [text]

    async def react(self, *args):
        return True


def _mind(channel, platform):
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
            await asyncio.sleep(0.05)
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
        config=config, llm=OneAnswerEach(), bus=channel, expression=FakeExpression(),
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
    await asyncio.sleep(0.6)

    mind.alive = False
    loop.cancel()
    try:
        await loop
    except asyncio.CancelledError:
        pass

    assert platform.sent == ["reply 1"], f"she answered {len(platform.sent)} times"


async def test_a_line_that_lands_after_she_answered_becomes_the_next_turn():
    """The other half of the same bug: what arrives *during* a turn used to be
    read back to her as fresh input, so she answered the same person twice in
    one turn. She has already replied — it waits, and gets batched."""
    channel = PerceptionBus(window=0.03, text_window=0.05, max_window=1.0)
    platform = Written()
    mind = _mind(channel, platform)
    mind.alive = True
    loop = asyncio.create_task(mind.run())

    channel.put(dm("hey", 1))
    await asyncio.sleep(0.07)          # she is now mid-turn (the model takes 50ms)
    channel.put(dm("come stai", 2))
    channel.put(dm("tutto bene?", 3))
    await asyncio.sleep(0.6)

    mind.alive = False
    loop.cancel()
    try:
        await loop
    except asyncio.CancelledError:
        pass

    assert platform.sent == ["reply 1", "reply 2"], platform.sent


async def test_something_from_elsewhere_still_steers_the_turn_in_flight():
    """Deferring is only right for a conversation she has answered. A voice
    line while she is writing a telegram reply is a barge-in, and reading it
    late is how she answers a question the room has moved past."""
    from src.core.perception.types import Author

    channel = PerceptionBus(window=0.03, text_window=0.05, max_window=1.0)
    platform = Written()
    mind = _mind(channel, platform)
    mind._sent = [{"platform": "telegram", "channel": "99", "text": "reply 1"}]

    heard = Perception(
        kind=PerceptionKind.VOICE, surface="voice:discord",
        content="[ema] (voice): aspetta", salience=0.9,
        author=Author(platform="discord", native_id="1", display_name="ema"))
    channel.put(heard)
    channel.put(dm("e comunque", 4))

    steering = mind._steering()
    assert [p.content for p in steering] == ["[ema] (voice): aspetta"]
    assert len(channel.drain_nowait()) == 1   # the telegram line went back


def test_the_steering_header_asks_her_to_fold_it_in():
    channel = PerceptionBus(window=0.0)
    mind = _mind(channel, Written())
    header = mind._frame([(dm("ciao", 1), 1.0)], steering=True)["content"]
    assert "do not send a separate reply" in header.lower()
