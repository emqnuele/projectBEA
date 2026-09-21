"""What the dream wrote can be read back without a semantic query.

Recall answers "what was said about x". The diary, the per-conversation
recaps and the per-person notes also need "what is written down at all" —
newest first, one scope at a time — which is what the dashboard's diary
screen reads. And recall results carry the scope they came from, so the UI
can label a diary page apart from a recap apart from a note.
"""

from types import SimpleNamespace

import pytest

from src.core.memory.store import MemoryStore
from src.web.routers.memory import memory_browse, memory_search


class Embedder:
    dim = 2

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture
def memory():
    store = MemoryStore(":memory:", embedder=Embedder(), min_similarity=0.0)
    yield store
    store.close()


def brain_with(memory):
    return SimpleNamespace(memory=memory)


def test_browse_returns_one_scope_newest_first(memory):
    memory.rag.remember(scope="diary", scope_key="s1", text="prima sera")
    memory.rag.remember(scope="diary", scope_key="s2", text="seconda sera")
    memory.rag.remember(scope="person", scope_key="p1", text="marco: aspetta la patch")

    pages = memory.rag.browse("diary")

    assert [p.text for p in pages] == ["seconda sera", "prima sera"]
    assert all(p.scope == "diary" for p in pages)


def test_browse_caps_how_much_it_reads(memory):
    for i in range(5):
        memory.rag.remember(scope="diary", scope_key=f"s{i}",
                            text=f"la sera numero {i} in chat con marco e gli altri")

    assert len(memory.rag.browse("diary", limit=3)) == 3


def test_recall_carries_the_scope_it_came_from(memory):
    memory.rag.remember(scope="conversation", scope_key="telegram:55",
                        text="con marco parlate di minecraft")

    facts, _ = memory.rag.recall_split("marco minecraft", k=5)

    assert facts and facts[0].scope == "conversation"
    assert facts[0].scope_key == "telegram:55"


def test_the_route_reads_one_scope(memory):
    memory.rag.remember(scope="diary", scope_key="s1", text="una sera tranquilla")

    rows = memory_browse("diary", 20, brain_with(memory))

    assert [r["text"] for r in rows] == ["una sera tranquilla"]
    assert rows[0]["scope"] == "diary"


def test_the_route_refuses_an_unknown_scope(memory):
    with pytest.raises(Exception, match="Unknown scope"):
        memory_browse("sogni", 20, brain_with(memory))


def test_the_route_needs_the_memory_skill():
    brain = SimpleNamespace(memory=SimpleNamespace(rag=None))

    with pytest.raises(Exception, match="memory skill"):
        memory_browse("diary", 20, brain)


def test_search_results_name_their_scope(memory):
    memory.rag.remember(scope="person", scope_key="p1", text="marco aspetta la patch")

    found = memory_search("marco patch", 5, brain_with(memory))

    assert found["facts"] and found["facts"][0]["scope"] == "person"
