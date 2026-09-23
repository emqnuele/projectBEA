"""Waiting for the rest of a sentence instead of answering half of it.

A turn detector ends a turn on a pause, and people pause inside sentences. The
first half used to be answered while the second was still being said, often
over the person saying it. The bot now tells the brain as somebody starts
talking, and she holds what she has not yet said until they stop.
"""

import asyncio

import pytest

from src.core.skills.voice import channel as channel_module
from src.core.skills.voice.channel import VoiceChannel


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(channel_module.time, "monotonic", c)
    return c


def hearing(state, user="u"):
    return {"type": "hearing", "state": state, "user_id": user}


# --- what the call knows ------------------------------------------------------


def test_somebody_talking_holds_the_floor_until_they_stop(clock):
    ch = VoiceChannel()
    assert not ch.busy()
    ch.on_message(hearing("start"))
    assert ch.busy()
    ch.on_message(hearing("end"))
    assert not ch.busy(), "a sound that was never a turn kept the floor"


def test_a_turn_on_its_way_holds_the_floor_until_it_is_transcribed(clock):
    ch = VoiceChannel()
    ch.on_message(hearing("start"))
    ch.on_message(hearing("sent"))
    ch.on_message(hearing("end"))
    assert ch.busy(), "the rest of the sentence is still being transcribed"
    ch.transcribed("u")
    assert not ch.busy()


def test_two_turns_on_their_way_need_two_transcripts(clock):
    ch = VoiceChannel()
    ch.on_message(hearing("sent"))
    ch.on_message(hearing("sent"))
    ch.transcribed("u")
    assert ch.busy()
    ch.transcribed("u")
    assert not ch.busy()


def test_a_lost_message_cannot_hold_the_floor_for_ever(clock):
    ch = VoiceChannel()
    ch.on_message(hearing("start"))
    clock.now += channel_module.TALKING_MAX_S + 1
    assert not ch.busy(), "a bot that never said they stopped silenced her for good"

    ch.on_message(hearing("sent", user="v"))
    clock.now += channel_module.TRANSCRIPT_MAX_S + 1
    assert not ch.busy(), "a transcript that never came silenced her for good"


def test_leaving_the_call_forgets_who_was_talking(clock):
    ch = VoiceChannel()
    ch.on_message(hearing("start"))
    ch.on_message(hearing("sent", user="v"))
    ch.on_message({"type": "left"})
    assert not ch.busy()


def test_the_mind_is_told_as_it_happens(clock):
    ch = VoiceChannel()
    seen = []
    ch.on_hearing = lambda user, state: seen.append((user, state))
    ch.on_message(hearing("start"))
    ch.on_message(hearing("sent"))
    assert seen == [("u", "start"), ("u", "sent")]


def test_a_listener_that_raises_does_not_break_the_socket(clock):
    ch = VoiceChannel()

    def boom(user, state):
        raise RuntimeError("listener bug")

    ch.on_hearing = boom
    ch.on_message(hearing("start"))
    assert ch.busy()


async def test_waiting_for_quiet_returns_as_soon_as_they_stop():
    ch = VoiceChannel()
    ch.on_message(hearing("start"))

    async def later():
        await asyncio.sleep(0.05)
        ch.on_message(hearing("end"))

    task = asyncio.create_task(later())
    assert await ch.until_quiet(timeout=2.0) is True
    await task


async def test_waiting_for_quiet_gives_up_at_its_limit():
    ch = VoiceChannel()
    ch.on_message(hearing("start"))
    assert await ch.until_quiet(timeout=0.05) is False


# --- a transcript that arrives, or fails, says so -----------------------------


class VoiceSurfaceStub:
    """Records what a route did with the call, in the order it did it."""

    def __init__(self):
        self.log = []
        self.latency = None

    def perceive(self, transcript, user, **kw):
        self.log.append(("perceive", transcript))

    def transcribed(self, user_id):
        self.log.append(("transcribed", user_id))


class BrainStub:
    def __init__(self, stt):
        self.stt = stt
        self.consciousness = object()
        self.voice = VoiceSurfaceStub()

    def _surface(self, name):
        return self.voice if name == "voice:discord" else None


async def test_a_turn_is_perceived_before_the_floor_is_released():
    from types import SimpleNamespace

    from src.core.brain import AIVtuberBrain

    brain = BrainStub(SimpleNamespace(transcribe=lambda path: "e poi il server"))
    await AIVtuberBrain.process_discord_interaction(brain, "clip.wav", "ema", user_id="u")
    # the other way round, the batch could close between the two without it
    assert brain.voice.log == [("perceive", "e poi il server"), ("transcribed", "u")]


async def test_a_transcription_that_fails_still_releases_the_floor():
    from types import SimpleNamespace

    from src.core.brain import AIVtuberBrain

    def broken(path):
        raise OSError("the transcriber is down")

    brain = BrainStub(SimpleNamespace(transcribe=broken))
    with pytest.raises(OSError):
        await AIVtuberBrain.process_discord_interaction(brain, "clip.wav", "ema", user_id="u")
    assert brain.voice.log == [("transcribed", "u")]


@pytest.fixture
def overheard(tmp_path, monkeypatch):
    import io
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from src.web import deps
    from src.web.app import app

    monkeypatch.chdir(tmp_path)
    voice = VoiceSurfaceStub()
    brain = SimpleNamespace(stt=None, skill_registry={"voice:discord": voice})
    previous = deps.brain_instance
    deps.brain_instance = brain

    def post(stt):
        brain.stt = stt
        return TestClient(app, raise_server_exceptions=False).post(
            "/voice/transcript",
            files={"file": ("clip.wav", io.BytesIO(b"RIFF....WAVE"), "audio/wav")},
            data={"username": "ema", "user_id": "u"})

    try:
        yield post, voice
    finally:
        deps.brain_instance = previous


def test_overheard_speech_releases_the_floor_once_perceived(overheard):
    from types import SimpleNamespace

    post, voice = overheard
    post(SimpleNamespace(transcribe=lambda path: "aspetta un attimo"))
    assert voice.log == [("perceive", "aspetta un attimo"), ("transcribed", "u")]


def test_overheard_speech_that_fails_still_releases_the_floor(overheard):
    from types import SimpleNamespace

    post, voice = overheard

    def broken(path):
        raise OSError("boom")

    assert post(SimpleNamespace(transcribe=broken)).status_code == 200
    assert voice.log == [("transcribed", "u")]


# --- the batch waits for the rest of the sentence -----------------------------


def voice_line(text, surface="voice:discord"):
    from src.core.perception.types import Perception, PerceptionKind

    return Perception(kind=PerceptionKind.VOICE, surface=surface, content=text)


def chat_line(text):
    from src.core.perception.types import Perception, PerceptionKind

    return Perception(kind=PerceptionKind.CHAT, surface="chat:telegram", content=text)


async def test_the_batch_waits_while_the_rest_of_the_sentence_is_coming():
    from src.core.perception.bus import PerceptionBus

    bus = PerceptionBus(window=0.05, max_window=2.0)
    talking = {"on": True}
    bus.holds.append(lambda items: talking["on"] and any(p.surface == "voice:discord" for p in items))

    bus.put(voice_line("[ema] (voice): allora ascolta"))
    drained = asyncio.create_task(bus.drain())
    await asyncio.sleep(0.3)
    assert not drained.done(), "the batch closed on half a sentence"

    bus.put(voice_line("[ema] (voice): ieri il server è crashato"))
    talking["on"] = False
    batch = await asyncio.wait_for(drained, timeout=1.0)
    assert [p.content for p in batch] == ["[ema] (voice): allora ascolta",
                                          "[ema] (voice): ieri il server è crashato"]


async def test_the_batch_closes_as_soon_as_the_sound_turns_out_to_be_nothing():
    from src.core.perception.bus import PerceptionBus

    bus = PerceptionBus(window=0.05, max_window=2.0)
    talking = {"on": True}
    bus.holds.append(lambda items: talking["on"])

    bus.put(voice_line("[ema] (voice): ok"))
    drained = asyncio.create_task(bus.drain())
    await asyncio.sleep(0.2)
    talking["on"] = False
    batch = await asyncio.wait_for(drained, timeout=0.3)
    assert len(batch) == 1


async def test_nobody_can_hold_a_batch_past_its_ceiling():
    from src.core.perception.bus import PerceptionBus

    bus = PerceptionBus(window=0.05, max_window=0.3)
    bus.holds.append(lambda items: True)
    bus.put(voice_line("[ema] (voice): e poi"))
    batch = await asyncio.wait_for(bus.drain(), timeout=1.0)
    assert len(batch) == 1


async def test_a_hold_that_raises_does_not_hold_anything():
    from src.core.perception.bus import PerceptionBus

    def broken(items):
        raise RuntimeError("bug")

    bus = PerceptionBus(window=0.05, max_window=2.0)
    bus.holds.append(broken)
    bus.put(voice_line("[ema] (voice): ciao"))
    batch = await asyncio.wait_for(bus.drain(), timeout=0.5)
    assert len(batch) == 1


def test_the_call_only_holds_what_it_is_part_of():
    from src.core.skills.voice.surface import VoiceSurface

    surface = VoiceSurface.__new__(VoiceSurface)
    surface.name = "voice:discord"
    surface.channel = VoiceChannel()
    surface.channel.on_message(hearing("start"))

    assert surface.holds([voice_line("[ema] (voice): allora")])
    # somebody talking in the call is no reason to keep a telegram message waiting
    assert not surface.holds([chat_line("[mario]: ciao")])
