"""The handoff recap survives the process that wrote it.

The window mirror holds entries, and the prose opening the next window is not
one: without a settings row a restart restores the evening without its head,
and the consolidation is the only event allowed to clear both.
"""

from types import SimpleNamespace

from src.core.consciousness import HANDOFF_PROSE_KEY, Consciousness
from src.core.memory.store import MemoryStore


def mind(memory):
    config = SimpleNamespace(consciousness={}, language="")
    return Consciousness(
        config=config, llm=None, bus=None, expression=None, surfaces=None,
        history_manager=SimpleNamespace(session_id="s1"), event_manager=None,
        soul_getter=lambda: "", operating_getter=lambda: "",
        memory=memory, profiler=None,
    )


def test_a_bridge_written_by_one_process_comes_back_in_the_next():
    memory = MemoryStore(":memory:")
    try:
        first = mind(memory)
        first._handoff.last_prose = "you talked about food for two hours"
        first._save_bridge()

        second = mind(memory)
        second._load_bridge()

        assert second._handoff.last_prose == "you talked about food for two hours"
    finally:
        memory.close()


def test_consolidation_clears_the_window_and_the_bridge():
    memory = MemoryStore(":memory:")
    try:
        consc = mind(memory)
        consc.sliding_window.append("user", "[user] ciao")
        consc._handoff.last_prose = "you talked about food"
        consc._save_bridge()

        consc.forget_window("")

        assert consc.sliding_window.entry_count() == 0
        assert consc._handoff.last_prose == ""
        assert memory.db.scalar(
            "SELECT value FROM settings WHERE key = ?", (HANDOFF_PROSE_KEY,),
            default="",
        ) == ""
    finally:
        memory.close()


def test_saving_an_empty_bridge_leaves_no_stale_row():
    memory = MemoryStore(":memory:")
    try:
        consc = mind(memory)
        consc._handoff.last_prose = "stale"
        consc._save_bridge()
        consc._handoff.last_prose = ""
        consc._save_bridge()

        assert memory.db.scalar(
            "SELECT COUNT(*) FROM settings WHERE key = ?", (HANDOFF_PROSE_KEY,),
        ) == 0
    finally:
        memory.close()
