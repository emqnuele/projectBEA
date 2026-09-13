"""The push channel: the pipe that lets her open her mouth on her own clock.

The two things worth guarding here are the ones the old HTTP path got wrong:
every sentence of a turn has to reach the room, and she has to find out how much
of one the room actually got.
"""

import asyncio

import numpy as np
import pytest

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.expression.pcm import CALL_SAMPLE_RATE, duration_ms, split_at_ms, to_call_pcm
from src.core.perception.bus import PerceptionBus
from src.core.skills.base import SkillRegistry
from src.core.skills.voice.channel import VoiceChannel, frame, unframe
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents, settle


class Socket:
    """A websocket that remembers instead of sending."""

    def __init__(self, fail: bool = False):
        self.binary = []
        self.text = []
        self.fail = fail

    async def send_bytes(self, data):
        if self.fail:
            raise ConnectionError("socket is gone")
        self.binary.append(data)

    async def send_text(self, data):
        if self.fail:
            raise ConnectionError("socket is gone")
        self.text.append(data)


def tone(seconds: float = 0.5, rate: int = 24000) -> np.ndarray:
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


# --- what goes on the wire ---------------------------------------------------


def test_a_frame_carries_its_header_with_its_payload():
    header, payload = unframe(frame({"type": "play", "seq": 3}, b"\x01\x02"))
    assert header == {"type": "play", "seq": 3}
    assert payload == b"\x01\x02"


def test_a_truncated_frame_is_refused_rather_than_guessed():
    with pytest.raises(ValueError):
        unframe(frame({"type": "play"}, b"abc")[:6])


# --- the channel -------------------------------------------------------------


async def test_nothing_is_live_until_the_bot_is_in_a_call():
    channel = VoiceChannel()
    assert not channel.live

    channel.attach(Socket())
    assert channel.connected and not channel.live

    channel.on_message({"type": "joined", "channel_id": "c1", "listeners": 2})
    assert channel.live and channel.listeners == 2


async def test_audio_reaches_the_bot_as_one_frame():
    channel, socket = VoiceChannel(), Socket()
    channel.attach(socket)
    pcm = to_call_pcm(tone(0.2), 24000)

    assert await channel.play(pcm, utterance_id="u1", text="ciao") is True

    header, payload = unframe(socket.binary[0])
    assert header["type"] == "play" and header["utterance_id"] == "u1" and header["last"] is True
    assert payload == pcm
    assert channel.utterances["u1"].sent_ms == pytest.approx(200, abs=2)


async def test_every_sentence_of_a_turn_reaches_the_same_utterance():
    """The old path delivered only the first one; the rest went to the speakers."""
    channel, socket = VoiceChannel(), Socket()
    channel.attach(socket)
    pcm = to_call_pcm(tone(0.1), 24000)

    await channel.play(pcm, utterance_id="u1", seq=0, last=False)
    await channel.play(pcm, utterance_id="u1", seq=1, last=True)

    assert len(socket.binary) == 2
    assert channel.utterances["u1"].sent_ms == pytest.approx(200, abs=4)


async def test_with_nobody_listening_the_audio_simply_does_not_leave():
    channel = VoiceChannel()
    assert await channel.play(b"\x00" * 100, utterance_id="u1") is False


async def test_a_socket_that_dies_mid_send_detaches_instead_of_raising():
    channel = VoiceChannel()
    channel.attach(Socket(fail=True))
    channel.on_message({"type": "joined", "channel_id": "c1", "listeners": 1})

    assert await channel.play(b"\x00" * 400, utterance_id="u1") is False
    assert not channel.live


async def test_stopping_reports_how_much_the_room_actually_heard():
    channel, socket = VoiceChannel(), Socket()
    channel.attach(socket)
    await channel.play(to_call_pcm(tone(2.0), 24000), utterance_id="u1", text="una frase lunga")

    async def bot_answers():
        await asyncio.sleep(0)
        channel.on_message({"type": "playback", "utterance_id": "u1",
                            "played_ms": 700, "state": "stopped"})

    asyncio.create_task(bot_answers())
    utterance = await channel.stop(ramp_ms=200)

    assert utterance.played_ms == 700
    assert not utterance.complete
    assert '"type":"stop"' in socket.text[0]


async def test_a_bot_that_never_answers_is_assumed_to_have_played_it_all():
    """A missing report must not hang the turn that asked."""
    channel = VoiceChannel()
    channel.attach(Socket())
    await channel.play(to_call_pcm(tone(0.5), 24000), utterance_id="u1")

    utterance = await channel.stop(ramp_ms=0, timeout=0.01)
    assert utterance.complete


async def test_the_first_sound_in_the_room_stops_the_latency_clock():
    channel, heard = VoiceChannel(), []
    channel.attach(Socket())
    channel.on_first_sound = lambda: heard.append(True)

    await channel.play(to_call_pcm(tone(0.3), 24000), utterance_id="u1")
    channel.on_message({"type": "playback", "utterance_id": "u1", "played_ms": 0, "state": "playing"})
    channel.on_message({"type": "playback", "utterance_id": "u1", "played_ms": 250, "state": "playing"})

    assert heard == [True]


async def test_leaving_the_call_ends_whatever_was_playing():
    channel = VoiceChannel()
    channel.attach(Socket())
    channel.on_message({"type": "joined", "channel_id": "c1", "listeners": 1})
    await channel.play(to_call_pcm(tone(1.0), 24000), utterance_id="u1")

    channel.on_message({"type": "left"})

    assert not channel.live
    assert channel.current is None
    assert channel.utterances["u1"].done.is_set()


async def test_the_call_reports_who_is_in_it():
    channel, seen = VoiceChannel(), []
    channel.on_call_change = lambda cid, n: seen.append((cid, n))

    channel.on_message({"type": "joined", "channel_id": "c1", "listeners": 1})
    channel.on_message({"type": "members", "listeners": 3})
    channel.on_message({"type": "left"})

    assert seen == [("c1", 1), ("c1", 3), (None, 0)]


# --- the mind speaking into it -----------------------------------------------


class LiveCall:
    def __init__(self):
        self.played = []
        self.live = True

    async def play(self, pcm, *, utterance_id, text="", seq=0, last=True):
        self.played.append(text)
        return True


def mind(call=None) -> Consciousness:
    class Config:
        consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                         "burst_steps": 3, "history_limit": 30, "correlation_timeout": 5.0}
        attention = {"enabled": True, "trigger_words": ["bea"]}
        skills = {}

    expression = FakeExpression()
    expression.set_call(call)
    return Consciousness(
        config=Config(), llm=FakeLLMClient(), bus=PerceptionBus(window=0.0),
        expression=expression, surfaces=SkillRegistry(),
        history_manager=FakeHistory(), event_manager=RecordingEvents(),
        soul_getter=lambda: "soul", operating_getter=lambda: "rules",
        attention=Attention(Config()),
    )


async def test_in_a_call_both_sentences_of_a_turn_go_to_the_room():
    """The whole reason the push channel exists."""
    c = mind(call=LiveCall())
    await c._speak("neutral", "aspetta")
    await c._speak("neutral", "no davvero, aspetta")
    await settle()

    assert c.expression.spoken == [("neutral", "aspetta", "call"),
                                   ("neutral", "no davvero, aspetta", "call")]


async def test_with_no_call_she_still_speaks_out_of_the_speakers():
    c = mind(call=None)
    await c._speak("neutral", "ma che vuoi")
    await settle()

    assert c.expression.spoken == [("neutral", "ma che vuoi", "local")]


# --- the samples themselves --------------------------------------------------


def test_whatever_the_engine_produced_comes_out_as_the_call_wants_it():
    pcm = to_call_pcm(tone(1.0, rate=24000), 24000)
    # one second, 48 kHz, two channels, two bytes a sample
    assert len(pcm) == CALL_SAMPLE_RATE * 2 * 2
    assert duration_ms(pcm) == 1000


def test_an_engine_that_hands_back_int16_is_not_mangled():
    samples = (tone(0.1) * 32767).astype(np.int16)
    assert duration_ms(to_call_pcm(samples, 24000)) == pytest.approx(100, abs=2)


def test_a_hot_sample_is_clipped_rather_than_wrapped():
    """A wrapped sample is a click, and a click sounds like a broken bot."""
    loud = np.array([2.0, -2.0, 0.0], dtype=np.float32)
    values = np.frombuffer(to_call_pcm(loud, CALL_SAMPLE_RATE), dtype="<i2")
    assert values.max() == 32767 and values.min() == -32767


def test_stereo_from_the_engine_is_folded_down_first():
    stereo = np.stack([tone(0.2), tone(0.2)], axis=1)
    assert duration_ms(to_call_pcm(stereo, 24000)) == pytest.approx(200, abs=2)


def test_silence_produces_nothing_to_send():
    assert to_call_pcm(np.zeros(0, dtype=np.float32), 24000) == b""


def test_what_was_heard_splits_from_what_was_not():
    pcm = to_call_pcm(tone(1.0), 24000)
    heard, unheard = split_at_ms(pcm, 400)

    assert duration_ms(heard) == 400
    assert duration_ms(unheard) == 600
    # never mid-frame: half a sample is a click
    assert len(heard) % 4 == 0
