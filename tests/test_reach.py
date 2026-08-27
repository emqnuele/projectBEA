"""One person, several places. She talks to people, not to channels.

A person's card already carries every account they own. What was missing is
the other direction: given a person, where can she reach them, and how does
she start the conversation herself — the DM after the voice call, on a whole
different platform.
"""

import pytest

from src.core.memory.store import MemoryStore
from src.core.skills.base import SkillRegistry
from src.core.skills.platform import PlatformSkill
from src.core.social.reach import Reach


class Config:
    def __init__(self):
        self.skills = {}
        self.attention = {}


class Recorder(PlatformSkill):
    """A platform that records what it was asked to deliver."""

    def __init__(self, platform: str, *, dm: bool = True):
        super().__init__(Config(), bus=None, expression=None)
        self.name = f"chat:{platform}"
        self.skill_name = platform
        self.platform = platform
        self.supports_dm = dm
        self.sent = []
        self.dms = []
        self.initialize()
        self.active = True

    async def send_text(self, channel_id, text, reply_to=None):
        self.sent.append((channel_id, text))
        return True

    async def send_dm(self, native_id, text):
        if not self.supports_dm:
            return None
        self.dms.append((native_id, text))
        return native_id


@pytest.fixture
def memory():
    return MemoryStore(":memory:")


def _person(memory, name: str, *identities) -> str:
    """A card with several accounts linked to it, the way promotion builds one."""
    for identity in identities:
        platform, _, native = identity.partition(":")
        memory.roster.record(identity=identity, display_name=name, platform=platform)
    entry = memory.roster.get(identities[0])
    card = memory.people.create_from_entry(entry)
    for identity in identities[1:]:
        memory.people.link_identity(card.person_id, identity)
    return card.person_id


def reach(memory, *skills) -> Reach:
    registry = SkillRegistry()
    for skill in skills:
        registry.register(skill)
    return Reach(memory=memory, surfaces=registry)


async def _instant(seconds):
    return None


def _fast(skill: Recorder) -> Recorder:
    skill.humanizer._sleep = _instant
    return skill


# --- finding a person --------------------------------------------------------


def test_a_person_is_found_by_name(memory):
    _person(memory, "Ema", "discord:1")
    assert reach(memory).find("Ema").primary_name == "Ema"


def test_the_name_does_not_have_to_match_the_case(memory):
    _person(memory, "Ema", "discord:1")
    assert reach(memory).find("ema") is not None


def test_a_person_is_found_by_any_of_their_accounts(memory):
    _person(memory, "Ema", "discord:1", "telegram:2")
    assert reach(memory).find("telegram:2").primary_name == "Ema"


def test_a_stranger_is_not_invented(memory):
    assert reach(memory).find("nessuno") is None


# --- where she can reach them ------------------------------------------------


def test_every_linked_account_is_a_way_to_reach_them(memory):
    pid = _person(memory, "Ema", "discord:1", "telegram:2")
    channels = reach(memory).channels(pid)
    assert {c.platform for c in channels} == {"discord", "telegram"}


def test_a_channel_is_only_usable_if_that_platform_is_live(memory):
    pid = _person(memory, "Ema", "discord:1", "telegram:2")
    r = reach(memory, _fast(Recorder("telegram")))
    usable = {c.platform for c in r.channels(pid) if c.reachable}
    assert usable == {"telegram"}


def test_a_platform_without_private_messages_is_not_a_way_to_reach_anyone(memory):
    pid = _person(memory, "Ema", "twitch:1")
    r = reach(memory, _fast(Recorder("twitch", dm=False)))
    assert [c for c in r.channels(pid) if c.reachable] == []


def test_the_most_recently_seen_account_comes_first(memory):
    pid = _person(memory, "Ema", "discord:1", "telegram:2")
    memory.roster.record(identity="telegram:2", display_name="Ema", platform="telegram")
    assert reach(memory).channels(pid)[0].platform == "telegram"


# --- actually reaching them --------------------------------------------------


async def test_she_can_message_a_person_by_name(memory):
    _person(memory, "Ema", "telegram:2")
    telegram = _fast(Recorder("telegram"))
    result = await reach(memory, telegram).message("Ema", "ehi, ci sei?")
    assert result.ok
    assert telegram.dms == [("2", "ehi, ci sei?")]


async def test_she_can_choose_the_platform(memory):
    _person(memory, "Ema", "discord:1", "telegram:2")
    discord, telegram = _fast(Recorder("discord")), _fast(Recorder("telegram"))
    await reach(memory, discord, telegram).message("Ema", "ciao", platform="discord")
    assert discord.dms == [("1", "ciao")]
    assert telegram.dms == []


async def test_reaching_a_stranger_says_so_instead_of_guessing(memory):
    result = await reach(memory).message("nessuno", "ciao")
    assert not result.ok
    assert "nessuno" in result.error


async def test_a_person_with_no_live_platform_cannot_be_reached(memory):
    _person(memory, "Ema", "discord:1")
    result = await reach(memory).message("Ema", "ciao")
    assert not result.ok
    assert "discord" in result.error


async def test_asking_for_a_platform_she_cannot_use_is_refused(memory):
    _person(memory, "Ema", "discord:1", "telegram:2")
    r = reach(memory, _fast(Recorder("telegram")))
    result = await r.message("Ema", "ciao", platform="discord")
    assert not result.ok


async def test_the_conversation_it_opens_is_the_one_the_reply_lands_in(memory):
    """The DM she sends and the answer she gets must be the same thread."""
    _person(memory, "Ema", "telegram:2")
    telegram = _fast(Recorder("telegram"))
    result = await reach(memory, telegram).message("Ema", "ciao")
    assert result.conversation_key == "telegram:2"


async def test_what_she_wrote_is_in_that_conversation_history(memory):
    _person(memory, "Ema", "telegram:2")
    telegram = _fast(Recorder("telegram"))
    await reach(memory, telegram).message("Ema", "ehi")
    history = memory.conversations.history("telegram:2")
    assert [h["content"] for h in history] == ["ehi"]
    assert history[0]["role"] == "bea"


async def test_a_failed_send_is_not_written_to_history(memory):
    _person(memory, "Ema", "telegram:2")

    class Broken(Recorder):
        async def send_dm(self, native_id, text):
            return None

    telegram = _fast(Broken("telegram"))
    result = await reach(memory, telegram).message("Ema", "ciao")
    assert not result.ok
    assert memory.conversations.history("telegram:2") == []


# --- the default platform skill ----------------------------------------------


async def test_by_default_a_private_message_goes_to_the_id_as_a_channel(memory):
    """On telegram a DM channel *is* the user id; discord has to override this."""
    telegram = _fast(Recorder("telegram"))
    assert await PlatformSkill.send_dm(telegram, "2", "ciao") == "2"
    assert telegram.sent == [("2", "ciao")]


# --- discord is the exception ------------------------------------------------


async def test_a_discord_dm_reports_the_channel_the_reply_will_arrive_on():
    """A discord DM is its own channel, not the user id: without the real id the
    answer lands in a thread she has no record of starting."""
    from src.core.skills.voice.surface import VoiceSurface

    class Transport:
        def __init__(self):
            self.dms = []

        async def send_dm(self, user_id, content):
            self.dms.append((user_id, content))
            return {"ok": True, "channelId": "dm-999"}

    class Cfg:
        skills = {"discord": {"enabled": True}}
        attention = {}

    surface = VoiceSurface(Cfg(), bus=None, expression=None)
    surface.transport = Transport()
    surface.active = True
    assert await surface.send_dm("4711", "ciao") == "dm-999"
    assert surface.transport.dms == [("4711", "ciao")]


async def test_a_discord_dm_that_fails_reports_nothing():
    from src.core.skills.voice.surface import VoiceSurface

    class Transport:
        async def send_dm(self, user_id, content):
            return {"ok": False, "error": "cannot send messages to this user"}

    class Cfg:
        skills = {"discord": {"enabled": True}}
        attention = {}

    surface = VoiceSurface(Cfg(), bus=None, expression=None)
    surface.transport = Transport()
    surface.active = True
    assert await surface.send_dm("4711", "ciao") is None


def test_twitch_has_no_private_messages():
    from src.core.skills.twitch.surface import TwitchSkill

    assert TwitchSkill.supports_dm is False
