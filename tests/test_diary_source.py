"""The diary is written from what happened, not from what she answered.

It used to be generated from the session file, which held her replies and
nothing else — so a page about an evening on telegram was reconstructed from
one side of it, and any evening she mostly listened through produced a page
about nobody. It reads the same stream the consolidation reads.
"""

from types import SimpleNamespace

import pytest

from src.core.memory.db import Database
from src.core.memory.rag import Rag
from src.core.memory.store import MemoryStore
from src.core.skills.memory.memory import MemorySkill

SESSION = "session_tonight"


class Embedder:
    dim = 2

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class RecordingGenerator:
    def __init__(self):
        self.seen = []

    async def generate_diary(self, transcript):
        self.seen.append(transcript)
        return {"diary_content": "oggi marco mi ha parlato della patch",
                "tags": ["marco"], "user_id": "telegram:7"}


@pytest.fixture
def memory():
    store = MemoryStore(":memory:", embedder=Embedder(), min_similarity=0.2)
    yield store
    store.close()


def talked(memory, session=SESSION):
    add = memory.conversations.add
    add(conversation_key="telegram:55", role="user", kind="chat", surface="telegram",
        content="[marco] bea domani esce la patch", platform="telegram",
        author_identity="telegram:7", display_name="marco", session_id=session, ts=10.0)
    add(conversation_key="telegram:55", role="bea", kind="chat", surface="chat:telegram",
        content="ci gioco subito", platform="telegram", display_name="bea",
        session_id=session, ts=11.0)


def skill(memory) -> MemorySkill:
    config = SimpleNamespace(skills={"memory": {"enabled": True}})
    context = SimpleNamespace(memory=memory, history_manager=None)
    built = MemorySkill(config, None, None, context)
    built.initialize()
    built.generator = RecordingGenerator()
    built.active = True
    return built


async def test_the_page_is_written_from_both_sides_of_the_evening(memory):
    talked(memory)
    written = skill(memory)

    await written._process_session_async(SESSION)

    assert "[marco] bea domani esce la patch" in written.generator.seen[0]
    assert "you: ci gioco subito" in written.generator.seen[0]


async def test_a_page_is_saved_under_the_session_it_is_about(memory):
    talked(memory)
    written = skill(memory)

    await written._process_session_async(SESSION)

    assert memory.rag.exists("diary", SESSION)


async def test_a_sitting_nobody_spoke_in_gets_no_page(memory):
    memory.conversations.add(conversation_key="stage", role="world", kind="game",
                             content="hp=20", session_id=SESSION)
    written = skill(memory)

    await written._process_session_async(SESSION)

    assert written.generator.seen == []
    assert not memory.rag.exists("diary", SESSION)


def test_a_sitting_nobody_spoke_in_is_not_even_scheduled(memory):
    written = skill(memory)

    written.process_previous_session(SESSION)

    assert written._pending is None


async def test_the_sitting_is_read_once_per_page(memory):
    """The scheduler renders it to decide it is worth a page, and used to
    render it again inside the task: two full queries of the same rows, on
    the shutdown path where the clock is already short.
    """
    talked(memory)
    written = skill(memory)
    reads = []
    real = memory.conversations.stream

    def counted(session_id, *a, **k):
        reads.append(session_id)
        return real(session_id, *a, **k)

    memory.conversations.stream = counted

    written.process_previous_session(SESSION)
    await written._pending

    assert reads == [SESSION]
    assert len(written.generator.seen) == 1


def test_the_rag_is_all_the_skill_needs_to_write_one():
    """No history manager, no session file: the stream is the only input."""
    db = Database(":memory:").init()
    try:
        rag = Rag(db, Embedder(), min_similarity=0.2)
        assert rag.count("diary") == 0
    finally:
        db.close()
