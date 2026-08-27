"""Things she means to do later.

A person says "I'll ask you how it went tomorrow" and then does. Without
somewhere to put an intention, Bea could only ever act inside the turn she was
already in — the moment the conversation ended, the thought was gone.
"""

import pytest

from src.core.memory.store import MemoryStore
from src.core.social.agenda import MAX_NOTE_CHARS, Agenda


@pytest.fixture
def agenda() -> Agenda:
    return MemoryStore(":memory:").agenda


# --- keeping an intention ----------------------------------------------------


def test_an_intention_is_kept(agenda):
    agenda.add("ask ema how the exam went", due_ts=100.0)
    assert [i.note for i in agenda.pending()] == ["ask ema how the exam went"]


def test_an_intention_knows_who_it_is_about(agenda):
    agenda.add("ask how it went", person_id="p1", due_ts=100.0)
    assert agenda.pending()[0].person_id == "p1"


def test_an_intention_can_name_the_conversation_it_belongs_to(agenda):
    agenda.add("say the thing", conversation_key="telegram:2", due_ts=100.0)
    assert agenda.pending()[0].conversation_key == "telegram:2"


def test_an_empty_intention_is_not_kept(agenda):
    assert agenda.add("   ", due_ts=100.0) is None
    assert agenda.pending() == []


def test_a_rambling_intention_is_cut_down(agenda):
    agenda.add("x" * (MAX_NOTE_CHARS + 500), due_ts=100.0)
    assert len(agenda.pending()[0].note) == MAX_NOTE_CHARS


# --- when it comes due -------------------------------------------------------


def test_nothing_is_due_before_its_time(agenda):
    agenda.add("later", due_ts=100.0)
    assert agenda.due(now=50.0) == []


def test_it_is_due_once_the_time_has_passed(agenda):
    agenda.add("now", due_ts=100.0)
    assert [i.note for i in agenda.due(now=101.0)] == ["now"]


def test_the_oldest_intention_comes_first(agenda):
    agenda.add("seconda", due_ts=90.0)
    agenda.add("prima", due_ts=50.0)
    assert [i.note for i in agenda.due(now=100.0)] == ["prima", "seconda"]


def test_something_done_does_not_come_back(agenda):
    item_id = agenda.add("una volta sola", due_ts=100.0)
    agenda.mark_done(item_id)
    assert agenda.due(now=101.0) == []
    assert agenda.pending() == []


def test_something_dropped_does_not_come_back(agenda):
    item_id = agenda.add("cambiato idea", due_ts=100.0)
    agenda.cancel(item_id)
    assert agenda.pending() == []


def test_an_intention_nobody_acted_on_expires(agenda):
    """A week-old reminder is not a plan any more, it is a haunting."""
    agenda.add("vecchia", due_ts=100.0)
    assert agenda.due(now=100.0 + 8 * 86400) == []


# --- what she is shown -------------------------------------------------------


def test_an_empty_agenda_renders_nothing(agenda):
    assert agenda.render() == ""


def test_the_agenda_renders_as_lines_she_can_read(agenda):
    agenda.add("chiedere a ema dell'esame", due_ts=100.0)
    rendered = agenda.render(now=50.0)
    assert "chiedere a ema dell'esame" in rendered
    assert "MEANT TO" in rendered.upper()


def test_only_a_few_are_ever_shown(agenda):
    for i in range(20):
        agenda.add(f"cosa {i}", due_ts=100.0 + i)
    assert agenda.render(now=50.0).count("\n") <= 7


def test_what_is_done_is_not_rendered(agenda):
    item_id = agenda.add("fatto", due_ts=100.0)
    agenda.mark_done(item_id)
    assert agenda.render(now=50.0) == ""


# --- the runner that acts on it ----------------------------------------------


class FakeConversations:
    def __init__(self):
        self.turns = []

    async def turn_now(self, key, perceptions, *, first=True, initiative=False, frame=""):
        self.turns.append({"key": key, "initiative": initiative, "frame": frame})


class FakeReach:
    def __init__(self, key: str = "telegram:2"):
        self.key = key
        self.calls = []

    def find(self, who):
        return None

    def channels(self, person_id):
        from src.core.social.reach import Channel

        platform, _, native = self.key.partition(":")
        self.calls.append(person_id)
        return [Channel(platform, native, "Ema", 0.0, True)]


def runner(agenda, conversations, reach=None):
    from src.core.social.agenda import AgendaRunner

    return AgendaRunner(agenda=agenda, conversations=conversations, reach=reach or FakeReach())


async def test_a_due_intention_opens_its_conversation(agenda):
    agenda.add("chiedile dell'esame", conversation_key="telegram:2", due_ts=100.0)
    talk = FakeConversations()
    assert await runner(agenda, talk).run_once(now=101.0) == 1
    assert talk.turns[0]["key"] == "telegram:2"
    assert talk.turns[0]["initiative"] is True


async def test_the_note_is_what_she_is_reminded_of(agenda):
    agenda.add("chiedile dell'esame", conversation_key="telegram:2", due_ts=100.0)
    talk = FakeConversations()
    await runner(agenda, talk).run_once(now=101.0)
    assert "chiedile dell'esame" in talk.turns[0]["frame"]


async def test_an_intention_about_a_person_finds_a_way_to_them(agenda):
    agenda.add("scrivile", person_id="p1", due_ts=100.0)
    talk = FakeConversations()
    await runner(agenda, talk, FakeReach("discord:dm-9")).run_once(now=101.0)
    assert talk.turns[0]["key"] == "discord:dm-9"


async def test_an_acted_intention_is_closed(agenda):
    agenda.add("una volta", conversation_key="telegram:2", due_ts=100.0)
    await runner(agenda, FakeConversations()).run_once(now=101.0)
    assert agenda.pending() == []


async def test_an_intention_with_nowhere_to_go_is_dropped_not_retried(agenda):
    """Otherwise it is tried again on every tick, forever."""
    agenda.add("scrivile", person_id="ignoto", due_ts=100.0)

    class NoWhere(FakeReach):
        def channels(self, person_id):
            return []

    talk = FakeConversations()
    assert await runner(agenda, talk, NoWhere()).run_once(now=101.0) == 0
    assert talk.turns == []
    assert agenda.pending() == []


async def test_nothing_due_costs_nothing(agenda):
    agenda.add("dopo", conversation_key="telegram:2", due_ts=999.0)
    talk = FakeConversations()
    assert await runner(agenda, talk).run_once(now=100.0) == 0
    assert talk.turns == []


async def test_one_failure_does_not_stop_the_rest(agenda):
    agenda.add("prima", conversation_key="telegram:1", due_ts=50.0)
    agenda.add("seconda", conversation_key="telegram:2", due_ts=60.0)

    class Flaky(FakeConversations):
        async def turn_now(self, key, perceptions, *, first=True, initiative=False, frame=""):
            if key == "telegram:1":
                raise RuntimeError("boom")
            await super().turn_now(key, perceptions, initiative=initiative, frame=frame)

    talk = Flaky()
    assert await runner(agenda, talk).run_once(now=101.0) == 1
    assert [t["key"] for t in talk.turns] == ["telegram:2"]
