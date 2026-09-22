"""Telegram group pull is a wired knob, not a displayed one.

`group_salience` was declared at 0.6 but never read, so every group message
actually pulled at 0.8. Wiring it without a migration would quietly move every
install that ever saved Telegram settings from 0.8 to 0.6.
"""

import json

import pytest

from src.core.config import BrainConfig
from src.core.perception.bus import PerceptionBus
from src.core.settings_schema import section
from src.core.skills.telegram.surface import TelegramSkill


class Config:
    def __init__(self, **telegram):
        self.skills = {"telegram": {"enabled": True, **telegram}}
        self.attention = {"trigger_words": ["bea"]}
        self.timezone = ""


class User:
    def __init__(self, uid=2, name="Ema"):
        self.id = uid
        self.full_name = name
        self.username = "ema"
        self.is_bot = False


class Chat:
    def __init__(self, cid=7, ctype="group", title="amici"):
        self.id = cid
        self.type = ctype
        self.title = title


class Msg:
    def __init__(self, text="ciao bea", chat=None):
        self.text = text
        self.caption = None
        self.sticker = None
        self.photo = None
        self.voice = None
        self.video = None
        self.video_note = None
        self.animation = None
        self.document = None
        self.audio = None
        self.chat = chat or Chat()
        self.from_user = User()
        self.message_id = 10
        self.reply_to_message = None


class Update:
    def __init__(self, message):
        self.message = message


@pytest.fixture
def bus():
    return PerceptionBus(window=0.0)


def skill(bus, **telegram) -> TelegramSkill:
    s = TelegramSkill(Config(**telegram), bus=bus, expression=None)
    s.initialize()
    s.active = True
    return s


def test_the_schema_default_is_the_historical_pull():
    assert section("telegram").get("group_salience").default == 0.8


async def test_a_group_message_pulls_at_the_historical_default(bus):
    await skill(bus)._on_message(Update(Msg()), None)
    assert bus.drain_nowait()[0].salience == 0.8


async def test_a_dm_still_pulls_like_a_dm(bus):
    msg = Msg(chat=Chat(cid=2, ctype="private"))
    await skill(bus)._on_message(Update(msg), None)
    assert bus.drain_nowait()[0].salience == 0.9


async def test_a_chosen_group_pull_is_honoured(bus):
    await skill(bus, group_salience=0.3)._on_message(Update(Msg()), None)
    assert bus.drain_nowait()[0].salience == 0.3


async def test_a_dm_ignores_the_group_knob(bus):
    msg = Msg(chat=Chat(cid=2, ctype="private"))
    await skill(bus, group_salience=0.3)._on_message(Update(msg), None)
    assert bus.drain_nowait()[0].salience == 0.9


def test_a_stored_old_default_is_not_a_choice(tmp_path, monkeypatch):
    """0.6 on disk is the default that was never read, not an answer."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"skills": {"telegram": {"group_salience": 0.6}}}),
        encoding="utf-8",
    )
    config = BrainConfig()
    config.load_from_file()
    assert "group_salience" not in config.skills["telegram"]


def test_a_chosen_value_survives_the_migration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"skills": {"telegram": {"group_salience": 0.5}}}),
        encoding="utf-8",
    )
    config = BrainConfig()
    config.load_from_file()
    assert config.skills["telegram"]["group_salience"] == 0.5
