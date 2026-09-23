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


async def test_the_rest_of_the_sentence_is_in_the_batch_the_moment_it_is_released():
    """The hold is released by the very transcript it was waiting for: it is on
    the queue before the release, and the batch must not close without it. The
    loop's poll can time out on the same tick, so this does it on the same call."""
    import time

    from src.core.perception.bus import PerceptionBus

    bus = PerceptionBus(window=0.05, max_window=2.0)
    state = {"asked": 0}

    def released_by_the_transcript(items):
        state["asked"] += 1
        if state["asked"] < 3:
            return True
        if state["asked"] == 3:
            # what `transcribed()` does: the perception first, then the release
            rest = voice_line("[ema] (voice): ieri il server è crashato")
            bus._queue.put_nowait((time.monotonic(), rest))
        return False

    bus.holds.append(released_by_the_transcript)
    bus.put(voice_line("[ema] (voice): allora ascolta"))
    batch = await asyncio.wait_for(bus.drain(), timeout=1.0)
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


# --- her line waits for them, and is called off if they carry on -------------


class Socket:
    def __init__(self, on_binary=None):
        self.binary = []
        self.text = []
        self.on_binary = on_binary

    async def send_bytes(self, data):
        self.binary.append(data)
        if self.on_binary:
            self.on_binary()

    async def send_text(self, data):
        self.text.append(data)


def live_call(socket=None):
    ch = VoiceChannel()
    socket = socket or Socket()
    ch.attach(socket)
    ch.on_message({"type": "joined", "channel_id": "c1", "listeners": 1})
    return ch, socket


def real_expression():
    from tests.test_voice_streaming import OneShotTTS, expression

    return expression(OneShotTTS())


async def test_her_first_word_waits_while_somebody_is_talking():
    e = real_expression()
    ch, socket = live_call()
    e.set_call(ch)
    ch.on_message(hearing("start"))

    speaking = asyncio.create_task(e.speak("neutral", "Allora, ti dico una cosa.", route="call"))
    await asyncio.sleep(0.2)
    assert socket.binary == [], "she talked over somebody who had started again"

    ch.on_message(hearing("end"))
    await asyncio.wait_for(speaking, timeout=2.0)
    assert socket.binary, "she never said it once they stopped"


async def test_once_she_is_talking_the_rest_of_her_line_is_not_held():
    e = real_expression()
    ch = VoiceChannel()
    # somebody starts the moment her first sound leaves: that is a barge-in,
    # and the barge-in rules deal with it, not a wait in the middle of a word
    socket = Socket(on_binary=lambda: ch.on_message(hearing("start")))
    ch.attach(socket)
    ch.on_message({"type": "joined", "channel_id": "c1", "listeners": 1})
    e.set_call(ch)

    await asyncio.wait_for(
        e.speak("neutral", "Prima frase, abbastanza lunga. Seconda frase, altrettanto lunga.",
                route="call"),
        timeout=2.0)
    assert len(socket.binary) == 3, "the second sentence waited behind somebody talking"


def mind_in_a_call(llm):
    from src.core.attention.gate import Attention
    from src.core.consciousness import Consciousness
    from src.core.memory.store import MemoryStore
    from src.core.perception.bus import PerceptionBus
    from src.core.skills.base import SkillRegistry
    from tests.fakes import FakeExpression, FakeHistory, RecordingEvents

    class Config:
        consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.02,
                         "burst_steps": 3, "correlation_timeout": 5.0,
                         "turn_log": False, "window_persist_after_turn": False}
        attention = {"enabled": True, "trigger_words": ["bea"]}
        skills: dict = {}
        language = ""

    ch, _ = live_call()
    expression = FakeExpression()
    expression.set_call(ch)
    bus = PerceptionBus(window=0.02, max_window=3.0)
    bus.holds.append(lambda items: ch.busy() and any(p.surface == "voice:discord" for p in items))
    config = Config()
    c = Consciousness(
        config=config, llm=llm, bus=bus, expression=expression, surfaces=SkillRegistry(),
        history_manager=FakeHistory(), event_manager=RecordingEvents(),
        soul_getter=lambda: "soul", operating_getter=lambda: "rules",
        memory=MemoryStore(":memory:"), profiler=None, attention=Attention(config),
    )
    ch.on_hearing = c._on_hearing
    return c, ch


class HeldLLM:
    """A model whose first answer takes as long as the test says it does."""

    def __new__(cls, script):
        from tests.fakes import FakeLLMClient

        class Held(FakeLLMClient):
            async def complete(self, messages, tools=None, response_format=None):
                first = not self.calls
                message = await super().complete(messages, tools, response_format)
                if first:
                    await self.release.wait()
                return message

        llm = Held(script)
        llm.release = asyncio.Event()
        return llm


async def running(c):
    c.alive = True
    return asyncio.create_task(c.run())


async def stopped(c, loop):
    c.alive = False
    loop.cancel()
    try:
        await loop
    except asyncio.CancelledError:
        pass


def said_in_the_call(c):
    return [message for _, message, route in c.expression.spoken if route == "call"]


async def until(condition, timeout=2.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("timed out waiting")
        await asyncio.sleep(0.01)


async def test_she_answers_the_whole_sentence_not_the_first_half():
    from tests.fakes import speaks

    llm = HeldLLM([speaks("rispondo a metà"), speaks("rispondo a tutto")])
    c, ch = mind_in_a_call(llm)
    loop = await running(c)

    c.bus.put(voice_line("[ema] (voice): allora ascolta"))
    await until(lambda: llm.call_count == 1)
    # she is thinking about the first half; they carry on
    ch.on_message(hearing("start"))
    ch.on_message(hearing("sent"))
    await asyncio.sleep(0.15)
    assert llm.call_count == 1, "she started again before the rest of it was there"

    c.bus.put(voice_line("[ema] (voice): ieri il server è crashato"))
    ch.transcribed("u")
    ch.on_message(hearing("end"))
    await until(lambda: said_in_the_call(c))
    await stopped(c, loop)

    assert said_in_the_call(c) == ["rispondo a tutto"]
    frame = llm.calls[-1][-1]["content"]
    assert "allora ascolta" in frame and "ieri il server è crashato" in frame


async def test_a_line_written_while_they_talk_waits_and_is_dropped_if_they_carry_on():
    from tests.fakes import speaks

    llm = HeldLLM([speaks("rispondo a metà"), speaks("rispondo a tutto")])
    c, ch = mind_in_a_call(llm)
    loop = await running(c)

    c.bus.put(voice_line("[ema] (voice): allora ascolta"))
    await until(lambda: llm.call_count == 1)
    ch.on_message(hearing("start"))
    llm.release.set()
    await asyncio.sleep(0.15)
    assert said_in_the_call(c) == [], "she said it over somebody who had started again"
    assert not any("metà" in m["content"] for m in c.history.messages), "a line nobody heard went into her history"

    ch.on_message(hearing("sent"))
    c.bus.put(voice_line("[ema] (voice): ieri il server è crashato"))
    ch.transcribed("u")
    ch.on_message(hearing("end"))
    await until(lambda: said_in_the_call(c))
    await stopped(c, loop)

    assert said_in_the_call(c) == ["rispondo a tutto"]
    assert not any("metà" in m["content"] for m in c.history.messages)


async def test_a_cough_only_delays_her_and_costs_nothing_else():
    from tests.fakes import speaks

    llm = HeldLLM([speaks("ciao ema")])
    c, ch = mind_in_a_call(llm)
    loop = await running(c)

    c.bus.put(voice_line("[ema] (voice): bea ci sei?"))
    await until(lambda: llm.call_count == 1)
    ch.on_message(hearing("start"))
    llm.release.set()
    await asyncio.sleep(0.1)
    assert said_in_the_call(c) == []

    # it was never words: nothing on its way, and she says what she had
    ch.on_message(hearing("end"))
    await until(lambda: said_in_the_call(c))
    await stopped(c, loop)
    assert said_in_the_call(c) == ["ciao ema"]
    assert llm.call_count == 1


async def test_nobody_talking_means_nobody_waits():
    c, ch = mind_in_a_call(HeldLLM([]))
    await asyncio.wait_for(c._speak("neutral", "subito"), timeout=0.1)
    assert said_in_the_call(c) == ["subito"]


async def test_what_is_already_under_way_is_never_called_off():
    c, _ = mind_in_a_call(HeldLLM([]))
    c._turn_task = asyncio.create_task(asyncio.sleep(10))
    c._batch = [voice_line("[ema] (voice): allora")]
    try:
        assert c._can_start_over()

        c._acted = [{"tool": "play_minecraft"}]
        assert not c._can_start_over(), "a tool that already ran would run twice"
        c._acted = []

        c._said = {"mood": "neutral", "message": "ciao"}
        assert not c._can_start_over(), "something she already said would be taken back"
        c._said = None

        c.expression.is_speaking = True
        assert not c._can_start_over(), "talking over her is the barge-in's business"
        c.expression.is_speaking = False

        c._dispatching = "play_minecraft"
        assert not c._can_start_over(), "a tool half way through would be cut in two"
        c._dispatching = None

        c._batch = [chat_line("[mario]: ciao")]
        assert not c._can_start_over(), "a telegram reply is not the call's to restart"
    finally:
        c._turn_task.cancel()


async def test_the_mind_listens_to_the_call_it_is_in():
    from types import SimpleNamespace

    c, _ = mind_in_a_call(HeldLLM([]))
    ch = VoiceChannel()

    class Surfaces:
        def get(self, name):
            return SimpleNamespace(channel=ch) if name == "voice:discord" else None

    c.surfaces = Surfaces()
    c._listen_to_the_call()
    assert ch.on_hearing == c._on_hearing
