"""Telegram, and the proof that `PlatformSkill` is a real abstraction.

A whole platform is a transport plus an `Author` builder: everything above is
keyed on `Author` and `conversation_key`, not on the platform.
"""

import pytest

from src.core.mind.routing import conversation_key
from src.core.perception.bus import PerceptionBus
from src.core.skills.telegram.handlers import display_name, is_bot_called, message_text
from src.core.skills.telegram.surface import TelegramSkill

TRIGGERS = ["bea", "beatrice"]


# --- is_bot_called (pure) ----------------------------------------------------


def test_her_name_calls_her():
    assert is_bot_called("ciao bea come va", trigger_words=TRIGGERS) is True


def test_a_typo_in_her_name_still_calls_her():
    assert is_bot_called("ciao beatrcie", trigger_words=TRIGGERS) is True


@pytest.mark.parametrize("text", ["what a beautiful beach", "beat that", "il bear"])
def test_a_lookalike_word_does_not(text):
    assert is_bot_called(text, trigger_words=TRIGGERS) is False


def test_an_at_mention_calls_her():
    assert is_bot_called("ehi @beabot vieni", bot_username="BeaBot",
                         trigger_words=TRIGGERS) is True


def test_a_reply_to_her_calls_her():
    assert is_bot_called("e quindi?", bot_id=42, reply_to_user_id=42,
                         trigger_words=TRIGGERS) is True


def test_a_reply_to_someone_else_does_not():
    assert is_bot_called("e quindi?", bot_id=42, reply_to_user_id=7,
                         trigger_words=TRIGGERS) is False


def test_an_empty_message_calls_nobody():
    assert is_bot_called("", trigger_words=TRIGGERS) is False
    assert is_bot_called(None, trigger_words=TRIGGERS) is False


# --- small extractors --------------------------------------------------------


class Msg:
    def __init__(self, text=None, caption=None):
        self.text = text
        self.caption = caption


def test_text_is_read_from_either_field():
    assert message_text(Msg(text=" ciao ")) == "ciao"
    assert message_text(Msg(caption="una foto")) == "una foto"
    assert message_text(Msg()) == ""


class User:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_a_display_name_prefers_the_full_name():
    assert display_name(User(full_name="Marco Rossi", username="mrossi", id=1)) == "Marco Rossi"


def test_a_display_name_falls_back_to_the_username_then_the_id():
    assert display_name(User(full_name="", username="mrossi", id=1)) == "mrossi"
    assert display_name(User(full_name="", username="", id=7)) == "7"
    assert display_name(None) == "someone"


# --- the skill ---------------------------------------------------------------


class Config:
    def __init__(self, **telegram):
        block = {"enabled": True, "owner_id": "", "allowed_chats": []}
        block.update(telegram)
        self.skills = {"telegram": block}
        self.attention = {"trigger_words": TRIGGERS}


def skill(**telegram) -> TelegramSkill:
    s = TelegramSkill(Config(**telegram), bus=PerceptionBus(window=0.0), expression=None)
    s.initialize()
    s.active = True
    return s


def test_an_author_carries_a_stable_identity():
    author = skill().build_author(4711, "marco")
    assert author.identity == "telegram:4711"
    assert author.display_name == "marco"


def test_the_identity_is_the_id_not_the_name():
    """Names change; a roster keyed on them would merge or split people."""
    s = skill()
    assert s.build_author(4711, "marco").identity == \
        s.build_author(4711, "marco_nuovo_nome").identity


def test_the_owner_is_recognised():
    s = skill(owner_id="4711")
    assert s._author(User(id=4711, full_name="ema", username="ema")).is_owner is True
    assert s._author(User(id=999, full_name="altro", username="a")).is_owner is False


def test_a_conversation_key_is_platform_and_chat():
    assert skill().conversation_key(-100999) == "telegram:-100999"


def test_an_empty_allowlist_means_every_chat():
    s = skill(allowed_chats=[])
    assert s._allowed(123) is True


def test_an_allowlist_keeps_the_rest_out():
    s = skill(allowed_chats=["123"])
    assert s._allowed(123) is True
    assert s._allowed(456) is False


# --- perceiving --------------------------------------------------------------


def perceive(s: TelegramSkill, text="ciao", **kwargs):
    return s.perceive_text(text, author=s.build_author(1, "marco"),
                           channel_id=-100, message_id="55", **kwargs)


def test_a_message_lands_on_the_bus_as_its_own_conversation():
    s = skill()
    p = perceive(s)
    assert conversation_key(p) == "telegram:-100"
    assert s.bus.drain_nowait() == [p]


def test_the_perception_carries_what_the_gate_needs():
    """`is_dm`, `mentions_self` and `reply_to_self` are what make being addressed
    deterministic — and being addressed is what bypasses cooldowns."""
    p = perceive(skill(), is_dm=True, mentions_self=True, reply_to_self=True)
    assert p.meta["is_dm"] is True
    assert p.meta["mentions_self"] is True
    assert p.meta["reply_to_self"] is True


def test_the_author_reaches_the_perception():
    p = perceive(skill())
    assert p.author.identity == "telegram:1"


def test_a_dm_pulls_harder_than_a_group_line():
    assert perceive(skill(), is_dm=True).salience > perceive(skill()).salience


# --- sending -----------------------------------------------------------------


class Recorder(TelegramSkill):
    """Captures what the transport would have sent."""

    def __init__(self, config):
        super().__init__(config, bus=PerceptionBus(window=0.0), expression=None)
        self.initialize()
        self.active = True
        self.sent = []
        self.typing = []
        self.fail = False

    async def send_text(self, channel_id, text, reply_to=None):
        if self.fail:
            return False
        self.sent.append((channel_id, text, reply_to))
        return True

    async def send_typing(self, channel_id):
        self.typing.append(channel_id)


def recorder(**telegram) -> Recorder:
    r = Recorder(Config(**telegram))
    r.humanizer._sleep = _instant
    return r


async def _instant(seconds):
    return None


async def test_a_multiline_reply_arrives_as_separate_messages():
    r = recorder()
    sent = await r.deliver("-100", "prima riga\nseconda riga")
    assert sent == ["prima riga", "seconda riga"]
    assert [t for _, t, _ in r.sent] == ["prima riga", "seconda riga"]


async def test_typing_is_shown_between_messages():
    r = recorder()
    await r.deliver("-100", "una\ndue")
    assert r.typing == ["-100", "-100"]


async def test_only_the_first_message_quotes_theirs():
    r = recorder()
    await r.deliver("-100", "una\ndue", reply_to="55")
    assert [reply for _, _, reply in r.sent] == ["55", None]


async def test_a_failed_send_is_not_reported_as_sent():
    r = recorder()
    r.fail = True
    assert await r.deliver("-100", "ciao") == []


async def test_the_scoped_tools_are_the_platform_ones_only():
    r = recorder()
    names = {t.name for t in r.conversation_tools("-100", reply_to="55")}
    assert names == {"reply", "send_message", "react"}
    assert "speak" not in names


async def test_without_reactions_she_only_has_words():
    r = recorder(reactions=False)
    names = {t.name for t in r.conversation_tools("-100", reply_to="55")}
    assert names == {"reply", "send_message"}


async def test_without_a_channel_there_are_no_tools():
    assert recorder().conversation_tools(None) == []


async def test_the_scoped_send_tool_writes_in_the_bound_channel():
    r = recorder()
    tool = next(t for t in r.conversation_tools("-100") if t.name == "send_message")
    result = await tool.handler(text="eccomi")
    assert r.sent == [("-100", "eccomi", None)]
    assert "1 message(s)" in result
