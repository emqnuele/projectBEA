"""The roster and the cards are counted and listed in one query each."""

from src.core.memory.store import MemoryStore


def test_counts_match_what_is_listed():
    memory = MemoryStore(":memory:")
    memory.roster.record(identity="discord:1", display_name="ema", platform="discord",
                         session_id="s1")
    memory.roster.record(identity="discord:1", display_name="ema", platform="discord",
                         session_id="s2")
    memory.roster.record(identity="telegram:2", display_name="marco", platform="telegram")
    entry = memory.roster.get("discord:1")
    assert entry is not None
    memory.people.create_from_entry(entry, reason="test")

    assert memory.roster.count() == len(memory.roster.all()) == 2
    assert memory.people.count() == len(memory.people.all()) == 1


def test_the_session_tally_is_per_identity():
    memory = MemoryStore(":memory:")
    for session in ("s1", "s2", "s2"):
        memory.roster.record(identity="discord:1", display_name="ema", platform="discord",
                             session_id=session)
    memory.roster.record(identity="twitch:3", display_name="lu", platform="twitch",
                         session_id="s1")

    tallies = {e.identity: e.session_count for e in memory.roster.all()}
    assert tallies == {"discord:1": 2, "twitch:3": 1}
    entry = memory.roster.get("discord:1")
    assert entry is not None and entry.session_count == 2
