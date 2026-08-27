"""The half of Twitch she was blind to.

Subs, resubs, gifted subs and raids arrive as USERNOTICE, not PRIVMSG, and the
parser only ever looked at PRIVMSG. A raid — two hundred people arriving at
once, the single biggest moment of a stream — did not reach her at all.
"""

import pytest

from src.core.perception.bus import PerceptionBus
from src.core.skills.twitch.irc import ChatEvent, parse_line
from src.core.skills.twitch.surface import TwitchSkill


class Config:
    def __init__(self, **twitch):
        self.skills = {"twitch": {"enabled": True, "channel": "ema", **twitch}}
        self.attention = {}


@pytest.fixture
def bus() -> PerceptionBus:
    return PerceptionBus(window=0.0)


def skill(bus, **twitch) -> TwitchSkill:
    s = TwitchSkill(Config(**twitch), bus=bus, expression=None)
    s.initialize()
    s.active = True
    return s


def drain(bus) -> list:
    return bus.drain_nowait()


RAID = (
    "@badge-info=;badges=;display-name=Marco;login=marco;msg-id=raid;"
    "msg-param-displayName=Marco;msg-param-viewerCount=212;room-id=1;user-id=4711 "
    ":tmi.twitch.tv USERNOTICE #ema"
)
SUB = (
    "@display-name=Marco;login=marco;msg-id=sub;msg-param-sub-plan=1000;"
    "msg-param-cumulative-months=1;user-id=4711 :tmi.twitch.tv USERNOTICE #ema "
    ":sono qui!"
)
RESUB = (
    "@display-name=Marco;login=marco;msg-id=resub;msg-param-sub-plan=1000;"
    "msg-param-cumulative-months=14;user-id=4711 :tmi.twitch.tv USERNOTICE #ema"
)
GIFT = (
    "@display-name=Marco;login=marco;msg-id=subgift;msg-param-recipient-display-name=Ludo;"
    "msg-param-gift-months=1;user-id=4711 :tmi.twitch.tv USERNOTICE #ema"
)
MASS_GIFT = (
    "@display-name=Marco;login=marco;msg-id=submysterygift;"
    "msg-param-mass-gift-count=20;user-id=4711 :tmi.twitch.tv USERNOTICE #ema"
)


# --- parsing -----------------------------------------------------------------


def test_a_raid_is_recognised():
    event = parse_line(RAID)
    assert isinstance(event, ChatEvent)
    assert event.kind == "raid"


def test_a_raid_carries_how_many_people_arrived():
    assert parse_line(RAID).viewers == 212


def test_a_raid_carries_who_brought_them():
    assert parse_line(RAID).name == "Marco"
    assert parse_line(RAID).user_id == "4711"


def test_a_sub_is_recognised():
    assert parse_line(SUB).kind == "sub"


def test_a_sub_can_come_with_a_message():
    assert parse_line(SUB).text == "sono qui!"


def test_a_resub_carries_how_long_they_have_been_around():
    assert parse_line(RESUB).months == 14


def test_a_gifted_sub_names_who_got_it():
    assert parse_line(GIFT).recipient == "Ludo"


def test_a_pile_of_gifted_subs_carries_the_count():
    assert parse_line(MASS_GIFT).gifts == 20


def test_an_ordinary_message_is_still_an_ordinary_message():
    from src.core.skills.twitch.irc import ChatLine

    line = parse_line("@user-id=1;display-name=Marco :marco!marco@x PRIVMSG #ema :ciao")
    assert isinstance(line, ChatLine)


def test_an_event_kind_nobody_cares_about_is_dropped():
    assert parse_line(
        "@msg-id=viewermilestone;user-id=1 :tmi.twitch.tv USERNOTICE #ema"
    ) is None


def test_junk_is_still_junk():
    assert parse_line(":tmi.twitch.tv 001 bea :Welcome") is None


def test_a_usernotice_without_a_kind_is_dropped():
    assert parse_line("@user-id=1 :tmi.twitch.tv USERNOTICE #ema") is None


# --- what reaches her --------------------------------------------------------


async def test_a_raid_reaches_her(bus):
    s = skill(bus)
    await s._on_event(parse_line(RAID))
    assert len(drain(bus)) == 1


async def test_a_raid_is_impossible_to_ignore(bus):
    """Two hundred people just walked in. Not reacting is not an option."""
    s = skill(bus)
    await s._on_event(parse_line(RAID))
    perception = drain(bus)[0]
    assert perception.meta["addressed"] == "raid"
    assert perception.salience >= 0.9


async def test_a_raid_says_how_many(bus):
    s = skill(bus)
    await s._on_event(parse_line(RAID))
    assert "212" in drain(bus)[0].content


async def test_a_sub_reaches_her_as_the_gift_it_is(bus):
    s = skill(bus)
    await s._on_event(parse_line(SUB))
    perception = drain(bus)[0]
    assert perception.author.extra["amount"] > 0
    assert "Marco" in perception.content


async def test_a_resub_mentions_how_long_they_have_stayed(bus):
    s = skill(bus)
    await s._on_event(parse_line(RESUB))
    assert "14" in drain(bus)[0].content


async def test_a_gifted_sub_names_both_people(bus):
    s = skill(bus)
    await s._on_event(parse_line(GIFT))
    content = drain(bus)[0].content
    assert "Marco" in content and "Ludo" in content


async def test_events_can_be_switched_off(bus):
    s = skill(bus, announce_subs=False)
    await s._on_event(parse_line(SUB))
    assert drain(bus) == []


async def test_raids_can_be_switched_off_separately(bus):
    s = skill(bus, announce_raids=False, announce_subs=True)
    await s._on_event(parse_line(RAID))
    assert drain(bus) == []
    await s._on_event(parse_line(SUB))
    assert len(drain(bus)) == 1


async def test_an_inactive_skill_hears_nothing(bus):
    s = skill(bus)
    s.active = False
    await s._on_event(parse_line(RAID))
    assert drain(bus) == []


async def test_a_subscriber_is_counted_in_the_roster(bus):
    """A sub is the strongest signal someone is a regular, not a passer-by."""
    recorded = []

    class Roster:
        def record(self, **kwargs):
            recorded.append(kwargs)

    class Memory:
        roster = Roster()

    class Ctx:
        memory = Memory()

    s = skill(bus)
    s.context = Ctx()
    await s._on_event(parse_line(SUB))
    assert recorded and recorded[0]["identity"] == "twitch:4711"
    assert recorded[0]["donation"] > 0


# --- the rate limit reads its setting ----------------------------------------


def test_the_say_rate_limit_is_configurable(bus):
    assert skill(bus, say_rate_limit=5).limiter.limit == 5


def test_the_default_stays_under_what_twitch_punishes(bus):
    assert skill(bus).limiter.limit <= 20
