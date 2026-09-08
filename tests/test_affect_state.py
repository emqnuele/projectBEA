"""The standing mood, with a real store under it and a clock we control.

The pure maths is in `test_affect_rules.py`. What is on trial here is what
touches the database: that it survives a restart correctly aged, that it only
blames somebody when there is somebody to blame, and that it never invents a
grudge out of a busy room.
"""

import time

import pytest

from src.core.affect.rules import PERSON_HALF_LIFE_SECONDS, Affect
from src.core.affect.state import AffectState
from src.core.memory.store import MemoryStore
from src.core.perception.types import Author, Perception, PerceptionKind
from tests.fakes import RecordingEvents

HOUR = 3600.0


class Clock:
    """Starts from the real clock: the store stamps its own rows with time.time()."""

    def __init__(self, now: float = None):
        self.now = time.time() if now is None else now

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += seconds


class Config:
    def __init__(self, **over):
        self.affect = {"enabled": True, "half_life_minutes": 25,
                       "person_half_life_hours": 60, "memory_ttl_hours": 6}
        self.affect.update(over)


@pytest.fixture
def store():
    s = MemoryStore(":memory:")
    yield s
    s.close()


def affect(store, clock=None, events=None, **cfg) -> AffectState:
    return AffectState(Config(**cfg), store, events=events, clock=clock or Clock())


def said(text="sei una noia", name="marco", identity="discord:1", owner=False) -> Perception:
    return Perception(
        kind=PerceptionKind.CHAT, surface="discord:text", content=f"[{name}] {text}",
        author=Author(platform="discord", native_id=identity.split(":")[1],
                      display_name=name, is_owner=owner),
    )


def known(store, identity="discord:1", name="marco", sessions=("a", "b", "c")):
    """Someone she has seen enough times to already have a card."""
    for session in sessions:
        store.roster.record(identity=identity, display_name=name,
                            platform="discord", session_id=session)
    entry = store.roster.get(identity)
    card = store.people.create_from_entry(entry, reason="a regular")
    store.roster.set_promoted(identity, card.person_id)
    return card


# --- the standing mood ------------------------------------------------------


def test_she_starts_neutral(store):
    assert affect(store).current.strength == 0.0
    assert affect(store).render() == ""


def test_one_line_moves_her_without_making_a_mood(store):
    state = affect(store)
    state.spoke("angry", [said()])
    assert state.current.valence < 0
    assert state.render() == ""


def test_two_angry_lines_are_a_mood_she_can_feel(store):
    state = affect(store)
    state.spoke("angry", [said()])
    state.spoke("angry", [said()])
    assert "[HOW YOU FEEL]" in state.render()


def test_the_mood_wears_off_on_its_own(store):
    clock = Clock()
    state = affect(store, clock)
    state.spoke("angry", [said()])
    state.spoke("angry", [said()])
    assert state.render() != ""

    clock.tick(2 * HOUR)
    assert state.render() == ""


def test_turning_it_off_makes_her_neutral_and_silent(store):
    state = affect(store, enabled=False)
    state.spoke("angry", [said()])
    state.spoke("angry", [said()])
    assert state.current == Affect()
    assert state.render() == ""


# --- surviving a restart ----------------------------------------------------


def test_she_comes_back_still_annoyed(store):
    clock = Clock()
    state = affect(store, clock)
    state.spoke("angry", [said()])
    state.spoke("angry", [said()])

    clock.tick(60)
    restarted = affect(store, clock)
    assert restarted.render() == state.render()


def test_she_comes_back_calm_after_a_night(store):
    clock = Clock()
    state = affect(store, clock)
    state.spoke("angry", [said()])
    state.spoke("angry", [said()])

    clock.tick(8 * HOUR)
    assert affect(store, clock).render() == ""


def test_a_corrupt_saved_mood_is_not_a_failure_to_start(store):
    store.db.execute("INSERT INTO settings (key, value) VALUES ('affect.state', 'nonsense')")
    assert affect(store).current.strength == 0.0


# --- who caused it ----------------------------------------------------------


def test_the_person_who_got_to_her_goes_cold(store):
    card = known(store)
    state = affect(store)
    state.spoke("angry", [said()])
    assert store.people.get(card.person_id).warmth < 0


def test_the_person_who_made_her_day_goes_warm(store):
    card = known(store)
    affect(store).spoke("love", [said("sei bravissima")])
    assert store.people.get(card.person_id).warmth > 0


def test_a_grudge_fades_by_itself(store):
    card = known(store)
    a_half_life_ago = time.time() - PERSON_HALF_LIFE_SECONDS
    store.people.nudge_warmth(card.person_id, -0.8, now=a_half_life_ago)
    assert store.people.get(card.person_id).warmth == pytest.approx(-0.4, abs=0.01)


def test_a_mild_mood_is_nobody_in_particular_s_fault(store):
    card = known(store)
    affect(store).spoke("bored", [said()])
    assert store.people.get(card.person_id).warmth == 0.0


def test_a_busy_room_never_gets_a_face_pinned_on_it(store):
    card = known(store)
    crowd = [said(name="marco"), said(name="lucia", identity="discord:2")]
    affect(store).spoke("angry", crowd)
    assert store.people.get(card.person_id).warmth == 0.0


def test_her_own_bad_mood_blames_nobody(store):
    state = affect(store)
    state.spoke("angry", [])
    assert state.current.valence < 0
    assert store.hot.active() == []


def test_the_owner_is_not_somebody_she_keeps_a_grudge_on(store):
    affect(store).spoke("angry", [said(owner=True)])
    assert store.hot.active() == []


# --- remembering it happened -------------------------------------------------


def test_she_remembers_what_it_was_about(store):
    known(store)
    affect(store).spoke("angry", [said("il tuo stream fa schifo")])

    facts = store.hot.active()
    assert len(facts) == 1
    assert "marco" in facts[0].text
    assert "il tuo stream fa schifo" in facts[0].text
    assert facts[0].source == "live"


def test_what_she_remembers_reaches_the_prompt(store):
    known(store)
    affect(store).spoke("angry", [said("il tuo stream fa schifo")])
    assert "marco" in store.hot.render()


def test_the_memory_is_given_a_lifetime_not_kept_forever(store):
    known(store)
    affect(store, memory_ttl_hours=6).spoke("angry", [said()])
    fact = store.hot.active()[0]
    assert fact.expires_at - fact.created_at == pytest.approx(6 * HOUR)


# --- earning a card ---------------------------------------------------------


def test_a_stranger_who_really_got_to_her_earns_a_card(store):
    store.roster.record(identity="discord:9", display_name="nuovo", platform="discord")
    affect(store).spoke("angry", [said(name="nuovo", identity="discord:9")])

    card = store.people.get_by_identity("discord:9")
    assert card is not None and card.warmth < 0


def test_somebody_she_has_never_seen_is_not_invented(store):
    affect(store).spoke("angry", [said(name="fantasma", identity="discord:99")])
    assert store.people.get_by_identity("discord:99") is None


# --- how it reads -----------------------------------------------------------


def test_the_card_says_it_in_words_not_in_numbers(store):
    card = known(store)
    state = affect(store)
    state.spoke("angry", [said()])
    state.spoke("angry", [said()])

    rendered = store.people.get(card.person_id).render()
    assert "annoyed" in rendered
    assert "0." not in rendered


def test_a_settled_attitude_and_a_recent_one_both_show(store):
    card = known(store)
    store.people.set_attitude(card.person_id, "a friend")
    state = affect(store)
    state.spoke("angry", [said()])
    state.spoke("angry", [said()])

    rendered = store.people.get(card.person_id).render()
    assert "a friend" in rendered and "annoyed" in rendered


# --- the dashboard ----------------------------------------------------------


def test_a_change_of_mood_is_visible_to_whoever_is_watching(store):
    events = RecordingEvents()
    state = affect(store, events=events)
    state.spoke("angry", [said()])
    state.spoke("angry", [said()])
    assert any(source == "affect" for _, source, _, _ in events.events)


def test_an_unchanged_mood_is_not_reannounced_every_turn(store):
    events = RecordingEvents()
    state = affect(store, events=events)
    for _ in range(6):
        state.spoke("normal", [said("ciao")])
    assert [e for e in events.events if e[1] == "affect"] == []


def test_the_people_page_is_given_the_words_and_never_the_number(store):
    """A value nobody can read is a value nobody can tell is stuck."""
    from fastapi.testclient import TestClient

    from src.web import app as web

    card = known(store)
    state = affect(store)
    state.spoke("angry", [said()])
    state.spoke("angry", [said()])

    class BrainStub:
        memory = store

    previous = web.brain_instance
    web.brain_instance = BrainStub()
    try:
        person = TestClient(web.app).get("/memory/people").json()[0]
    finally:
        web.brain_instance = previous

    assert person["person_id"] == card.person_id
    assert "annoyed" in person["mood"]
    assert "warmth" not in person
