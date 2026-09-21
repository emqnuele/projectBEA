"""The dashboard shows the stream, so a reload loses nothing.

`GET /history` used to read the session JSON, which only ever holds her own
lines: user rows lived in `useState` and vanished on refresh. It now reads
the stage stream — user lines and her stage replies, oldest first, in the
shape the frontend already renders. Other conversations never leak in, and
world rows stay stored without taking a speaker seat.
"""

import pytest

from src.core.memory.store import MemoryStore


@pytest.fixture
def memory():
    store = MemoryStore(":memory:")
    yield store
    store.close()


def test_user_lines_survive_a_reload(memory):
    memory.conversations.add(conversation_key="stage", role="user", kind="chat",
                             content="[user] ciao", platform="ui",
                             author_identity="ui:user", display_name="user",
                             surface="chat:ui", session_id="s1")
    memory.conversations.add(conversation_key="stage", role="bea", kind="voice",
                             content="ei, ciao", surface="stage", session_id="s1")
    memory.conversations.add(conversation_key="stage", role="user", kind="chat",
                             content="[user] come va", platform="ui",
                             author_identity="ui:user", display_name="user",
                             surface="chat:ui", session_id="s1")

    rows = memory.conversations.dashboard_history()

    assert [(r["role"], r["content"]) for r in rows] == [
        ("user", "[user] ciao"), ("assistant", "ei, ciao"), ("user", "[user] come va"),
    ]
    assert all(r["timestamp"] for r in rows)


def test_other_conversations_do_not_leak_into_the_dashboard(memory):
    memory.conversations.add(conversation_key="telegram:55", role="user", kind="chat",
                             content="[marco] segreto", platform="telegram",
                             channel_id="55", author_identity="telegram:7",
                             display_name="marco", surface="chat:telegram",
                             session_id="s1")
    memory.conversations.add(conversation_key="stage", role="user", kind="chat",
                             content="[user] ciao", platform="ui",
                             author_identity="ui:user", display_name="user",
                             surface="chat:ui", session_id="s1")

    rows = memory.conversations.dashboard_history()

    assert [r["content"] for r in rows] == ["[user] ciao"]


def test_world_rows_stay_stored_without_taking_a_speaker_seat(memory):
    memory.conversations.add(conversation_key="stage", role="world", kind="game",
                             content="died to a skeleton", surface="game:mc",
                             session_id="s1")
    memory.conversations.add(conversation_key="stage", role="user", kind="chat",
                             content="[user] ciao", platform="ui",
                             author_identity="ui:user", display_name="user",
                             surface="chat:ui", session_id="s1")

    rows = memory.conversations.dashboard_history()

    assert [r["content"] for r in rows] == ["[user] ciao"]
    assert memory.conversations.count("stage") == 2


def test_the_live_room_does_not_leak_into_the_dashboard(memory):
    """A call, a player in the game and a donation all route to `stage` too.

    Filtering on the conversation key alone put every one of them in the
    owner's private chat as though he had typed it.
    """
    memory.conversations.add(conversation_key="stage", role="user", kind="voice",
                             content="[luca] (spoken): oi", platform="discord",
                             author_identity="discord:77", display_name="luca",
                             surface="voice:discord", session_id="s1")
    memory.conversations.add(conversation_key="stage", role="user", kind="chat",
                             content="[Steve] vieni qui", platform="minecraft",
                             author_identity="minecraft:Steve", display_name="Steve",
                             surface="game:mc", session_id="s1")
    memory.conversations.add(conversation_key="stage", role="user", kind="chat",
                             content="[Anon] tieni 5 euro", platform="donation",
                             author_identity="donation:anon", display_name="Anon",
                             surface="donation", session_id="s1")
    memory.conversations.add(conversation_key="stage", role="user", kind="chat",
                             content="[user] ciao", platform="ui",
                             author_identity="ui:user", display_name="user",
                             surface="chat:ui", session_id="s1")

    rows = memory.conversations.dashboard_history()

    assert [r["content"] for r in rows] == ["[user] ciao"]
    assert memory.conversations.count("stage") == 4


def test_she_is_heard_in_the_dashboard_wherever_she_said_it(memory):
    """Her spoken lines stay: the dashboard is where she is answered from."""
    memory.conversations.add(conversation_key="stage", role="user", kind="chat",
                             content="[user] ciao", platform="ui",
                             author_identity="ui:user", display_name="user",
                             surface="chat:ui", session_id="s1")
    memory.conversations.add(conversation_key="stage", role="bea", kind="voice",
                             content="ei", surface="stage", session_id="s1")

    assert [r["role"] for r in memory.conversations.dashboard_history()] == [
        "user", "assistant"]


def test_the_route_falls_back_to_the_session_file_when_the_db_fails():
    from types import SimpleNamespace

    from src.web.routers.chat import get_history

    class BrokenConversations:
        def dashboard_history(self, limit=50):
            raise RuntimeError("disk gone")

    fallback = [{"role": "assistant", "content": "ei", "timestamp": "t"}]
    brain = SimpleNamespace(
        memory=SimpleNamespace(conversations=BrokenConversations()),
        history_manager=SimpleNamespace(
            get_recent_history=lambda limit=50: fallback),
    )

    assert get_history(brain) == fallback
