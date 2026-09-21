"""What she does in her sleep, and what she reads while doing it.

The consolidation used to read the session files on disk, which only ever held
her own replies, and it skipped the session it was standing in. Both together
meant that a night of telegram consolidated into nothing at all: she woke up
with no cards, no facts and the same context she went to bed with.

It reads the stream now, one session at a time, segmented by conversation so a
DM with marco and a death in minecraft are not one flat pile. The session she
is in is the one that matters most, so it goes last and is followed by a fresh
one and an empty window.
"""

import asyncio
from types import SimpleNamespace

import pytest

from src.core.memory.store import MemoryStore
from src.core.memory.transcript import render_stream
from src.core.skills.dream.dreamer import Dreamer
from src.core.skills.dream.surface import DreamSkill

SESSION = "session_tonight"


class Config:
    def __init__(self, **dream):
        self.skills = {"dream": {"enabled": True, **dream}}
        self.language = ""


class ScriptedLLM:
    """Bea's subconscious, replaced by a fixed answer and a transcript log."""

    def __init__(self, reply=None):
        self.reply = reply or {"title": "una sera con marco", "self_facts": [],
                               "people": [], "hot_facts": [], "profile": {}}
        self.seen = []

    async def complete_json(self, user_input, system_prompt=None, history=None):
        self.seen.append(user_input)
        return dict(self.reply)


class History:
    def __init__(self, session_id=SESSION):
        self.session_id = session_id
        self.titled = []
        self.sessions = [session_id]

    def set_session_title(self, session_id, title):
        self.titled.append((session_id, title))
        return True

    def create_session(self):
        self.session_id = f"session_{len(self.sessions) + 1}"
        self.sessions.append(self.session_id)


class Mind:
    def __init__(self):
        self.sleeping = False
        self.forgotten = []

    def sleep(self, reason=""):
        self.sleeping = True

    def wake(self):
        self.sleeping = False

    def forget_window(self, bridge=""):
        self.forgotten.append(bridge)


@pytest.fixture
def memory():
    store = MemoryStore(":memory:")
    yield store
    store.close()


def talked(memory, session=SESSION):
    """One evening: a DM with marco, and minecraft going on in the background."""
    add = memory.conversations.add
    add(conversation_key="telegram:55", role="user", kind="chat", surface="telegram",
        content="[marco] bea domani esce la patch", platform="telegram",
        author_identity="telegram:7", display_name="marco", session_id=session, ts=10.0)
    add(conversation_key="telegram:55", role="bea", kind="chat", surface="chat:telegram",
        content="ci gioco subito", platform="telegram", display_name="bea",
        session_id=session, ts=11.0)
    add(conversation_key="stage", role="world", kind="game", surface="game:mc",
        content="You died to a Skeleton at -120 64 33", session_id=session, ts=12.0)
    add(conversation_key="stage", role="bea", kind="voice", surface="stage",
        content="ma vaffanculo lo scheletro", display_name="bea",
        session_id=session, ts=13.0)


def dreamer(memory, llm, history) -> Dreamer:
    return Dreamer(llm=llm, history_manager=history, roster=memory.roster,
                   people=memory.people, selflore=memory.selflore, recent=memory.hot,
                   sessions=memory.sessions, conversations=memory.conversations)


# --- what the consolidation reads --------------------------------------------


def test_the_transcript_is_segmented_by_conversation(memory):
    talked(memory)

    text = render_stream(memory.conversations.stream(SESSION))

    assert "telegram:55" in text and "stage" in text
    assert text.index("telegram:55") < text.index("[marco]")
    assert "[marco] bea domani esce la patch" in text


def test_what_happened_with_nobody_behind_it_is_in_the_transcript(memory):
    talked(memory)

    text = render_stream(memory.conversations.stream(SESSION))

    assert "(game) You died to a Skeleton at -120 64 33" in text


def test_her_own_lines_are_marked_as_hers(memory):
    talked(memory)

    text = render_stream(memory.conversations.stream(SESSION))

    assert "you: ci gioco subito" in text


# --- the evening she just lived ----------------------------------------------


async def test_the_session_she_is_in_is_consolidated(memory):
    talked(memory)
    llm = ScriptedLLM()

    result = await dreamer(memory, llm, History()).run()

    assert result["sessions"] == 1
    assert SESSION in memory.sessions.dreamed()
    assert "[marco] bea domani esce la patch" in llm.seen[0]


async def test_a_session_with_almost_nothing_costs_no_model_call(memory):
    memory.conversations.add(conversation_key="stage", role="world", kind="system",
                             content="started", session_id="session_empty")
    llm = ScriptedLLM()

    await dreamer(memory, llm, History("session_other")).run()

    assert llm.seen == []
    assert "session_empty" in memory.sessions.dreamed()


async def test_a_session_is_never_consolidated_twice(memory):
    talked(memory)
    llm = ScriptedLLM()

    await dreamer(memory, llm, History()).run()
    await dreamer(memory, llm, History()).run()

    assert len(llm.seen) == 1


# --- waking up ----------------------------------------------------------------


def _skill(memory, mind, history, llm) -> DreamSkill:
    def create_new_session():
        """What the brain does: a new file, and the session on the record."""
        history.create_session()
        memory.sessions.record(history.session_id)

    context = SimpleNamespace(memory=memory, consciousness=mind, skill_registry=None,
                              history_manager=history, model_for=lambda _r: llm,
                              create_new_session=create_new_session)
    skill = DreamSkill(Config(), bus=None, expression=None, context=context)
    skill.initialize()
    skill.active = True
    skill.dreamer = dreamer(memory, llm, history)
    return skill


async def test_she_wakes_up_with_an_empty_window(memory):
    talked(memory)
    mind, history = Mind(), History()
    skill = _skill(memory, mind, history, ScriptedLLM())

    await skill.run_dream()

    assert mind.forgotten == [""]


async def test_the_dream_hands_the_next_window_what_to_carry(memory):
    talked(memory)
    mind, history = Mind(), History()
    llm = ScriptedLLM({"title": "una sera", "carry_over": "marco aspetta la patch",
                       "self_facts": [], "people": [], "hot_facts": []})
    skill = _skill(memory, mind, history, llm)

    await skill.run_dream()

    assert mind.forgotten == ["[EARLIER]\nmarco aspetta la patch"]


async def test_she_wakes_up_in_a_new_session(memory):
    talked(memory)
    mind, history = Mind(), History()
    skill = _skill(memory, mind, history, ScriptedLLM())

    await skill.run_dream()

    assert history.session_id != SESSION
    assert memory.sessions.started_at(history.session_id) is not None


async def test_nothing_to_consolidate_still_starts_her_over(memory):
    mind, history = Mind(), History()
    skill = _skill(memory, mind, history, ScriptedLLM())

    await skill.run_dream()

    assert history.session_id != SESSION
    assert mind.sleeping is False


def test_the_event_loop_is_not_needed_to_render(memory):
    """Rendering is pure: no clock, no io, no loop."""
    talked(memory)
    assert asyncio.iscoroutinefunction(render_stream) is False
