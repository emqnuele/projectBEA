"""Telegram was text-only, and blind to everything else.

A photo, a sticker, a voice note: none of them reached her. The extractor even
read `caption`, which could never arrive, because the handler filtered
captions out before they got there.
"""

import pytest

from src.core.perception.bus import PerceptionBus
from src.core.skills.telegram.handlers import describe_message, message_text
from src.core.skills.telegram.surface import TelegramSkill


class Config:
    def __init__(self, **telegram):
        self.skills = {"telegram": {"enabled": True, **telegram}}
        self.attention = {"trigger_words": ["bea"]}


class Msg:
    """Only the fields the extractor looks at."""

    def __init__(self, **kwargs):
        self.text = None
        self.caption = None
        self.sticker = None
        self.photo = None
        self.voice = None
        self.video = None
        self.video_note = None
        self.animation = None
        self.document = None
        self.audio = None
        self.__dict__.update(kwargs)


class Sticker:
    def __init__(self, emoji="", set_name=""):
        self.emoji = emoji
        self.set_name = set_name


class File:
    def __init__(self, file_id="f1", file_name=""):
        self.file_id = file_id
        self.file_name = file_name


@pytest.fixture
def bus():
    return PerceptionBus(window=0.0)


def skill(bus, **telegram) -> TelegramSkill:
    s = TelegramSkill(Config(**telegram), bus=bus, expression=None)
    s.initialize()
    s.active = True
    return s


# --- describing what arrived -------------------------------------------------


def test_text_is_still_just_text():
    assert describe_message(Msg(text="ciao")) == "ciao"


def test_a_photo_says_it_is_a_photo():
    assert describe_message(Msg(photo=[File()])) == "[photo]"


def test_a_photo_with_a_caption_carries_the_caption():
    assert describe_message(Msg(photo=[File()], caption="guarda qui")) == "[photo] guarda qui"


def test_a_sticker_carries_its_emoji():
    assert describe_message(Msg(sticker=Sticker(emoji="🗿"))) == "[sticker 🗿]"


def test_a_sticker_without_an_emoji_is_still_a_sticker():
    assert describe_message(Msg(sticker=Sticker())) == "[sticker]"


def test_a_voice_note_is_announced():
    assert describe_message(Msg(voice=File())) == "[voice note]"


def test_a_video_is_announced():
    assert describe_message(Msg(video=File())) == "[video]"


def test_a_video_note_is_its_own_thing():
    assert describe_message(Msg(video_note=File())) == "[video message]"


def test_a_gif_is_announced():
    assert describe_message(Msg(animation=File())) == "[gif]"


def test_a_document_carries_its_name():
    assert describe_message(Msg(document=File(file_name="tesi.pdf"))) == "[file: tesi.pdf]"


def test_a_nameless_document_is_still_a_file():
    assert describe_message(Msg(document=File())) == "[file]"


def test_an_empty_message_describes_as_nothing():
    assert describe_message(Msg()) == ""


def test_the_old_extractor_still_works():
    assert message_text(Msg(text=" ciao ")) == "ciao"


# --- what reaches the bus ----------------------------------------------------


class User:
    def __init__(self, uid=2, name="Ema"):
        self.id = uid
        self.full_name = name
        self.username = "ema"
        self.is_bot = False


class Chat:
    def __init__(self, cid=2, ctype="private", title=""):
        self.id = cid
        self.type = ctype
        self.title = title


def incoming(**kwargs) -> Msg:
    message = Msg(**kwargs)
    message.chat = Chat()
    message.from_user = User()
    message.message_id = 10
    message.reply_to_message = None
    return message


async def test_a_photo_now_reaches_her(bus):
    s = skill(bus)
    await s._on_message(_update(incoming(photo=[File()], caption="guarda")), None)
    perceptions = bus.drain_nowait()
    assert len(perceptions) == 1
    assert "guarda" in perceptions[0].content


async def test_a_sticker_now_reaches_her(bus):
    s = skill(bus)
    await s._on_message(_update(incoming(sticker=Sticker(emoji="🗿"))), None)
    assert "🗿" in bus.drain_nowait()[0].content


async def test_media_can_be_switched_off(bus):
    s = skill(bus, read_media=False)
    await s._on_message(_update(incoming(photo=[File()])), None)
    assert bus.drain_nowait() == []


async def test_switching_media_off_does_not_make_her_deaf_to_text(bus):
    s = skill(bus, read_media=False)
    await s._on_message(_update(incoming(text="ciao")), None)
    assert len(bus.drain_nowait()) == 1


async def test_a_message_with_nothing_in_it_is_ignored(bus):
    s = skill(bus)
    await s._on_message(_update(incoming()), None)
    assert bus.drain_nowait() == []


async def test_the_kind_of_media_is_on_the_perception(bus):
    s = skill(bus)
    await s._on_message(_update(incoming(photo=[File()])), None)
    assert bus.drain_nowait()[0].meta["media"] == "photo"


async def test_plain_text_is_not_flagged_as_media(bus):
    s = skill(bus)
    await s._on_message(_update(incoming(text="ciao")), None)
    assert bus.drain_nowait()[0].meta.get("media") == ""


class _Update:
    def __init__(self, message):
        self.message = message


def _update(message):
    return _Update(message)


# --- voice notes she can actually answer -------------------------------------


class FakeSTT:
    def __init__(self, transcript="ciao come stai"):
        self.transcript = transcript
        self.files = []

    def transcribe(self, path):
        self.files.append(path)
        return self.transcript


class FakeBot:
    def __init__(self):
        self.downloaded = []
        self.reactions = []

    async def get_file(self, file_id):
        self.downloaded.append(file_id)

        class F:
            async def download_to_drive(self, path):
                open(path, "wb").write(b"RIFF")

        return F()

    async def set_message_reaction(self, **kwargs):
        self.reactions.append(kwargs)


class FakeApp:
    def __init__(self):
        self.bot = FakeBot()


async def test_a_voice_note_is_transcribed(bus, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = skill(bus)
    s.app = FakeApp()
    s.stt = FakeSTT("mi sono rotto un dente")
    await s._on_message(_update(incoming(voice=File("v1"))), None)
    perception = bus.drain_nowait()[0]
    assert "mi sono rotto un dente" in perception.content
    assert s.app.bot.downloaded == ["v1"]


async def test_an_untranscribable_voice_note_still_reaches_her(bus, tmp_path, monkeypatch):
    """Better "they sent a voice note" than silence."""
    monkeypatch.chdir(tmp_path)
    s = skill(bus)
    s.app = FakeApp()
    s.stt = FakeSTT("")
    await s._on_message(_update(incoming(voice=File("v1"))), None)
    assert bus.drain_nowait()[0].content.endswith("[voice note]")


async def test_transcription_can_be_switched_off(bus, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = skill(bus, transcribe_voice=False)
    s.app = FakeApp()
    s.stt = FakeSTT("non dovrebbe servire")
    await s._on_message(_update(incoming(voice=File("v1"))), None)
    assert s.app.bot.downloaded == []
    assert bus.drain_nowait()[0].content.endswith("[voice note]")


async def test_a_broken_download_does_not_lose_the_message(bus, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class Broken(FakeBot):
        async def get_file(self, file_id):
            raise RuntimeError("telegram is having a moment")

    s = skill(bus)
    s.app = FakeApp()
    s.app.bot = Broken()
    s.stt = FakeSTT()
    await s._on_message(_update(incoming(voice=File("v1"))), None)
    assert len(bus.drain_nowait()) == 1


# --- reacting instead of writing ---------------------------------------------


def test_reactions_are_on_by_default(bus):
    assert skill(bus).supports_reactions is True


def test_reactions_can_be_switched_off(bus):
    assert skill(bus, reactions=False).supports_reactions is False


async def test_she_can_react_to_a_message(bus):
    s = skill(bus)
    s.app = FakeApp()
    assert await s.react("2", "10", "🔥") is True
    assert s.app.bot.reactions[0]["chat_id"] == 2
    assert s.app.bot.reactions[0]["message_id"] == 10


async def test_a_reaction_telegram_refuses_is_reported_as_failed(bus):
    class Refusing(FakeBot):
        async def set_message_reaction(self, **kwargs):
            raise RuntimeError("REACTION_INVALID")

    s = skill(bus)
    s.app = FakeApp()
    s.app.bot = Refusing()
    assert await s.react("2", "10", "🥑") is False


async def test_reacting_without_a_connection_fails_quietly(bus):
    assert await skill(bus).react("2", "10", "🔥") is False
