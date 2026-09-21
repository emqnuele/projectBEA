"""One human, one card — whatever surface they arrive on.

Promotion used to mint by identity in the live paths and by name in the
dreamer, so one human on two surfaces became two cards. Every promotion now
goes through `promote_entry`: an exact name on a shared session links the
identity to the existing card instead of minting. Substring matches and
strangers who never shared a session stay separate cards.
"""

from types import SimpleNamespace

import pytest

from src.core.memory.store import MemoryStore
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.social.people import (
    promote_entry,
    record_person,
    repair_duplicate_cards,
)
from src.core.skills.social.social import SocialMemory


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
    record_person(memory.roster, memory.people, "Marco", session_id="s1")
    record_person(memory.roster, memory.people, "Marco", session_id="s2")
    assert record_person(memory.roster, memory.people, "Marco", session_id="s3")

    entry = memory.roster.record(identity="twitch:9", display_name="Marco",
                                 platform="twitch", session_id="s9", is_1on1=True)
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


def test_the_repair_leaves_strangers_sharing_only_a_name(memory):
    _two_cards(memory, session_shared=False)

    assert repair_duplicate_cards(memory.roster, memory.people) == 0
    assert len(memory.people.all()) == 2


def test_the_repair_is_a_noop_the_second_time(memory):
    _two_cards(memory)

    assert repair_duplicate_cards(memory.roster, memory.people) == 1
    assert repair_duplicate_cards(memory.roster, memory.people) == 0


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
