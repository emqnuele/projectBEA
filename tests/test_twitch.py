"""Twitch: the phase-7 definition of done — high volume that costs almost nothing."""

import asyncio
import random
import time

import pytest

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.memory.store import MemoryStore
from src.core.mind.routing import STAGE, conversation_key
from src.core.perception.bus import PerceptionBus
from src.core.skills.base import SkillRegistry
from src.core.skills.twitch.irc import ChatLine, parse_line, parse_tags
from src.core.skills.twitch.surface import TwitchSkill
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents, speaks

PRIVMSG = ("@badge-info=;badges=moderator/1;color=#1E90FF;display-name=Marco;"
           "mod=1;subscriber=1;user-id=4711 "
           ":marco!marco@marco.tmi.twitch.tv PRIVMSG #beastream :ciao a tutti")


# --- parsing (pure) ----------------------------------------------------------


def test_tags_are_split_into_pairs():
    assert parse_tags("a=1;b=2") == {"a": "1", "b": "2"}


def test_an_empty_tag_string_is_empty():
    assert parse_tags("") == {}


def test_escaped_spaces_are_restored():
    assert parse_tags(r"display-name=Marco\sRossi")["display-name"] == "Marco Rossi"


def test_a_privmsg_is_parsed():
    line = parse_line(PRIVMSG)
    assert line is not None
    assert line.nick == "marco"
    assert line.display_name == "Marco"
    assert line.user_id == "4711"
    assert line.channel == "beastream"
    assert line.text == "ciao a tutti"
    assert line.is_moderator is True
    assert line.is_subscriber is True


def test_a_message_with_colons_keeps_them():
    raw = ":x!x@x PRIVMSG #c :guarda qui: https://esempio.it"
    assert parse_line(raw).text == "guarda qui: https://esempio.it"


def test_bits_are_read_as_a_number():
    raw = "@bits=500;user-id=9 :x!x@x PRIVMSG #c :cheer500 tieni"
    assert parse_line(raw).bits == 500


def test_broken_bits_do_not_raise():
    raw = "@bits=notanumber;user-id=9 :x!x@x PRIVMSG #c :ciao"
    assert parse_line(raw).bits == 0


@pytest.mark.parametrize("raw", [
    "PING :tmi.twitch.tv",
    ":tmi.twitch.tv 001 justinfan1 :Welcome",
    ":x!x@x JOIN #c",
    "",
])
def test_anything_that_is_not_a_message_is_ignored(raw):
    assert parse_line(raw) is None


def test_a_display_name_falls_back_to_the_nick():
    assert ChatLine(nick="marco", channel="c", text="x").name == "marco"


# --- the skill ---------------------------------------------------------------


class Context:
    def __init__(self, store):
        self.memory = store
        self.history_manager = FakeHistory()


class Config:
    def __init__(self, **twitch):
        block = {"enabled": True, "channel": "beastream", "nick": ""}
        block.update(twitch)
        self.skills = {"twitch": block}
        self.attention = {"enabled": True, "trigger_words": ["bea"], "cooldown_seconds": 20}
        self.consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                              "burst_steps": 3, "history_limit": 30,
                              "correlation_timeout": 5.0}


@pytest.fixture
def twitch():
    store = MemoryStore(":memory:")
    bus = PerceptionBus(window=0.0)
    skill = TwitchSkill(Config(), bus=bus, expression=None, context=Context(store))
    skill.initialize()
    skill.active = True
    yield skill, store, bus
    store.close()


def line(text="ciao", nick="marco", user_id="4711", bits=0) -> ChatLine:
    return ChatLine(nick=nick, channel="beastream", text=text,
                    user_id=user_id, display_name=nick.capitalize(), bits=bits)


async def test_chat_belongs_to_the_stage_not_to_a_thread(twitch):
    """A streamer answers chat out loud; making it a text thread would have her
    typing instead of talking."""
    skill, _, bus = twitch
    await skill._on_message(line())
    assert conversation_key(bus.drain_nowait()[0]) == STAGE


async def test_every_message_is_tallied_even_when_ignored(twitch):
    skill, store, _ = twitch
    for _ in range(5):
        await skill._on_message(line())
    assert store.roster.get("twitch:4711").message_count == 5


async def test_the_identity_is_the_twitch_user_id(twitch):
    skill, store, _ = twitch
    await skill._on_message(line(nick="marco", user_id="4711"))
    await skill._on_message(line(nick="marco_renamed", user_id="4711"))
    assert len(store.roster.all()) == 1
    assert store.roster.get("twitch:4711").display_name == "Marco_renamed"


async def test_bits_are_recorded_as_money(twitch):
    skill, store, _ = twitch
    await skill._on_message(line(text="cheer500", bits=500))
    assert store.roster.get("twitch:4711").donation_total == pytest.approx(5.0)


async def test_a_cheer_pulls_much_harder_than_chatter(twitch):
    skill, _, bus = twitch
    await skill._on_message(line(text="cheer100", bits=100))
    await skill._on_message(line(text="ciao"))
    cheer, chatter = bus.drain_nowait()
    assert cheer.salience > chatter.salience


# --- chat as texture ---------------------------------------------------------


async def test_a_silent_chat_has_no_pulse(twitch):
    skill, _, _ = twitch
    assert skill.pulse() == ""
    assert skill.live_state() is None


async def test_the_pulse_counts_the_last_minute(twitch):
    skill, _, _ = twitch
    for _ in range(12):
        await skill._on_message(line())
    assert "12 messages in the last minute" in skill.pulse()


async def test_old_messages_fall_out_of_the_pulse(twitch):
    skill, _, _ = twitch
    skill._recent.append((time.time() - 300, "vecchio"))
    await skill._on_message(line())
    assert "1 messages" in skill.pulse()


async def test_the_pulse_says_what_chat_is_on_about(twitch):
    skill, _, _ = twitch
    for _ in range(4):
        await skill._on_message(line(text="parliamo di minecraft"))
    assert "minecraft" in skill.pulse()


def test_common_words_are_not_what_chat_is_about():
    assert TwitchSkill._top_terms(["che cosa non sono", "che cosa non sono"]) == []


def test_something_one_person_said_once_is_not_a_topic():
    assert TwitchSkill._top_terms(["ferrari", "pizza", "gattini"]) == []


# --- the definition of done --------------------------------------------------


async def test_thirty_messages_a_minute_stay_under_four_model_calls(twitch):
    """Phase-7 definition of done. Without the gate this would be 30 calls."""
    skill, store, bus = twitch
    config = Config()
    rng = random.Random(7)
    mind = Consciousness(
        config=config, llm=(llm := FakeLLMClient([speaks(f"line {i}") for i in range(40)])),
        bus=bus, expression=FakeExpression(), surfaces=SkillRegistry(),
        history_manager=FakeHistory(), event_manager=RecordingEvents(),
        soul_getter=lambda: "soul", operating_getter=lambda: "rules",
        attention=Attention(config, roster=store.roster, rng=rng),
    )
    mind.context = [mind._system_message([])]

    for i in range(30):
        await skill._on_message(line(text=f"messaggio numero {i}",
                                     nick=f"user{i % 7}", user_id=str(i % 7)))

    mind.alive = True
    task = asyncio.create_task(mind.run())
    deadline = asyncio.get_event_loop().time() + 2.0
    while bus._queue.qsize() and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.05)
    mind.alive = False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert llm.call_count <= 4, f"{llm.call_count} model calls for 30 chat messages"


async def test_being_named_in_a_busy_chat_always_gets_through(twitch):
    skill, store, bus = twitch
    config = Config()
    rng = random.Random()
    rng.uniform = lambda a, b: 0.0
    mind = Consciousness(
        config=config, llm=(llm := FakeLLMClient([speaks("che c'e'")])), bus=bus,
        expression=FakeExpression(), surfaces=SkillRegistry(),
        history_manager=FakeHistory(), event_manager=RecordingEvents(),
        soul_getter=lambda: "soul", operating_getter=lambda: "rules",
        attention=Attention(config, roster=store.roster, rng=rng),
    )
    mind.context = [mind._system_message([])]

    await skill._on_message(line(text="bea guarda questo", nick="marco"))

    mind.alive = True
    task = asyncio.create_task(mind.run())
    await asyncio.sleep(0.05)
    mind.alive = False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert llm.call_count == 1
    assert mind.expression.spoken == [("normal", "che c'e'", "local")]
