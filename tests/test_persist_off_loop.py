"""The disk never stands between her and the conversation.

The window lives in RAM while she talks: appends only mark it dirty, and a
flush after each turn — plus a synchronous one at shutdown — carries it over
in a single transaction. The stream lands in one transaction per drain, not
one per row. And recall embeds the question once no matter how many scopes it
asks, skips silence entirely, and never holds a turn hostage.
"""

import asyncio
import time
from types import SimpleNamespace

import pytest

from src.core.memory.store import MemoryStore
from src.core.mind.single_context import SingleContext
from src.core.mind.token_budget import TokenBudget
from src.core.perception.types import Perception, PerceptionKind
from src.core.skills.base import Skill
from src.core.skills.memory.memory import MemorySkill


class CountingEmbedder:
    dim = 2

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture
def memory():
    store = MemoryStore(":memory:", embedder=CountingEmbedder(), min_similarity=0.0)
    yield store
    store.close()


def window(memory, **budget) -> SingleContext:
    return SingleContext(TokenBudget(**budget) if budget else None, store=memory.window)


def skill(memory) -> MemorySkill:
    config = SimpleNamespace(skills={"memory": {"enabled": True}})
    built = MemorySkill(config, None, None, SimpleNamespace(memory=memory))
    built.initialize()
    built.active = True
    return built


# --- the stream lands once per drain -----------------------------------------


def test_a_drained_batch_is_written_in_one_transaction(memory):
    n = memory.conversations.add_many([
        {"conversation_key": "stage", "role": "user", "content": f"riga {i}",
         "session_id": "s1", "ts": float(i)} for i in range(5)
    ])

    assert n == 5
    assert memory.conversations.count("stage") == 5


def test_an_empty_batch_writes_nothing(memory):
    assert memory.conversations.add_many([]) == 0


# --- the window is ram first --------------------------------------------------


def test_appends_do_not_touch_the_disk(memory):
    live = window(memory)
    live.append("user", "[marco] ciao", key="telegram:55")

    assert live.needs_flush
    assert memory.window.load() == []


def test_flush_carries_it_over_and_clears_the_flag(memory):
    live = window(memory)
    live.append("user", "[marco] ciao", key="telegram:55")

    assert live.flush() is True
    assert not live.needs_flush
    assert [r["content"] for r in memory.window.load()] == ["[marco] ciao"]
    assert live.flush() is False


def test_a_stale_background_flush_loses_to_a_swap(memory):
    live = window(memory)
    live.append("user", "vecchio")
    rows, version, write_seq = live.flush_snapshot()

    live.swap("[EARLIER]\nvi siete parlati")

    assert memory.window.replace(rows, version, write_seq=write_seq) is False
    assert [r["content"] for r in memory.window.load()] == [
        m["content"] for m in live.messages()]


def test_a_stale_flush_loses_even_without_a_swap(memory):
    """Two flushes of the SAME version, landing out of order.

    `version` only moves on a swap or a clear, so a guard on it cannot tell
    these two apart — which is how an orphaned background write could land
    its older rows on top of the shutdown flush and lose the last turns.
    """
    live = window(memory)
    live.append("user", "primo")
    stale = live.flush_snapshot()

    live.append("user", "secondo")
    fresh = live.flush_snapshot()

    assert stale[1] == fresh[1], "the version must not have moved"

    rows, version, write_seq = fresh
    assert memory.window.replace(rows, version, write_seq=write_seq) is True

    rows, version, write_seq = stale
    assert memory.window.replace(rows, version, write_seq=write_seq) is False
    assert [r["content"] for r in memory.window.load()] == ["primo", "secondo"]


def test_the_write_sequence_keeps_rising_across_a_restart(memory):
    lived = window(memory)
    lived.append("user", "ieri sera")
    lived.flush()

    woken = window(memory)
    woken.restore()
    woken.append("user", "stamattina")

    assert woken.flush() is True
    assert [r["content"] for r in memory.window.load()] == ["ieri sera", "stamattina"]


def test_a_window_with_no_store_never_needs_a_flush():
    live = SingleContext()
    live.append("user", "ciao")

    assert not live.needs_flush
    assert live.flush() is False


# --- the mind persists behind the turn ----------------------------------------


async def test_a_turn_carries_the_window_over_without_waiting(memory):
    from tests.test_perception_log import build, marco, one_turn

    mind, bus, _memory = build(memory=memory)
    bus.put(marco())
    await one_turn(mind)

    await asyncio.gather(*list(mind._bg_tasks), return_exceptions=True)

    assert [r["content"] for r in memory.window.load()] != []


async def test_stopping_flushes_what_no_turn_carried_yet(memory):
    from tests.test_perception_log import build

    mind, _bus, _memory = build(memory=memory)
    mind.sliding_window.append("user", "[marco] ciao", key="telegram:55")

    await mind.stop()

    assert [r["content"] for r in memory.window.load()] == ["[marco] ciao"]


# --- recall spends the model once ----------------------------------------------


def test_recall_embeds_the_question_once_for_all_scopes(memory):
    text = skill(memory).retrieve_context("ciao bea, parliamo di minecraft")

    assert text == ""
    assert memory.rag.embedder.calls == 1


def test_silence_asks_the_past_nothing(memory):
    built = skill(memory)
    idle = Perception(PerceptionKind.IDLE, "loop", "")

    assert built.context_for([idle]) is None
    assert memory.rag.embedder.calls == 0


# --- a hung disk never holds the conversation -----------------------------------


class SlowSkill(Skill):
    name = "slow"

    def context_for(self, batch):
        time.sleep(3)
        return "SLOW BLOCK"


async def test_a_hung_retrieval_answers_without_it(memory):
    from tests.test_perception_log import build, marco

    mind, _bus, _memory = build(memory=memory)
    slow = SlowSkill(mind.config, None, None)
    slow.active = True
    mind.surfaces.register(slow)
    mind._dynamic_timeout = 0.05

    started = time.monotonic()
    briefing = await mind._build_briefing([marco()], is_idle=False)
    elapsed = time.monotonic() - started

    assert elapsed < 2.0
    assert "SLOW BLOCK" not in briefing["content"]
