"""Count-triggered background passes: knowing who you are without a dream."""

import pytest

from src.core.memory.profiler import Profiler
from src.core.memory.store import MemoryStore
from tests.fakes import FakeLLMClient


@pytest.fixture
def store():
    s = MemoryStore(":memory:")
    yield s
    s.close()


def a_person(store, identity="discord:1", name="marco"):
    entry = store.roster.record(identity=identity, display_name=name, platform="discord")
    card = store.people.create_from_entry(entry, reason="a regular")
    store.roster.set_promoted(identity, card.person_id)
    return card


def say(store, n, identity="discord:1", key="discord:99"):
    for i in range(n):
        store.conversations.add(conversation_key=key, role="user", content=f"messaggio {i}",
                                author_identity=identity, display_name="marco")


def profiler(store, llm=None, **kwargs):
    return Profiler(llm or FakeLLMClient(), store, **kwargs)


# --- person profiles ---------------------------------------------------------


async def test_a_stranger_without_a_card_is_not_profiled(store):
    say(store, 50)
    assert await profiler(store).maybe_profile("discord:1") is False


async def test_too_few_messages_means_no_profile_yet(store):
    a_person(store)
    say(store, 5)
    assert await profiler(store, first_profile_at=20).maybe_profile("discord:1") is False


async def test_the_first_card_is_built_early(store):
    """Until the card exists Bea genuinely has no idea who they are."""
    a_person(store)
    say(store, 20)
    llm = FakeLLMClient(json_script=[{"facts": ["gioca a minecraft"], "attitude": "tollerabile"}])

    assert await profiler(store, llm, first_profile_at=20).maybe_profile("discord:1") is True
    card = store.people.get_by_identity("discord:1")
    assert "gioca a minecraft" in card.facts
    assert card.bea_attitude == "tollerabile"


async def test_refreshes_are_far_rarer_than_the_first_one(store):
    a_person(store)
    say(store, 20)
    p = profiler(store, FakeLLMClient(json_script=[{"facts": ["a"]}, {"facts": ["b"]}]),
                 first_profile_at=20, reprofile_every=50)
    assert await p.maybe_profile("discord:1") is True

    say(store, 10)   # 30 total: not enough for a refresh
    assert await p.maybe_profile("discord:1") is False

    say(store, 45)   # 75 total: past the delta
    assert await p.maybe_profile("discord:1") is True


async def test_at_most_four_facts_are_kept_per_pass(store):
    a_person(store)
    say(store, 20)
    llm = FakeLLMClient(json_script=[{"facts": [f"fatto {i}" for i in range(10)]}])
    await profiler(store, llm, first_profile_at=20).maybe_profile("discord:1")
    assert len(store.people.get_by_identity("discord:1").facts) == 4


async def test_a_useless_answer_still_advances_the_counter(store):
    """A person with nothing to say must not be re-profiled on every message."""
    a_person(store)
    say(store, 20)
    llm = FakeLLMClient(json_script=[{}, {"facts": ["qualcosa"]}])
    p = profiler(store, llm, first_profile_at=20, reprofile_every=50)

    assert await p.maybe_profile("discord:1") is True
    assert await p.maybe_profile("discord:1") is False
    assert llm.json_calls and len(llm.json_calls) == 1


async def test_a_failing_model_does_not_raise(store):
    a_person(store)
    say(store, 20)
    llm = FakeLLMClient()
    llm.complete_json = _boom
    assert await profiler(store, llm, first_profile_at=20).maybe_profile("discord:1") is False


async def test_what_bea_already_knows_is_sent_along(store):
    card = a_person(store)
    store.people.add_fact(card.person_id, "odia il lunedi")
    say(store, 20)
    llm = FakeLLMClient(json_script=[{"facts": []}])
    await profiler(store, llm, first_profile_at=20).maybe_profile("discord:1")
    assert "odia il lunedi" in llm.json_calls[0]


# --- conversation summaries --------------------------------------------------


async def test_a_quiet_conversation_is_not_summarized(store):
    say(store, 3)
    assert await profiler(store, summary_every=30).maybe_summarize("discord:99") is False


async def test_a_busy_conversation_gets_a_summary(store):
    say(store, 30)
    llm = FakeLLMClient(json_script=[{"summary": "parlano di minecraft"}])
    assert await profiler(store, llm, summary_every=30).maybe_summarize("discord:99") is True
    assert store.conversations.summary("discord:99") == "parlano di minecraft"


async def test_the_previous_summary_is_given_to_the_model(store):
    store.conversations.save_summary("discord:99", "vecchio riassunto")
    say(store, 30)
    llm = FakeLLMClient(json_script=[{"summary": "nuovo"}])
    await profiler(store, llm, summary_every=30).maybe_summarize("discord:99")
    assert "vecchio riassunto" in llm.json_calls[0]


async def test_a_failed_summary_does_not_retry_every_turn(store):
    say(store, 30)
    llm = FakeLLMClient(json_script=[{}])
    p = profiler(store, llm, summary_every=30)
    assert await p.maybe_summarize("discord:99") is False
    assert await p.maybe_summarize("discord:99") is False
    assert len(llm.json_calls) == 1


async def test_a_failed_summary_does_not_erase_the_old_one(store):
    store.conversations.save_summary("discord:99", "quello buono")
    say(store, 30)
    await profiler(store, FakeLLMClient(json_script=[{}]), summary_every=30).maybe_summarize("discord:99")
    assert store.conversations.summary("discord:99") == "quello buono"


async def test_an_empty_conversation_summarizes_to_nothing(store):
    assert await profiler(store, summary_every=0).maybe_summarize("discord:nothing") is False


async def _boom(*args, **kwargs):
    raise RuntimeError("model is down")
