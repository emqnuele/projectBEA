"""She knows where she is, and a text-only answer never stays mute."""

import random
from types import SimpleNamespace

import pytest

from src.core.agent.types import AssistantMessage, ToolCall
from src.core.memory.store import MemoryStore
from src.core.mind.conversation import ConversationMind, place_header
from src.core.mind.scheduler import ConversationScheduler
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import SkillRegistry
from tests.fakes import FakeLLMClient, RecordingEvents
from tests.test_conversation import FakeDiscord, message, replies


@pytest.fixture
def setup():
    store = MemoryStore(":memory:")
    surfaces = SkillRegistry()
    discord = FakeDiscord()
    surfaces.register(discord)
    yield store, surfaces, discord
    store.close()


def build(setup, llm):
    from tests.test_conversation import Config

    store, surfaces, _ = setup
    return ConversationMind(
        config=Config(), llm=llm, memory=store, surfaces=surfaces,
        soul_getter=lambda: "you are bea",
        operating_getter=lambda: "you speak with tools",
        scheduler=ConversationScheduler(), event_manager=RecordingEvents(),
    )


def test_the_header_names_platform_channel_and_person():
    author = Author(platform="telegram", native_id="4711", display_name="marco")
    incoming = [Perception(kind=PerceptionKind.CHAT, surface="chat:telegram",
                           content="[marco] ciao", salience=0.8,
                           meta={"channel_id": "999"}, author=author)]
    header = place_header("telegram:999", incoming)
    assert "telegram" in header.lower()
    assert "999" in header
    assert "marco" in header.lower()


async def test_the_scoped_context_says_where_she_is(setup):
    llm = FakeLLMClient([replies()])
    await build(setup, llm).turn_now("discord:123", [message()])
    assert "WHERE YOU ARE" in llm.last_system_prompt
    assert "discord" in llm.last_system_prompt.lower()


async def test_a_text_only_answer_is_rescued_once(setup):
    llm = FakeLLMClient([
        AssistantMessage(content="ok ok sto arrivando"),
        replies("ok ok sto arrivando"),
    ])
    _, _, discord = setup
    await build(setup, llm).turn_now("discord:123", [message()])
    assert discord.sent == [("123", "ok ok sto arrivando", "m1")]
    assert llm.call_count == 2


async def test_silence_is_a_decision_not_a_failure(setup):
    silence = AssistantMessage(tool_calls=[ToolCall(id="c", name="say_nothing", arguments={})])
    llm = FakeLLMClient([silence])
    _, _, discord = setup
    await build(setup, llm).turn_now("discord:123", [message()])
    assert discord.sent == []
    assert llm.call_count == 1


def test_annotate_never_drops_and_stays_deterministic():
    from src.core.attention.gate import Attention

    cfg = SimpleNamespace(**{
        "attention": {"enabled": True, "mode": "annotate", "cooldown_seconds": 20,
                      "voice_cooldown_seconds": 5, "interject_threshold": 0.45,
                      "quiet_hours": [3, 9], "trigger_words": ["bea"],
                      "hot_names": [], "self_ids": [], "digest_max_lines": 8},
        "persona": {"name": "Bea"},
    })

    def msg(text, **meta):
        m = {"channel_id": "999", "message_id": "1", "is_dm": False,
             "mentions_self": False, "reply_to_self": False,
             "conversation_key": "telegram:999"}
        m.update(meta)
        return Perception(kind=PerceptionKind.CHAT, surface="chat:telegram",
                          content=f"[marco] {text}", salience=0.8, meta=m,
                          author=Author(platform="telegram", native_id="4711",
                                        display_name="marco"))

    batch = [msg("ciao a tutti"), msg("bea dimmi", mentions_self=True)]
    first = Attention(cfg, rng=random.Random(0), clock=lambda: 1000000.0).annotate(batch)
    second = Attention(cfg, rng=random.Random(99), clock=lambda: 1000000.0).annotate(batch)
    assert len(first) == 2
    assert [prio for _, prio in first] == [prio for _, prio in second]
    assert first[1][1] == 1.0
