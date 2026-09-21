"""A sitting too long to read whole says so.

One consolidation reads at most `STREAM_LIMIT` rows and keeps the most recent,
so a long night in the game loses its beginning. Nothing is wrong with the cap
— the pass has a context window of its own — but a hole in a memory that
nobody is told about is how "she forgot the whole first half" looks from the
outside, so it is logged rather than truncated quietly.
"""

import logging

import pytest

from src.core.memory.store import STREAM_LIMIT, MemoryStore


@pytest.fixture
def memory():
    store = MemoryStore(":memory:")
    yield store
    store.close()


def sitting(memory, session_id: str, rows: int = 3) -> None:
    memory.conversations.add_many([
        {"conversation_key": "stage", "role": "user", "content": f"{session_id}-{i}",
         "surface": "chat:ui", "session_id": session_id, "ts": float(i)}
        for i in range(rows)
    ])


def test_a_long_sitting_keeps_its_most_recent_lines(memory):
    memory.conversations.add_many([
        {"conversation_key": "stage", "role": "user", "content": f"riga {i}",
         "surface": "chat:ui", "session_id": "lunga", "ts": float(i)}
        for i in range(STREAM_LIMIT + 50)
    ])

    rows = memory.conversations.stream("lunga")

    assert len(rows) == STREAM_LIMIT
    assert rows[-1]["content"] == f"riga {STREAM_LIMIT + 49}"
    assert memory.conversations.stream_overflow("lunga") == 50


def test_a_sitting_too_long_to_read_whole_says_so(memory, caplog):
    memory.conversations.add_many([
        {"conversation_key": "stage", "role": "user", "content": f"riga {i}",
         "surface": "chat:ui", "session_id": "lunga", "ts": float(i)}
        for i in range(STREAM_LIMIT + 1)
    ])

    with caplog.at_level(logging.WARNING, logger="bea.memory.store"):
        memory.conversations.stream("lunga")

    assert any("lunga" in r.message for r in caplog.records)


def test_a_sitting_that_fits_says_nothing(memory, caplog):
    sitting(memory, "corta", rows=5)

    with caplog.at_level(logging.WARNING, logger="bea.memory.store"):
        memory.conversations.stream("corta")

    assert caplog.records == []
    assert memory.conversations.stream_overflow("corta") == 0
