"""Opening a conversation with a reason, not just because a timer fired.

A spontaneous turn used to be "this went quiet, say something". An intention
she kept is a different thing: she has a reason, and the turn has to carry it
or she opens the chat with nothing to say.
"""

import time

import pytest

from src.core.agent.types import AssistantMessage, ToolCall
from src.core.memory.store import MemoryStore
from src.core.mind.conversation import INITIATIVE_FRAME, ConversationMind
from src.core.mind.scheduler import ConversationScheduler
from src.core.skills.base import SkillRegistry
from src.core.skills.platform import PlatformSkill
from tests.fakes import FakeLLMClient


class Config:
    def __init__(self):
        self.skills = {}
        self.attention = {}
        self.consciousness = {"conversation_history": 8, "conversation_steps": 2}
        self.rhythm = {"cross_platform": True}


class Recorder(PlatformSkill):
    def __init__(self, platform="telegram"):
        super().__init__(Config(), bus=None, expression=None)
        self.name = f"chat:{platform}"
        self.skill_name = platform
        self.platform = platform
        self.sent = []
        self.initialize()
        self.humanizer._sleep = _instant
        self.active = True

    async def send_text(self, channel_id, text, reply_to=None):
        self.sent.append((channel_id, text))
        return True


async def _instant(seconds):
    return None


def says(text: str) -> AssistantMessage:
    return AssistantMessage(tool_calls=[
        ToolCall(id="c1", name="send_message", arguments={"text": text})
    ])


@pytest.fixture
def memory():
    return MemoryStore(":memory:")


def mind(memory, llm, surface) -> ConversationMind:
    registry = SkillRegistry()
    registry.register(surface)
    return ConversationMind(
        config=Config(), llm=llm, memory=memory, surfaces=registry,
        soul_getter=lambda: "you are bea",
        operating_getter=lambda: "",
        scheduler=ConversationScheduler(),
    )


def _last_user(llm: FakeLLMClient) -> str:
    return llm.calls[-1][-1]["content"]


# --- the plain initiative turn is unchanged ---------------------------------


async def test_an_ordinary_initiative_turn_still_gets_the_usual_nudge(memory):
    llm = FakeLLMClient([says("ehi")])
    surface = Recorder()
    await mind(memory, llm, surface).turn_now("telegram:2", [], initiative=True)
    assert INITIATIVE_FRAME in _last_user(llm)


# --- a turn that has a reason ------------------------------------------------


async def test_a_reason_replaces_the_nudge(memory):
    llm = FakeLLMClient([says("com'è andata?")])
    surface = Recorder()
    await mind(memory, llm, surface).turn_now(
        "telegram:2", [], initiative=True, frame="[YOU MEANT TO] ask about the exam")
    assert "ask about the exam" in _last_user(llm)
    assert INITIATIVE_FRAME not in _last_user(llm)


async def test_she_actually_writes_when_she_had_a_reason(memory):
    llm = FakeLLMClient([says("com'è andata?")])
    surface = Recorder()
    await mind(memory, llm, surface).turn_now(
        "telegram:2", [], initiative=True, frame="ask about the exam")
    assert surface.sent == [("2", "com'è andata?")]


async def test_a_reason_without_initiative_is_ignored(memory):
    """A frame is what she opens with; an answer is not an opening."""
    llm = FakeLLMClient([says("ok")])
    surface = Recorder()
    await mind(memory, llm, surface).turn_now("telegram:2", [], frame="qualcosa")
    assert llm.calls == []


# --- the whole path, end to end ---------------------------------------------


async def test_an_intention_kept_now_becomes_a_message_later(memory):
    """The point of all of it: she decides, time passes, she does it."""
    from src.core.social.agenda import AgendaRunner

    memory.agenda.add("chiedere a ema com'è andato l'esame",
                      conversation_key="telegram:2", due_ts=time.time() - 1)

    llm = FakeLLMClient([says("ehi, com'è andata?")])
    surface = Recorder()
    runner = AgendaRunner(agenda=memory.agenda, conversations=mind(memory, llm, surface))

    assert await runner.run_once() == 1
    assert surface.sent == [("2", "ehi, com'è andata?")]
    assert "chiedere a ema com'è andato l'esame" in _last_user(llm)
    assert memory.agenda.pending() == []


async def test_what_she_opened_with_is_in_the_thread(memory):
    from src.core.social.agenda import AgendaRunner

    memory.agenda.add("chiedile dell'esame", conversation_key="telegram:2",
                      due_ts=time.time() - 1)
    llm = FakeLLMClient([says("com'è andata?")])
    runner = AgendaRunner(agenda=memory.agenda,
                          conversations=mind(memory, llm, Recorder()))
    await runner.run_once()
    assert [h["content"] for h in memory.conversations.history("telegram:2")] == [
        "com'è andata?"
    ]
