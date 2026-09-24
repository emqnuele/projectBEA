"""One human, one card — whatever surface they arrive on.

Promotion used to mint by identity in the live paths and by name in the
dreamer, so one human on two surfaces became two cards. Every promotion now
goes through `promote_entry`: an exact name on a shared session, or on a
card known only by that name, links the identity to the existing card
instead of minting. Substring matches and accounts that never shared a
session stay separate cards.
"""

from types import SimpleNamespace

import pytest

from src.core.memory.store import MemoryStore
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.social.people import (
    card_for_identity,
    promote_entry,
    record_person,
    repair_duplicate_cards,
    resolve_or_create_card,
)
from src.core.skills.social.social import SocialMemory

DAY = 86400


@pytest.fixture
def memory():
    store = MemoryStore(":memory:")
    yield store
    store.close()


def test_a_voice_identity_links_to_the_chat_card_with_the_same_name(memory):
    record_person(memory.roster, memory.people, "Ema", session_id="s1")
    record_person(memory.roster, memory.people, "Ema", session_id="s2")
    chat_card = record_person(memory.roster, memory.people, "Ema", session_id="s3")
    assert chat_card is not None

    entry = memory.roster.record(identity="discord:7", display_name="Ema",
                                 platform="discord", session_id="s2", is_1on1=True)
    card = promote_entry(memory.roster, memory.people, entry)

    assert card is not None
    assert card.person_id == chat_card.person_id
    assert len(memory.people.all()) == 1
    assert memory.people.get_by_identity("discord:7") is not None


def test_the_same_name_in_another_session_stays_a_second_card(memory):
    first = memory.roster.record(identity="twitch:1", display_name="Marco",
                                 platform="twitch", session_id="s1", is_1on1=True)
    promote_entry(memory.roster, memory.people, first)

    entry = memory.roster.record(identity="twitch:9", display_name="Marco",
                                 platform="twitch", session_id="s9", is_1on1=True)
    promote_entry(memory.roster, memory.people, entry)

    assert len(memory.people.all()) == 2


def test_an_account_takes_in_the_card_known_only_by_its_name(memory):
    named = resolve_or_create_card(memory.roster, memory.people, "Marco")

    entry = memory.roster.record(identity="twitch:9", display_name="Marco",
                                 platform="twitch", session_id="s9", is_1on1=True)
    card = promote_entry(memory.roster, memory.people, entry)

    assert card.person_id == named.person_id
    assert len(memory.people.all()) == 1
    assert set(card.identities) == {"named:marco", "twitch:9"}


def test_only_the_first_account_takes_in_a_name_only_card(memory):
    resolve_or_create_card(memory.roster, memory.people, "Marco")
    for identity, session in (("twitch:1", "s1"), ("twitch:2", "s2")):
        entry = memory.roster.record(identity=identity, display_name="Marco",
                                     platform="twitch", session_id=session, is_1on1=True)
        promote_entry(memory.roster, memory.people, entry)

    assert len(memory.people.all()) == 2


def test_a_near_name_never_links(memory):
    record_person(memory.roster, memory.people, "Marco", session_id="s1")
    record_person(memory.roster, memory.people, "Marco", session_id="s2")
    assert record_person(memory.roster, memory.people, "Marco", session_id="s3")

    entry = memory.roster.record(identity="discord:3", display_name="Marc",
                                 platform="discord", session_id="s3", is_1on1=True)
    promote_entry(memory.roster, memory.people, entry)

    assert len(memory.people.all()) == 2


def test_an_already_promoted_identity_returns_its_card(memory):
    record_person(memory.roster, memory.people, "Ema", session_id="s1")
    record_person(memory.roster, memory.people, "Ema", session_id="s2")
    card = record_person(memory.roster, memory.people, "Ema", session_id="s3")

    entry = memory.roster.get("named:ema")

    assert promote_entry(memory.roster, memory.people, entry).person_id == card.person_id
    assert len(memory.people.all()) == 1


def _two_cards(memory, session_shared=True):
    e1 = memory.roster.record(identity="named:ema", display_name="Ema",
                              platform="named", session_id="s1")
    c1 = memory.people.create_from_entry(e1)
    memory.roster.set_promoted(e1.identity, c1.person_id)
    memory.people.add_fact(c1.person_id, "hosts a server")
    e2 = memory.roster.record(identity="discord:7", display_name="Ema",
                              platform="discord",
                              session_id="s1" if session_shared else "s9")
    c2 = memory.people.create_from_entry(e2)
    memory.roster.set_promoted(e2.identity, c2.person_id)
    memory.people.add_fact(c2.person_id, "called on discord")
    memory.people.set_attitude(c2.person_id, "neutro positivo")
    return c1, c2


def test_the_repair_folds_duplicates_that_shared_a_session(memory):
    _two_cards(memory)

    assert repair_duplicate_cards(memory.roster, memory.people) == 1

    cards = memory.people.all()
    assert len(cards) == 1
    assert {"named:ema", "discord:7"} <= set(cards[0].identities)
    assert {"hosts a server", "called on discord"} <= set(cards[0].facts)
    assert cards[0].bea_attitude == "neutro positivo"


def _two_accounts(memory, *, shared: bool):
    cards = []
    for identity, session in (("twitch:1", "s1"), ("twitch:2", "s1" if shared else "s9")):
        entry = memory.roster.record(identity=identity, display_name="Marco",
                                     platform="twitch", session_id=session)
        card = memory.people.create_from_entry(entry)
        memory.roster.set_promoted(identity, card.person_id)
        cards.append(card)
    return cards


def test_the_repair_leaves_strangers_sharing_only_a_name(memory):
    _two_accounts(memory, shared=False)

    assert repair_duplicate_cards(memory.roster, memory.people) == 0
    assert len(memory.people.all()) == 2


def test_the_repair_folds_a_name_only_card_that_never_shared_a_session(memory):
    _two_cards(memory, session_shared=False)

    assert repair_duplicate_cards(memory.roster, memory.people) == 1
    cards = memory.people.all()
    assert len(cards) == 1
    assert {"hosts a server", "called on discord"} <= set(cards[0].facts)


def test_the_repair_folds_a_card_left_with_no_identity(memory):
    a, b = _two_accounts(memory, shared=False)
    memory.people.add_fact(b.person_id, "plays redstone")
    memory.db.execute("UPDATE identities SET person_id = ? WHERE person_id = ?",
                      (a.person_id, b.person_id))

    assert repair_duplicate_cards(memory.roster, memory.people) == 1
    cards = memory.people.all()
    assert len(cards) == 1
    assert "plays redstone" in cards[0].facts


def test_the_repair_keeps_homonym_accounts_apart_after_taking_in_a_name(memory):
    _two_accounts(memory, shared=False)
    entry = memory.roster.record(identity="named:marco", display_name="Marco",
                                 platform="named")
    named = memory.people.create_from_entry(entry)
    memory.roster.set_promoted(entry.identity, named.person_id)
    memory.people.add_fact(named.person_id, "a")
    memory.people.add_fact(named.person_id, "b")

    assert repair_duplicate_cards(memory.roster, memory.people) == 1
    assert len(memory.people.all()) == 2


def test_the_repair_is_a_noop_the_second_time(memory):
    _two_cards(memory)

    assert repair_duplicate_cards(memory.roster, memory.people) == 1
    assert repair_duplicate_cards(memory.roster, memory.people) == 0


def test_inherited_warmth_starts_decaying_from_the_merge(memory):
    """Warmth is read already decayed to now, so its clock has to move with it.

    Left at the loser's old `warmth_at`, warmth folded in from a card last
    touched weeks ago would keep decaying from that reading and fade in
    minutes instead of days.
    """
    import time

    _c1, c2 = _two_cards(memory)
    memory.people.nudge_warmth(c2.person_id, 0.8)
    memory.db.execute("UPDATE people SET warmth_at = ? WHERE person_id = ?",
                      (time.time() - 60 * DAY, c2.person_id))

    repair_duplicate_cards(memory.roster, memory.people)

    survivor = memory.people.all()[0]
    fresh = float(memory.db.scalar(
        "SELECT warmth_at FROM people WHERE person_id = ?", (survivor.person_id,)))
    assert survivor.warmth > 0
    assert time.time() - fresh < 5


# --- she can say who is in front of her -------------------------------------

class SocialConfig:
    def __init__(self):
        self.skills = {"social_memory": {"enabled": True}}


def social_skill(memory):
    skill = SocialMemory(SocialConfig(), bus=None, expression=None,
                         context=SimpleNamespace(memory=memory, history_manager=None))
    skill.initialize()
    skill.active = True
    return skill


def card_for(memory, name="Marco"):
    record_person(memory.roster, memory.people, name, session_id="s1")
    record_person(memory.roster, memory.people, name, session_id="s2")
    return record_person(memory.roster, memory.people, name, session_id="s3")


def voice(identity, display, text="sono Marco"):
    platform = identity.split(":")[0]
    return Perception(
        kind=PerceptionKind.CHAT, surface=f"chat:{platform}",
        content=f"[{display}] {text}",
        author=Author(platform=platform, native_id=identity.split(":")[1],
                      display_name=display),
    )


def test_she_links_the_player_who_told_her_who_they_are(memory):
    marco = card_for(memory)
    skill = social_skill(memory)
    skill.context_for([voice("minecraft:uuid-1", "xX_DarkSlayer")])

    reply = skill._tool_link_person(name="Marco")

    assert "xX_DarkSlayer is Marco" in reply
    assert memory.people.get_by_identity("minecraft:uuid-1").person_id == marco.person_id
    assert len(memory.people.all()) == 1


def test_linking_a_stranger_creates_nothing(memory):
    skill = social_skill(memory)
    skill.context_for([voice("minecraft:uuid-1", "xX_DarkSlayer")])

    reply = skill._tool_link_person(name="Nobody")

    assert "don't know anyone" in reply
    assert len(memory.people.all()) == 0


def test_two_speakers_need_disambiguation(memory):
    card_for(memory)
    skill = social_skill(memory)
    skill.context_for([voice("minecraft:uuid-1", "xX_DarkSlayer"),
                       voice("discord:2", "luca")])

    reply = skill._tool_link_person(name="Marco")

    assert "can't tell" in reply
    assert memory.people.get_by_identity("minecraft:uuid-1") is None


def test_speaking_as_picks_among_several_speakers(memory):
    marco = card_for(memory)
    skill = social_skill(memory)
    skill.context_for([voice("minecraft:uuid-1", "xX_DarkSlayer"),
                       voice("discord:2", "luca")])

    reply = skill._tool_link_person(name="Marco", speaking_as="dark")

    assert "xX_DarkSlayer is Marco" in reply
    assert memory.people.get_by_identity("minecraft:uuid-1").person_id == marco.person_id
    assert memory.people.get_by_identity("discord:2") is None


def test_linking_folds_the_card_the_speaker_was_on(memory):
    marco = card_for(memory)
    entry = memory.roster.record(identity="minecraft:uuid-1", display_name="xX_DarkSlayer",
                                 platform="minecraft", session_id="s9", is_1on1=True)
    old = promote_entry(memory.roster, memory.people, entry)
    memory.people.add_fact(old.person_id, "builds redstone")
    skill = social_skill(memory)
    skill.context_for([voice("minecraft:uuid-1", "xX_DarkSlayer")])

    skill._tool_link_person(name="Marco")

    cards = memory.people.all()
    assert [c.person_id for c in cards] == [marco.person_id]
    assert "builds redstone" in cards[0].facts
    assert "minecraft:uuid-1" in cards[0].identities


def test_linking_keeps_a_card_that_still_has_other_accounts(memory):
    marco = card_for(memory)
    entry = memory.roster.record(identity="minecraft:uuid-1", display_name="xX_DarkSlayer",
                                 platform="minecraft", session_id="s9", is_1on1=True)
    old = promote_entry(memory.roster, memory.people, entry)
    memory.roster.link(identity="twitch:5", display_name="xX_DarkSlayer",
                       platform="twitch", person_id=old.person_id)
    skill = social_skill(memory)
    skill.context_for([voice("minecraft:uuid-1", "xX_DarkSlayer")])

    skill._tool_link_person(name="Marco")

    assert memory.people.get(old.person_id).identities == ["twitch:5"]
    assert memory.people.get_by_identity("minecraft:uuid-1").person_id == marco.person_id


def test_two_cards_with_one_name_answer_the_oldest_first(memory):
    a, b = _two_accounts(memory, shared=False)
    memory.db.execute("UPDATE people SET created_at = created_at - 100 WHERE person_id = ?",
                      (b.person_id,))

    assert memory.people.find_by_name("Marco").person_id == b.person_id


def test_an_account_already_on_a_card_keeps_it(memory):
    a, _b = _two_accounts(memory, shared=False)

    card = card_for_identity(memory.roster, memory.people, memory.roster.get("twitch:1"))

    assert card.person_id == a.person_id


def test_an_account_below_the_thresholds_lands_on_the_name_only_card(memory):
    named = resolve_or_create_card(memory.roster, memory.people, "Marco")
    entry = memory.roster.record(identity="twitch:9", display_name="Marco",
                                 platform="twitch", session_id="s9")

    card = card_for_identity(memory.roster, memory.people, entry)

    assert card.person_id == named.person_id
    assert "twitch:9" in card.identities


def test_an_account_below_the_thresholds_with_no_card_gets_none(memory):
    entry = memory.roster.record(identity="twitch:9", display_name="Marco",
                                 platform="twitch", session_id="s9")

    assert card_for_identity(memory.roster, memory.people, entry) is None
    assert memory.people.count() == 0
