"""The diary is a phase of the dream, and the shutdown save only a safety net.

A page used to be written only when a session rotated or the process shut
down. A boot opens a new sitting without rotating, so a run that did not
reach its shutdown save lost that evening's page for good, and the dream,
which reads every sitting anyway, never wrote one.
"""

from types import SimpleNamespace

import pytest

from src.core.brain import AIVtuberBrain
from src.core.memory.store import MemoryStore
from src.core.skills.dream.dreamer import Dreamer
from src.core.skills.dream.surface import DreamSkill
from src.core.skills.memory.memory import MemorySkill


class Config:
    timezone = ""
    language = ""

    def __init__(self):
        self.skills = {"memory": {"enabled": True}, "dream": {"enabled": True}}


class Pages:
    """The two calls the diary path makes on recall."""

    def __init__(self):
        self.written = []

    def exists(self, scope, key):
        return any(p["scope"] == scope and p["scope_key"] == key for p in self.written)

    def remember(self, **page):
        self.written.append(page)

    def keys(self):
        return [p["scope_key"] for p in self.written]


class Writer:
    def __init__(self):
        self.calls = 0

    async def generate_diary(self, transcript):
        self.calls += 1
        return {"diary_content": transcript, "tags": []}


class LLM:
    async def complete_json(self, user_input, system_prompt=None, history=None):
        return {"title": "una sera"}


class Registry:
    def __init__(self, **skills):
        self.skills = skills

    def get(self, name):
        return self.skills.get(name)


@pytest.fixture
def memory():
    store = MemoryStore(":memory:")
    store.rag = Pages()
    yield store
    store.close()


def talk(memory, session):
    for role, text in (("user", "[marco] ciao bea"), ("bea", "ciao marco")):
        memory.conversations.add(conversation_key="discord:1", role=role, content=text,
                                 display_name="marco" if role == "user" else "bea",
                                 author_identity="discord:7" if role == "user" else None,
                                 session_id=session)


def world(memory, session="s1", *, memory_on=True):
    """The brain as the two skills see it, rotation included."""
    counter = iter(range(2, 100))
    history = SimpleNamespace(session_id=session, set_session_title=lambda *a: True)

    def create_session():
        history.session_id = f"s{next(counter)}"

    history.create_session = create_session
    brain = SimpleNamespace(memory=memory, history_manager=history, consciousness=None)
    brain.create_new_session = lambda: AIVtuberBrain.create_new_session(brain)

    diary = MemorySkill(Config(), bus=None, expression=None, context=brain)
    diary.initialize()
    diary.generator = Writer()
    diary.active = memory_on
    brain.memory_skill = diary if memory_on else None
    brain.skill_registry = Registry(memory=diary if memory_on else None)

    dream = DreamSkill(Config(), bus=None, expression=None, context=brain)
    dream.initialize()
    dream.active = True
    dream.dreamer = Dreamer(llm=LLM(), history_manager=history, roster=memory.roster,
                            people=memory.people, selflore=memory.selflore,
                            recent=memory.hot, sessions=memory.sessions,
                            conversations=memory.conversations)
    return SimpleNamespace(history=history, diary=diary, dream=dream)


async def test_every_sitting_the_dream_reads_has_its_page_before_she_wakes(memory):
    talk(memory, "s0")
    talk(memory, "s1")
    w = world(memory)

    summary = await w.dream.run_dream()

    assert sorted(memory.rag.keys()) == ["s0", "s1"]
    assert summary["pages"] == 2
    assert w.diary._writing == set()


async def test_a_sitting_a_crash_left_without_a_page_gets_it_from_the_dream(memory):
    talk(memory, "s_crashed")
    w = world(memory, session="s_next")

    await w.dream.run_dream()

    assert "s_crashed" in memory.rag.keys()


async def test_the_shutdown_after_a_dream_writes_nothing_when_she_was_quiet(memory):
    talk(memory, "s1")
    w = world(memory)

    await w.dream.run_dream()
    await w.diary.save_all_pending()

    assert memory.rag.keys() == ["s1"]
    assert w.diary.generator.calls == 1


async def test_the_shutdown_after_a_dream_still_writes_what_came_after(memory):
    talk(memory, "s1")
    w = world(memory)

    await w.dream.run_dream()
    talk(memory, w.history.session_id)
    await w.diary.save_all_pending()

    assert memory.rag.keys() == ["s1", w.history.session_id]


async def test_a_page_already_written_is_not_written_again(memory):
    talk(memory, "s1")
    w = world(memory)
    w.diary.save_current_session()
    await next(iter(w.diary._writing))

    summary = await w.dream.run_dream()

    assert summary["pages"] == 0
    assert w.diary.generator.calls == 1


async def test_without_the_memory_skill_the_dream_still_runs(memory):
    talk(memory, "s1")
    w = world(memory, memory_on=False)

    summary = await w.dream.run_dream()

    assert summary["ok"] is True and summary["pages"] == 0
    assert "s1" in memory.sessions.dreamed()


async def test_a_nap_is_on_the_dashboard_but_does_not_count_as_the_night(memory):
    talk(memory, "s1")
    w = world(memory)

    await w.dream.run_dream()

    assert w.dream.last_night() != ""
    assert w.dream._dreamed_tonight() is False


async def test_a_dream_with_no_model_leaves_the_date_alone(memory):
    w = world(memory)
    w.dream.dreamer.llm = None

    await w.dream.run_dream()

    assert w.dream.last_night() == ""
