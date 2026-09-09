"""Being talked over, and knowing it.

Two separate things go wrong when someone interrupts her. The first is audible:
she used to be cut off mid-word instead of trailing off. The second is worse and
invisible — her history recorded the whole sentence, so she went on referring to
a second half the room never heard.
"""

import asyncio

import numpy as np

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.expression.chunking import spoken_prefix
from src.core.expression.voice import Expression
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Perception, PerceptionKind
from src.core.skills.base import SkillRegistry
from src.core.skills.voice.channel import VoiceChannel
from src.interfaces.base_interfaces import TTSInterface
from tests.fakes import (
    FakeAvatar,
    FakeCaption,
    FakeExpression,
    FakeHistory,
    FakeLLMClient,
    RecordingEvents,
)

# --- how much of it landed ---------------------------------------------------


def test_the_part_that_landed_stops_at_a_word():
    line = "allora la cosa che volevo dirti è che non mi convince per niente"
    heard = spoken_prefix(line, played_ms=1000, total_ms=4000)

    assert line.startswith(heard)
    assert not heard.endswith(" ")
    # a whole word, never half of one
    assert heard.split()[-1] in line.split()


def test_a_sentence_that_finished_is_reported_whole():
    assert spoken_prefix("ciao a tutti", 2000, 2000) == "ciao a tutti"


def test_being_cut_off_at_the_very_start_leaves_nothing():
    assert spoken_prefix("non ho fatto in tempo", 5, 4000) == ""


def test_a_line_with_no_duration_cannot_be_split():
    assert spoken_prefix("qualcosa", 100, 0) == ""


# --- what the mind is told ---------------------------------------------------


class Interrupted:
    """The utterance shape the channel hands back after a barge-in."""

    def __init__(self, text, played_ms, sent_ms, complete=False):
        self.text = text
        self.played_ms = played_ms
        self.sent_ms = sent_ms
        self.complete = complete


def mind() -> Consciousness:
    class Config:
        consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                         "burst_steps": 3, "history_limit": 30, "correlation_timeout": 5.0}
        attention = {"enabled": True, "trigger_words": ["bea"]}
        skills = {}

    return Consciousness(
        config=Config(), llm=FakeLLMClient(), bus=PerceptionBus(window=0.0),
        expression=FakeExpression(), surfaces=SkillRegistry(),
        history_manager=FakeHistory(), event_manager=RecordingEvents(),
        soul_getter=lambda: "soul", operating_getter=lambda: "rules",
        attention=Attention(Config()),
    )


def heard(content: str) -> Perception:
    return Perception(PerceptionKind.VOICE, "voice:discord", content, salience=0.85)


def test_she_is_told_where_she_actually_stopped():
    c = mind()
    c.expression.interrupted = Interrupted(
        "allora la cosa che volevo dirti è che non mi convince", played_ms=1800, sent_ms=3600)

    frame = c._frame([heard("[ema] (voice): no aspetta")])

    assert "[YOU WERE CUT OFF]" in frame["content"]
    assert "allora la cosa che volevo" in frame["content"]
    assert "non mi convince" not in frame["content"]


def test_a_sentence_nobody_heard_at_all_says_so():
    c = mind()
    c.expression.interrupted = Interrupted("stavo per dire una cosa", played_ms=0, sent_ms=2000)

    assert "before a word of that landed" in c._frame([heard("[ema] (voice): ...)")])["content"]


def test_a_sentence_that_finished_is_never_mentioned():
    """Only a real cut-off is worth spending context on."""
    c = mind()
    c.expression.interrupted = Interrupted("detta tutta", 2000, 2000, complete=True)

    assert "[YOU WERE CUT OFF]" not in c._frame([heard("[ema] (voice): ok")])["content"]


def test_she_is_told_once_and_not_every_turn_after():
    c = mind()
    c.expression.interrupted = Interrupted("una frase lunga che è stata tagliata", 500, 3000)

    first = c._frame([heard("[ema] (voice): scusa")])
    second = c._frame([heard("[ema] (voice): dicevi?")])

    assert "[YOU WERE CUT OFF]" in first["content"]
    assert "[YOU WERE CUT OFF]" not in second["content"]


# --- is she still talking ----------------------------------------------------


class SilentTTS(TTSInterface):
    async def generate_audio(self, text, prosody=None):
        return np.zeros(2400, dtype=np.float32), 24000

    async def speak(self, text, output_device_id):
        pass

    def reload_config(self, config):
        pass


class Config:
    text_font_size = 40
    text_line_width = 30
    text_lines = 3
    text_min_font_size = 20
    text_font_step = 2
    typing_delay = 0.0
    text_min_duration = 0.0
    obs_text_source = ""
    obs_source_type = "image"
    audio_device_id = None


class Events:
    def publish(self, *a, **k):
        pass


class Socket:
    async def send_bytes(self, data):
        pass

    async def send_text(self, data):
        pass


def test_the_call_has_the_last_word_on_whether_she_is_talking():
    """The OBS animation only ever knew the *estimated* length of the audio."""
    e = Expression(Config(), SilentTTS(), FakeAvatar(), FakeCaption(), Events())
    channel = VoiceChannel()
    channel.attach(Socket())
    channel.on_message({"type": "joined", "channel_id": "c1", "listeners": 1})
    e.set_call(channel)

    assert e.is_speaking is False

    channel.utterances["u1"] = type("U", (), {"id": "u1"})()
    channel.current = channel.utterances["u1"]
    assert e.is_speaking is True

    channel.current = None
    assert e.is_speaking is False


async def test_an_interruption_reaches_the_call_and_not_only_the_speakers():
    e = Expression(Config(), SilentTTS(), FakeAvatar(), FakeCaption(), Events())
    channel = VoiceChannel()
    channel.attach(Socket())
    channel.on_message({"type": "joined", "channel_id": "c1", "listeners": 1})
    e.set_call(channel)

    await e.speak("normal", "una frase abbastanza lunga da poter essere tagliata", route="call")
    utterance_id = channel.current.id

    async def bot_answers():
        await asyncio.sleep(0)
        channel.on_message({"type": "playback", "utterance_id": utterance_id,
                            "played_ms": 30, "state": "stopped"})

    asyncio.create_task(bot_answers())
    await e.interrupt(ramp_ms=200)

    assert e.interrupted is not None
    assert e.interrupted.played_ms == 30
    assert not e.interrupted.complete
