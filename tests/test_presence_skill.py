"""The tools that make her a person rather than a chat endpoint.

She can look someone up, write to them wherever they are, decide to come back
to it later, and walk out of a call. All four are things a person does and a
bot usually cannot.
"""

import time

import pytest

from src.core.memory.store import MemoryStore
from src.core.skills.base import SkillRegistry
from src.core.skills.platform import PlatformSkill
from src.core.skills.presence.surface import PresenceSkill


class Config:
    def __init__(self, **rhythm):
        self.skills = {}
        self.attention = {}
        self.rhythm = {"cross_platform": True, **rhythm}


class Recorder(PlatformSkill):
    def __init__(self, platform: str):
        super().__init__(Config(), bus=None, expression=None)
        self.name = f"chat:{platform}"
        self.skill_name = platform
        self.platform = platform
        self.dms = []
        self.initialize()
        self.humanizer._sleep = _instant
        self.active = True

    async def send_text(self, channel_id, text, reply_to=None):
        return True

    async def send_dm(self, native_id, text):
        self.dms.append((native_id, text))
        return native_id


async def _instant(seconds):
    return None


class Context:
    """Shaped like the brain, which is what a skill actually receives."""

    def __init__(self, memory, surfaces):
        self.memory = memory
        self.surface_registry = surfaces


@pytest.fixture
def memory():
    return MemoryStore(":memory:")


def _person(memory, name, *identities):
    for identity in identities:
        platform, _, _native = identity.partition(":")
        memory.roster.record(identity=identity, display_name=name, platform=platform)
    card = memory.people.create_from_entry(memory.roster.get(identities[0]))
    for identity in identities[1:]:
        memory.people.link_identity(card.person_id, identity)
    return card.person_id


def skill(memory, *platforms, **rhythm) -> PresenceSkill:
    registry = SkillRegistry()
    for platform in platforms:
        registry.register(Recorder(platform))
    s = PresenceSkill(Config(**rhythm), bus=None, expression=None,
                      context=Context(memory, registry))
    s.initialize()
    s.active = True
    return s


def tool(s: PresenceSkill, name: str):
    return next(t for t in s.tools() if t.name == name)


async def call(s: PresenceSkill, name: str, **kwargs) -> str:
    return await tool(s, name).handler(**kwargs)


# --- what she is given -------------------------------------------------------


def test_she_has_the_tools_a_person_needs(memory):
    names = {t.name for t in skill(memory, "telegram").tools()}
    assert {"message_person", "where_can_i_reach", "remember_to"} <= names


def test_an_inactive_skill_offers_nothing(memory):
    s = skill(memory, "telegram")
    s.active = False
    assert s.tools() == []


def test_reaching_across_platforms_can_be_switched_off(memory):
    names = {t.name for t in skill(memory, "telegram", cross_platform=False).tools()}
    assert "message_person" not in names
    assert "remember_to" in names


# --- looking someone up ------------------------------------------------------


async def test_she_can_ask_where_someone_is(memory):
    _person(memory, "Ema", "telegram:2", "discord:1")
    answer = await call(skill(memory, "telegram"), "where_can_i_reach", who="Ema")
    assert "telegram" in answer
    assert "discord" in answer


async def test_asking_about_a_stranger_says_so(memory):
    answer = await call(skill(memory, "telegram"), "where_can_i_reach", who="nessuno")
    assert "don't know" in answer.lower()


# --- writing to them ---------------------------------------------------------


async def test_she_can_write_to_someone_on_another_platform(memory):
    _person(memory, "Ema", "telegram:2")
    s = skill(memory, "telegram")
    answer = await call(s, "message_person", who="Ema", text="ehi, tutto bene?")
    telegram = s.context.surface_registry.get("chat:telegram")
    assert telegram.dms == [("2", "ehi, tutto bene?")]
    assert "telegram" in answer.lower()


async def test_writing_to_a_stranger_fails_out_loud(memory):
    answer = await call(skill(memory, "telegram"), "message_person",
        who="nessuno", text="ciao")
    assert answer.startswith("FAILED")


async def test_she_may_pick_the_platform_herself(memory):
    _person(memory, "Ema", "telegram:2", "discord:1")
    s = skill(memory, "telegram", "discord")
    await call(s, "message_person", who="Ema", text="ciao", platform="discord")
    assert s.context.surface_registry.get("chat:discord").dms == [("1", "ciao")]


# --- deciding to come back to it ---------------------------------------------


async def test_she_can_decide_to_do_something_later(memory):
    answer = await call(skill(memory, "telegram"), "remember_to",
        what="chiedere a ema com'è andato l'esame", in_minutes=60)
    assert memory.agenda.pending()[0].note == "chiedere a ema com'è andato l'esame"
    assert "FAILED" not in answer


async def test_the_reminder_is_due_when_she_said(memory):
    before = time.time()
    await call(skill(memory, "telegram"), "remember_to", what="x", in_minutes=30)
    due = memory.agenda.pending()[0].due_ts
    assert before + 1740 <= due <= before + 1860


async def test_a_reminder_about_a_person_is_attached_to_them(memory):
    pid = _person(memory, "Ema", "telegram:2")
    await call(skill(memory, "telegram"), "remember_to",
        what="chiedile dell'esame", in_minutes=10, who="Ema")
    assert memory.agenda.pending()[0].person_id == pid


async def test_a_reminder_about_a_stranger_is_refused(memory):
    answer = await call(skill(memory, "telegram"), "remember_to",
        what="x", in_minutes=10, who="nessuno")
    assert answer.startswith("FAILED")
    assert memory.agenda.pending() == []


async def test_a_reminder_in_the_past_is_refused(memory):
    answer = await call(skill(memory, "telegram"), "remember_to",
        what="x", in_minutes=-5)
    assert answer.startswith("FAILED")


async def test_she_cannot_fill_her_own_head_with_reminders(memory):
    s = skill(memory, "telegram")
    for i in range(30):
        await call(s, "remember_to", what=f"cosa {i}", in_minutes=10)
    assert len(memory.agenda.pending()) <= 20


# --- what she is reminded of -------------------------------------------------


def test_what_she_meant_to_do_reaches_her_context(memory):
    memory.agenda.add("chiedere a ema dell'esame", due_ts=time.time() + 600)
    assert "chiedere a ema dell'esame" in skill(memory, "telegram").live_state()


def test_an_empty_agenda_adds_nothing_to_her_context(memory):
    assert skill(memory, "telegram").live_state() is None


# --- the shape the brain actually hands it -----------------------------------


def test_it_initializes_against_what_the_brain_really_exposes(memory):
    """The brain passes itself as context, and it calls its registry
    `surface_registry`. Reaching for a name it does not have is an
    AttributeError at startup, on a core skill."""
    from src.core.brain import AIVtuberBrain

    assert hasattr(AIVtuberBrain, "surface_registry")

    class BrainShaped:
        def __init__(self, mem):
            self.memory = mem
            self.surface_registry = SkillRegistry()

    s = PresenceSkill(Config(), bus=None, expression=None, context=BrainShaped(memory))
    s.initialize()
    s.active = True
    assert {t.name for t in s.tools()} >= {"remember_to", "message_person"}


async def test_the_registry_it_holds_stays_live(memory):
    """Skills register one after another, so it must hold the registry itself
    and not a snapshot of who was in it at startup."""
    class BrainShaped:
        def __init__(self, mem):
            self.memory = mem
            self.surface_registry = SkillRegistry()

    brain = BrainShaped(memory)
    s = PresenceSkill(Config(), bus=None, expression=None, context=brain)
    s.initialize()
    s.active = True

    _person(memory, "Ema", "telegram:2")
    brain.surface_registry.register(Recorder("telegram"))
    assert await call(s, "message_person", who="Ema", text="ciao") == "Written to Ema on telegram."
