"""Long-term memory is more than one page a night.

The schema has always declared three scopes — `diary`, `conversation` and
`person` — and only the first was ever written or read. So everything she
could recall was one page per session, written from her own replies: three
memories in three months. The consolidation now writes a recap per
conversation and a note per person as well, and recall reaches all three.
"""

from types import SimpleNamespace

import pytest

from src.core.memory.store import MemoryStore
from src.core.skills.dream.dreamer import Dreamer
from src.core.skills.memory.memory import MemorySkill

SESSION = "session_tonight"


class Embedder:
    dim = 2

    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class ScriptedLLM:
    def __init__(self, reply):
        self.reply = reply

    async def complete_json(self, user_input, system_prompt=None, history=None):
        return dict(self.reply)


class History:
    session_id = SESSION

    def set_session_title(self, session_id, title):
        return True


@pytest.fixture
def memory():
    store = MemoryStore(":memory:", embedder=Embedder(), min_similarity=0.0)
    yield store
    store.close()


def talked(memory):
    add = memory.conversations.add
    add(conversation_key="telegram:55", role="user", kind="chat", surface="telegram",
        content="[marco] bea domani esce la patch", platform="telegram",
        author_identity="telegram:7", display_name="marco", session_id=SESSION, ts=10.0)
    add(conversation_key="telegram:55", role="bea", kind="chat", surface="chat:telegram",
        content="ci gioco subito", platform="telegram", display_name="bea",
        session_id=SESSION, ts=11.0)


def dreamer(memory, reply) -> Dreamer:
    return Dreamer(llm=ScriptedLLM(reply), history_manager=History(),
                   roster=memory.roster, people=memory.people, selflore=memory.selflore,
                   recent=memory.hot, sessions=memory.sessions,
                   conversations=memory.conversations, rag=memory.rag)


def skill(memory) -> MemorySkill:
    config = SimpleNamespace(skills={"memory": {"enabled": True}})
    built = MemorySkill(config, None, None, SimpleNamespace(memory=memory))
    built.initialize()
    built.active = True
    return built


# --- what the consolidation writes -------------------------------------------


async def test_a_recap_is_kept_per_conversation(memory):
    talked(memory)
    await dreamer(memory, {
        "title": "una sera",
        "conversations": [{"key": "telegram:55",
                           "recap": "marco ti ha detto che la patch esce domani"}],
    }).run()

    assert memory.rag.exists("conversation", "telegram:55")


async def test_what_she_learned_about_someone_is_recallable(memory):
    talked(memory)
    await dreamer(memory, {
        "title": "una sera",
        "people": [{"name": "marco", "facts": ["aspetta la patch di minecraft"],
                    "attitude": "ci vai d'accordo"}],
    }).run()

    assert memory.rag.count("person") == 1


async def test_a_recap_for_a_conversation_nobody_named_is_skipped(memory):
    talked(memory)
    await dreamer(memory, {
        "title": "una sera",
        "conversations": [{"key": "", "recap": "qualcosa"}],
    }).run()

    assert memory.rag.count("conversation") == 0


async def test_a_consolidation_without_a_rag_still_runs(memory):
    talked(memory)
    blind = Dreamer(llm=ScriptedLLM({"title": "una sera"}), history_manager=History(),
                    roster=memory.roster, people=memory.people, selflore=memory.selflore,
                    recent=memory.hot, sessions=memory.sessions,
                    conversations=memory.conversations)

    result = await blind.run()

    assert result["ok"] is True


# --- what recall reads --------------------------------------------------------


def test_recall_reaches_every_scope(memory):
    memory.rag.remember(scope="diary", scope_key="s1",
                        text="oggi ho parlato con marco della patch")
    memory.rag.remember(scope="conversation", scope_key="telegram:55",
                        text="con marco su telegram parlate di minecraft")
    memory.rag.remember(scope="person", scope_key="p1",
                        text="marco aspetta la patch di minecraft")

    found = skill(memory).retrieve_context("marco patch minecraft", limit=5)

    assert "oggi ho parlato con marco della patch" in found
    assert "con marco su telegram parlate di minecraft" in found
    assert "marco aspetta la patch di minecraft" in found


def test_recall_still_answers_when_only_the_diary_has_anything(memory):
    memory.rag.remember(scope="diary", scope_key="s1", text="una sera tranquilla in chat")

    found = skill(memory).retrieve_context("una sera", limit=3)

    assert "una sera tranquilla in chat" in found


def test_recall_keeps_her_own_lines_in_their_own_block(memory):
    memory.rag.remember(scope="conversation", scope_key="telegram:55",
                        text="le hai detto che sei nata in un server minecraft",
                        source="bea")

    found = skill(memory).retrieve_context("dove sei nata", limit=3)

    assert "THINGS YOU SAID BEFORE" in found
