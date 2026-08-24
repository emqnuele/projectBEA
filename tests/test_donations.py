"""Money: the one input that always earns a reaction."""

import pytest

from src.core.attention.rules import is_addressed
from src.core.memory.store import MemoryStore
from src.core.perception.bus import PerceptionBus
from src.core.skills.donation.surface import DonationSkill
from tests.fakes import FakeHistory


class Context:
    def __init__(self, store):
        self.memory = store
        self.history_manager = FakeHistory()


class Config:
    def __init__(self, **donations):
        block = {"enabled": True}
        block.update(donations)
        self.skills = {"donations": block}
        self.attention = {"trigger_words": ["bea"]}


@pytest.fixture
def donation():
    store = MemoryStore(":memory:")
    bus = PerceptionBus(window=0.0)
    skill = DonationSkill(Config(), bus=bus, expression=None, context=Context(store))
    skill.initialize()
    skill.active = True
    yield skill, store, bus
    store.close()


def give(skill, name="marco", amount=10.0, **kwargs):
    return skill.receive(name=name, amount=amount, **kwargs)


# --- the perception ----------------------------------------------------------


def test_a_donation_lands_on_the_bus(donation):
    skill, _, bus = donation
    perception = give(skill)
    assert bus.drain_nowait() == [perception]


def test_the_amount_travels_with_the_author(donation):
    skill, _, _ = donation
    p = give(skill, amount=25.0, currency="USD")
    assert p.author.extra["amount"] == 25.0
    assert p.author.extra["currency"] == "USD"


def test_a_donation_always_reaches_her(donation):
    """Past the cooldown, past quiet hours: money is not something she misses."""
    skill, _, _ = donation
    p = give(skill)
    assert is_addressed(p, trigger_words=["bea"]) == "addressed:donation"


def test_the_message_is_rendered_for_her_to_read(donation):
    skill, _, _ = donation
    p = give(skill, amount=5.0, message="sei la migliore")
    assert "marco" in p.content.lower()
    assert "5 EUR" in p.content
    assert "sei la migliore" in p.content


def test_a_donation_belongs_to_the_stage(donation):
    skill, _, _ = donation
    assert give(skill).meta["conversation_key"] == "stage"


def test_a_nameless_donation_still_works(donation):
    skill, _, _ = donation
    assert give(skill, name="").author.display_name == "someone"


# --- what it does to her memory ----------------------------------------------


def test_a_donor_earns_a_card_immediately(donation):
    """No waiting for the dreamer: the next line she says already knows them."""
    skill, store, _ = donation
    give(skill, name="marco", amount=10.0)
    card = store.people.find_by_name("marco")
    assert card is not None
    assert card.promoted_reason == "donated"


def test_the_donation_is_written_on_the_card(donation):
    skill, store, _ = donation
    give(skill, name="marco", amount=10.0, message="tieni")
    facts = store.people.find_by_name("marco").facts
    assert any("donated 10 EUR" in f for f in facts)
    assert any("tieni" in f for f in facts)


def test_the_total_adds_up_across_donations(donation):
    skill, store, _ = donation
    give(skill, name="marco", amount=10.0, donor_id="d1", event_id="e1")
    give(skill, name="marco", amount=5.0, donor_id="d1", event_id="e2")
    assert store.roster.get("donation:d1").donation_total == pytest.approx(15.0)


def test_she_can_bring_it_up_for_a_while(donation):
    skill, store, _ = donation
    give(skill, name="marco", amount=10.0)
    assert any("marco just donated" in f.text for f in store.hot.active())


# --- webhooks are retried ----------------------------------------------------


def test_a_retried_webhook_is_not_a_second_donation(donation):
    skill, store, bus = donation
    assert give(skill, event_id="evt-1") is not None
    assert give(skill, event_id="evt-1") is None
    assert len(bus.drain_nowait()) == 1
    assert store.roster.get("donation:marco").donation_total == pytest.approx(10.0)


def test_without_an_event_id_every_call_counts(donation):
    skill, _, bus = donation
    give(skill)
    give(skill)
    assert len(bus.drain_nowait()) == 2


# --- authorization -----------------------------------------------------------


def test_with_no_secret_configured_the_endpoint_is_open(donation):
    skill, _, _ = donation
    assert skill.authorized(None) is True


def test_a_configured_secret_is_enforced(monkeypatch):
    store = MemoryStore(":memory:")
    skill = DonationSkill(Config(secret="s3cret"), bus=PerceptionBus(window=0.0),
                          expression=None, context=Context(store))
    skill.initialize()
    assert skill.authorized("s3cret") is True
    assert skill.authorized("wrong") is False
    assert skill.authorized(None) is False
    store.close()


# --- the tool ----------------------------------------------------------------


def test_with_no_donors_she_says_so(donation):
    skill, _, _ = donation
    assert "Nobody" in skill._tool_recall_donors()


def test_donors_come_back_biggest_first(donation):
    skill, _, _ = donation
    give(skill, name="marco", amount=5.0, donor_id="d1")
    give(skill, name="luca", amount=50.0, donor_id="d2")
    result = skill._tool_recall_donors()
    assert result.index("luca") < result.index("marco")
