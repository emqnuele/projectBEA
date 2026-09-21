"""The one sliding window outlives the process it was built in.

It is her working memory: what was said an hour ago, who she was answering,
which rooms are still alive. All of that used to live only in RAM, so a
restart left the follow-up gate blind and the next turn started from nothing.
It lives in RAM still — the turn never waits on the disk — and a flush after
each turn, plus a synchronous one at shutdown, is what carries it over. It is
emptied by exactly one event: the consolidation she does in her sleep.
"""

import pytest

from src.core.memory.store import MemoryStore
from src.core.mind.single_context import SingleContext
from src.core.mind.token_budget import TokenBudget


@pytest.fixture
def memory():
    store = MemoryStore(":memory:")
    yield store
    store.close()


def window(memory, **budget) -> SingleContext:
    return SingleContext(TokenBudget(**budget) if budget else None, store=memory.window)


def reopened(memory) -> SingleContext:
    """A window built by the next process against the same database."""
    fresh = window(memory)
    fresh.restore()
    return fresh


# --- it comes back ------------------------------------------------------------


def test_a_window_written_by_one_process_comes_back_in_the_next(memory):
    live = window(memory)
    live.append("user", "[marco] ciao", key="telegram:55", author="telegram:7")
    live.append("assistant", "ei marco", key="telegram:55", addressee="telegram:7")
    assert live.flush()

    after = reopened(memory)

    assert [m["content"] for m in after.messages()] == ["[marco] ciao", "ei marco"]


def test_the_conversation_tags_survive_the_restart(memory):
    live = window(memory)
    live.append("user", "[marco] ciao", key="telegram:55", author="telegram:7")
    live.append("assistant", "ei marco", key="telegram:55", addressee="telegram:7")
    live.flush()

    after = reopened(memory)

    assert after.live_keys() == ["telegram:55"]
    assert after.turns_for("telegram:55") == [
        {"role": "user", "identity": "telegram:7", "addressee": "", "content": "[marco] ciao"},
        {"role": "bea", "identity": "", "addressee": "telegram:7", "content": "ei marco"},
    ]
    assert after.seconds_since_bea("telegram:55") is not None


def test_the_next_entry_does_not_reuse_a_restored_sequence_number(memory):
    live = window(memory)
    live.append("user", "uno")
    live.append("user", "due")
    live.flush()

    after = reopened(memory)
    entry = after.append("user", "tre")

    assert entry.seq == 3


def test_the_budget_is_rebuilt_from_what_came_back(memory):
    live = window(memory)
    live.append("user", "qualcosa di abbastanza lungo da contare")
    live.flush()

    after = reopened(memory)

    assert after.total_tokens == live.total_tokens


# --- it stays in step ---------------------------------------------------------


def test_a_swap_replaces_what_is_stored_instead_of_adding_to_it(memory):
    live = window(memory)
    live.append("user", "vecchio")
    live.append("user", "recente")
    _, hot = live.snapshot_for_handoff()
    live.swap_with_snapshot("[EARLIER]\nvi siete parlati", hot)

    after = reopened(memory)

    assert [m["content"] for m in after.messages()] == [m["content"] for m in live.messages()]
    assert after.version == live.version


def test_what_the_valve_throws_away_is_thrown_away_on_disk_too(memory):
    live = window(memory, max_tokens=40, trigger_tokens=30, target_tokens=20)
    live.append("user", "x" * 200)
    live.append("user", "y" * 200)
    live.flush()

    after = reopened(memory)

    assert len(after) == len(live)
    assert [m["content"] for m in after.messages()] == [m["content"] for m in live.messages()]


# --- only sleeping empties it -------------------------------------------------


def test_clearing_the_window_clears_what_is_stored(memory):
    live = window(memory)
    live.append("user", "[marco] ciao", key="telegram:55")

    live.clear()

    assert reopened(memory).entry_count() == 0


def test_clearing_can_leave_the_bridge_the_consolidation_wrote(memory):
    live = window(memory)
    live.append("user", "[marco] ciao", key="telegram:55")

    live.clear(bridge="[EARLIER]\nhai parlato con marco della pizza")

    after = reopened(memory)
    assert [m["content"] for m in after.messages()] == [
        "[EARLIER]\nhai parlato con marco della pizza"]
    assert after.messages()[0]["role"] == "system"


def test_a_window_with_no_store_still_works(memory):
    live = SingleContext()
    live.append("user", "ciao")

    assert live.entry_count() == 1
    live.clear()
    assert live.entry_count() == 0


# --- the mind picks it up at start-up -----------------------------------------


async def test_the_mind_rebuilds_its_window_when_it_starts(memory):
    from tests.test_perception_log import build

    before = window(memory)
    before.append("user", "[marco] ciao", key="telegram:55", author="telegram:7")
    before.flush()

    mind, _bus, _memory = build(memory=memory)
    await mind.start()
    try:
        assert [m["content"] for m in mind.sliding_window.messages()] == ["[marco] ciao"]
    finally:
        await mind.stop()


async def test_a_fresh_mind_writes_its_window_where_the_next_one_looks(memory):
    from tests.test_perception_log import build

    mind, _bus, _memory = build(memory=memory)
    mind.sliding_window.append("user", "[marco] ciao", key="telegram:55")

    assert [r["content"] for r in memory.window.load()] == []
    await mind.stop()

    assert [r["content"] for r in memory.window.load()] == ["[marco] ciao"]
