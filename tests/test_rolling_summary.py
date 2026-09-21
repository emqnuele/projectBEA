"""The rolling summary of a conversation, and the morning that reads it.

The `summaries` table had a reader and no writer: the morning pass asked it
what happened last time and always got nothing back, so point three of waking
up ("pick a conversation up instead of restarting it") was dead code. The
pass that filled it was deleted with the class it lived in.
"""

import time
from types import SimpleNamespace

import pytest

from src.core.memory.profiler import SUMMARY_EVERY, Profiler
from src.core.memory.store import MemoryStore
from src.core.skills.dream.surface import DreamSkill

KEY = "telegram:55"


class ScriptedLLM:
    def __init__(self, reply=None):
        self.reply = reply if reply is not None else {"summary": "marco aspetta la patch"}
        self.payloads = []

    async def complete_json(self, payload, system=None, history=None):
        self.payloads.append(payload)
        return dict(self.reply) if isinstance(self.reply, dict) else self.reply


class Config:
    def __init__(self):
        self.skills = {"dream": {"enabled": True}}
        self.language = ""


@pytest.fixture
def memory():
    store = MemoryStore(":memory:")
    yield store
    store.close()


def chatter(memory, lines: int, key: str = KEY):
    for i in range(lines):
        memory.conversations.add(conversation_key=key, role="user", kind="chat",
                                 content=f"[marco] riga {i}", platform="telegram",
                                 author_identity="telegram:7", display_name="marco")


# --- the summary is written again --------------------------------------------


async def test_a_busy_conversation_gets_a_summary(memory):
    chatter(memory, SUMMARY_EVERY)
    llm = ScriptedLLM()

    assert await Profiler(llm, memory).maybe_summarize(KEY) is True
    assert memory.conversations.summary(KEY) == "marco aspetta la patch"


async def test_a_quiet_conversation_costs_no_model_call(memory):
    chatter(memory, 3)
    llm = ScriptedLLM()

    assert await Profiler(llm, memory).maybe_summarize(KEY) is False
    assert llm.payloads == []


async def test_the_next_summary_is_handed_the_one_before(memory):
    chatter(memory, SUMMARY_EVERY)
    llm = ScriptedLLM()
    await Profiler(llm, memory).maybe_summarize(KEY)

    chatter(memory, SUMMARY_EVERY)
    await Profiler(llm, memory).maybe_summarize(KEY)

    assert "marco aspetta la patch" in llm.payloads[1]


async def test_a_model_that_says_nothing_does_not_retry_every_turn(memory):
    chatter(memory, SUMMARY_EVERY)
    llm = ScriptedLLM({})
    profiler = Profiler(llm, memory)

    assert await profiler.maybe_summarize(KEY) is False
    assert await profiler.maybe_summarize(KEY) is False
    assert len(llm.payloads) == 1


# --- and read when she wakes up ----------------------------------------------


def test_the_morning_pass_finds_what_happened_last_time(memory):
    memory.conversations.save_summary(KEY, "marco aspetta la patch di minecraft")
    context = SimpleNamespace(memory=memory, consciousness=None, skill_registry=None,
                              history_manager=None, model_for=None)
    skill = DreamSkill(Config(), bus=None, expression=None, context=context)
    skill.initialize()
    skill.active = True

    skill.morning_pass()

    assert any("marco aspetta la patch" in f.text for f in memory.hot.active())


def test_a_summary_replaces_the_one_before_it(memory):
    memory.conversations.save_summary(KEY, "vecchia")
    memory.conversations.save_summary(KEY, "nuova")

    assert memory.conversations.summary(KEY) == "nuova"
    assert memory.db.scalar("SELECT COUNT(*) FROM summaries") == 1


def test_marking_a_summary_done_does_not_wipe_it(memory):
    """Two statements, one row: the bookkeeping must not blank the text."""
    chatter(memory, 5)
    memory.conversations.save_summary(KEY, "marco aspetta la patch")

    memory.conversations.mark_summarized(KEY)

    assert memory.conversations.summary(KEY) == "marco aspetta la patch"
    assert time.time() - float(memory.db.scalar(
        "SELECT updated_at FROM summaries WHERE conversation_key = ?", (KEY,))) < 5
