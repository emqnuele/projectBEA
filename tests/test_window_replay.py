"""Her past lines come back to her as the calls they were.

She speaks only through `speak`, writes only through `send_message`, and plain
text is thinking nobody hears. The window used to replay every line of hers as
plain assistant text, so each turn showed her dozens of answers given the way
the manual forbids — and the history won. On real turns from a Discord call on
2026-09-23, 32 of 36 answers came back as plain text nobody heard; replaying the
same window with her lines as calls, 0 of 36 did.

`messages()` stays the log as it was written down. `replay()` is what the model
reads, and the only thing the loop hands it.
"""

import asyncio
import json

import pytest

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.memory.store import MemoryStore
from src.core.mind.single_context import (
    REPLAYED_CALL_TOKENS,
    SENT,
    SPOKEN,
    SingleContext,
    entry_tokens,
)
from src.core.mind.token_budget import TokenBudget
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import SkillRegistry
from src.modules.llm.anthropic import _to_messages
from src.modules.llm.responses import _to_items
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents
from tests.test_unheard_words import Config, speaks


def calls_in(messages):
    return [(c["function"]["name"], json.loads(c["function"]["arguments"]))
            for m in messages for c in m.get("tool_calls") or []]


def a_call() -> SingleContext:
    ctx = SingleContext()
    ctx.append("user", "(VOICE) [via voice call] [ema] (voice): how are you?",
               key="stage", author="discord:1")
    ctx.append("assistant", "Fantastic, obviously.", key="stage", mood="happy")
    return ctx


# --- what she said ------------------------------------------------------------


def test_a_spoken_line_comes_back_as_the_speak_call_it_was():
    replay = a_call().replay()

    assert calls_in(replay) == [
        ("speak", {"mood": "happy", "message": "Fantastic, obviously."})]
    assert not any(m["role"] == "assistant" and m.get("content") for m in replay)


def test_the_call_is_answered_the_way_the_live_tool_answers_it():
    replay = a_call().replay()

    call, result = replay[-2], replay[-1]
    assert result == {"role": "tool", "tool_call_id": call["tool_calls"][0]["id"],
                      "name": "speak", "content": SPOKEN}


def test_a_written_line_comes_back_as_send_message_to_where_it_went():
    ctx = SingleContext()
    ctx.append("user", "[marco] ciao", key="telegram:55", author="telegram:7")
    ctx.append("assistant", "ei marco", key="telegram:55", addressee="telegram:7")

    replay = ctx.replay()

    assert calls_in(replay) == [("send_message", {
        "platform": "telegram", "channel": "55", "text": "ei marco"})]
    assert replay[-1]["content"] == SENT


def test_a_line_kept_before_moods_were_comes_back_with_the_default_face():
    ctx = SingleContext()
    ctx.append("assistant", "hey", key="stage")

    assert calls_in(ctx.replay()) == [("speak", {"mood": "neutral", "message": "hey"})]


def test_the_direction_inside_a_line_stays_inside_the_message():
    ctx = SingleContext()
    ctx.append("assistant", "<mood:smug> nice try.", key="stage", mood="neutral")

    assert calls_in(ctx.replay())[0][1]["message"] == "<mood:smug> nice try."


# --- everything else ------------------------------------------------------------


def test_what_others_said_and_the_bridge_pass_through_without_bookkeeping():
    ctx = SingleContext()
    ctx.clear("[EARLIER] the bridge")
    ctx.append("user", "[marco] ciao", key="telegram:55", author="telegram:7")

    assert ctx.replay() == [
        {"role": "system", "content": "[EARLIER] the bridge"},
        {"role": "user", "content": "[marco] ciao"},
    ]


def test_the_log_itself_still_reads_as_it_was_written():
    ctx = a_call()

    assert [(m["role"], m["content"]) for m in ctx.messages()] == [
        ("user", "(VOICE) [via voice call] [ema] (voice): how are you?"),
        ("assistant", "Fantastic, obviously."),
    ]


# --- the wire -------------------------------------------------------------------


def test_every_call_is_answered_before_anything_else_is_said():
    ctx = SingleContext()
    ctx.append("user", "[ema] ciao", key="discord:9", author="discord:1")
    ctx.append("assistant", "I AM HERE.", key="discord:9")
    ctx.append("assistant", "Oh, NOW she wants me.", key="stage", mood="angry")
    ctx.append("user", "(VOICE) [ema] (voice): hey", key="stage")

    replay = ctx.replay()

    for i, m in enumerate(replay):
        if m.get("tool_calls"):
            assert replay[i + 1]["role"] == "tool"
            assert replay[i + 1]["tool_call_id"] == m["tool_calls"][0]["id"]
    assert [m["role"] for m in replay] == [
        "user", "assistant", "tool", "assistant", "tool", "user"]


def test_the_same_window_replays_the_same_way_every_turn():
    """The provider caches the longest common prefix: an id that moved would
    re-bill the whole window on every turn."""
    ctx = a_call()
    ctx.append("assistant", "Still fantastic.", key="stage", mood="bored")

    first, second = ctx.replay(), ctx.replay()

    assert first == second
    ids = [m["tool_calls"][0]["id"] for m in first if m.get("tool_calls")]
    assert len(ids) == len(set(ids)) == 2


def test_a_line_is_rendered_once_and_reused_every_turn():
    """The window replays on every turn, on the way to the model: rendering
    thousands of lines again each time is latency nobody needs."""
    ctx = a_call()
    ctx.replay()
    hers = ctx._entries[-1]
    rendered = hers.wire

    ctx.append("user", "(VOICE) [ema] (voice): what?", key="stage")
    ctx.replay()

    assert hers.wire is rendered


def test_changing_what_replay_handed_out_never_changes_the_next_turn():
    ctx = a_call()
    first = ctx.replay()
    first[-2]["content"] = "scribbled on"
    first[-1]["content"] = "scribbled on"

    assert ctx.replay() == a_call().replay()


def test_a_line_shrunk_in_place_replays_with_its_new_words():
    """A ceiling lowered under a lone line shrinks it where it stands: the
    rendering kept from before must not replay the words that were cut."""
    ctx = SingleContext()
    long_line = "word " * 3000
    ctx.append("assistant", long_line, key="stage", mood="happy")
    ctx.replay()

    ctx.retarget(TokenBudget(max_tokens=1_000, trigger_tokens=800), 1_000)

    message = calls_in(ctx.replay())[0][1]["message"]
    assert message == ctx.messages()[0]["content"]
    assert len(message) < len(long_line)


def test_anthropic_reads_the_replay_as_tool_use_and_its_result():
    _, converted = _to_messages([{"role": "system", "content": "soul"},
                                 *a_call().replay()])

    use = converted[1]["content"][0]
    result = converted[2]["content"][0]
    assert use["type"] == "tool_use" and use["name"] == "speak"
    assert use["input"] == {"mood": "happy", "message": "Fantastic, obviously."}
    assert result == {"type": "tool_result", "tool_use_id": use["id"], "content": SPOKEN}


def test_the_responses_api_reads_the_replay_as_a_call_and_its_output():
    _, items = _to_items([{"role": "system", "content": "soul"}, *a_call().replay()])

    call, output = items[1], items[2]
    assert call["type"] == "function_call" and call["name"] == "speak"
    assert output == {"type": "function_call_output", "call_id": call["call_id"],
                      "output": SPOKEN}


# --- the budget -----------------------------------------------------------------


def test_the_budget_counts_what_the_call_costs_on_the_wire():
    ctx = SingleContext()
    theirs = ctx.append("user", "the same words", key="stage")
    hers = ctx.append("assistant", "the same words", key="stage", mood="happy")

    assert hers.tokens - theirs.tokens == REPLAYED_CALL_TOKENS
    assert ctx.total_tokens == entry_tokens("user", "the same words") + \
        entry_tokens("assistant", "the same words")


# --- across a restart -----------------------------------------------------------


@pytest.fixture
def memory():
    store = MemoryStore(":memory:")
    yield store
    store.close()


def test_the_face_she_said_it_with_survives_a_restart(memory):
    live = SingleContext(store=memory.window)
    live.append("assistant", "Fantastic, obviously.", key="stage", mood="happy")
    assert live.flush()

    after = SingleContext(store=memory.window)
    after.restore()

    assert calls_in(after.replay()) == [
        ("speak", {"mood": "happy", "message": "Fantastic, obviously."})]


# --- in the loop ----------------------------------------------------------------


def heard(text: str) -> Perception:
    return Perception(
        kind=PerceptionKind.VOICE, surface="voice:discord",
        content=f"[ema] (voice): {text}", salience=0.9, meta={"mentions_self": True},
        author=Author(platform="discord", native_id="1", display_name="ema"),
    )


async def test_the_next_turn_sees_her_last_line_as_a_speak_call():
    config = Config()
    first = speaks("Fantastic, obviously.")
    first.tool_calls[0].arguments["mood"] = "happy"
    mind = Consciousness(
        config=config, llm=FakeLLMClient(script=[first, speaks("Still fantastic.")]),
        bus=PerceptionBus(window=0.0), expression=FakeExpression(),
        surfaces=SkillRegistry(), history_manager=FakeHistory(),
        event_manager=RecordingEvents(), soul_getter=lambda: "soul",
        operating_getter=lambda: "rules", memory=MemoryStore(":memory:"),
        profiler=None, attention=Attention(config),
    )
    mind.alive = True
    task = asyncio.create_task(mind.run())
    try:
        mind.bus.put(heard("how are you?"))
        await asyncio.sleep(0.2)
        mind.bus.put(heard("what?"))
        await asyncio.sleep(0.2)
    finally:
        mind.alive = False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert mind.llm.call_count == 2
    second = mind.llm.calls[1]
    assert ("speak", {"mood": "happy", "message": "Fantastic, obviously."}) in calls_in(second)
    assert not any(m["role"] == "assistant" and m.get("content") and not m.get("tool_calls")
                   for m in second)
