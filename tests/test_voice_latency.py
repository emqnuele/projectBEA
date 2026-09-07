"""The stopwatch of a voice turn, and what the call puts on a perception.

The latency number is the only thing that settles whether the voice work paid
off, so it gets tested like a feature, not like a log line.
"""

import pytest

from src.core.perception.bus import PerceptionBus
from src.core.skills.voice.latency import MIND, STT, TRANSPORT, TTS, VoiceLatency
from src.core.skills.voice.surface import VoiceSurface


class Clock:
    """A hand-cranked monotonic clock: no sleeps in a timing test."""

    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, ms: float) -> None:
        self.t += ms / 1000.0


class Events:
    def __init__(self):
        self.published = []

    def publish(self, category, source, message, metadata=None):
        self.published.append((source, message, metadata or {}))


# --- the stopwatch -----------------------------------------------------------


def test_the_breakdown_says_which_stage_to_blame():
    clock, events = Clock(), Events()
    latency = VoiceLatency(events=events, clock=clock)

    latency.open("ema")
    clock.advance(400)
    latency.mark(STT)
    clock.advance(900)
    latency.mark(MIND)
    clock.advance(700)
    latency.mark(TTS)

    turn = latency.close()
    assert turn.breakdown() == {STT: 400, MIND: 900, TTS: 700}
    assert turn.ttft_ms == pytest.approx(2000)


def test_the_number_reaches_the_dashboard():
    clock, events = Clock(), Events()
    latency = VoiceLatency(events=events, clock=clock)

    latency.open("ema")
    clock.advance(250)
    latency.mark(STT)
    latency.close()

    source, message, metadata = events.published[0]
    assert source == "voice.latency"
    assert "ttft 250ms" in message
    assert metadata["ttft_ms"] == 250
    assert metadata["speaker"] == "ema"


def test_a_turn_with_two_sentences_pays_the_tts_twice():
    """Hiding the second synthesis would flatter the number."""
    clock = Clock()
    latency = VoiceLatency(clock=clock)

    latency.open("ema")
    clock.advance(100)
    latency.mark(TTS)
    clock.advance(300)
    latency.mark(TTS)

    assert latency.close().breakdown() == {TTS: 400}


def test_staying_silent_reports_no_time_to_first_sound():
    latency = VoiceLatency(events=Events(), clock=Clock())
    latency.open("ema")
    latency.mark(STT)
    latency.abandon()

    assert latency.turn is None
    assert latency.close() is None


def test_marking_without_an_open_turn_is_harmless():
    """She can speak with nobody in a call; the metric must not care."""
    latency = VoiceLatency(clock=Clock())
    latency.mark(TRANSPORT)
    assert latency.close() is None


def test_a_turn_nobody_closed_is_replaced_by_the_next_one():
    clock = Clock()
    latency = VoiceLatency(clock=clock)

    latency.open("ema")
    clock.advance(500)
    latency.open("luca")
    clock.advance(100)
    latency.mark(STT)

    turn = latency.close()
    assert turn.speaker == "luca"
    assert turn.breakdown() == {STT: 100}


# --- what the call puts on a voice perception --------------------------------


def _surface():
    class Cfg:
        skills = {"discord": {"enabled": True}}
        attention = {}

    s = VoiceSurface(Cfg(), bus=PerceptionBus(window=0.0), expression=None)
    s.initialize()
    s.active = True
    return s


def test_a_call_of_two_is_all_addressed_to_her():
    from src.core.attention.rules import is_addressed

    p = _surface().perceive("come va", "Ema", user_id="1", listeners=1)
    assert p.meta["alone_with_speaker"] is True
    assert is_addressed(p) == "addressed:voice-1on1"


def test_in_a_group_call_nothing_is_addressed_to_her_by_default():
    from src.core.attention.rules import is_addressed

    p = _surface().perceive("come va", "Ema", user_id="1", listeners=3)
    assert p.meta["alone_with_speaker"] is False
    assert is_addressed(p) is None


def test_a_bot_that_does_not_say_how_many_leaves_the_rule_alone():
    p = _surface().perceive("come va", "Ema", user_id="1")
    assert "alone_with_speaker" not in p.meta


def test_a_stranger_in_the_call_is_heard_more_faintly():
    """Same reasoning as the text path: heard, just not loudly."""
    known = _surface().perceive("ciao", "Ema", user_id="1", whitelisted=True)
    stranger = _surface().perceive("ciao", "Tizio", user_id="9", whitelisted=False)

    assert known.salience == 0.85
    assert 0 < stranger.salience < known.salience
    assert stranger.meta["whitelisted"] is False
