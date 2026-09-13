"""The reflex: when her mouth opens, and every reason it stays shut.

The decision is a pure function over a handful of numbers, so it gets tested the
way `attention/rules.py` is — on a table of cases, with no clock and no socket.
The one property worth stating out loud: nothing here can produce words. If a
decision ever grows a text field, the design has slipped into a second mind.
"""

import random

from src.core.attention.gate import Attention
from src.core.floor.controller import FloorController
from src.core.floor.rules import FloorDecision, FloorState, decide
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Perception, PerceptionKind

LIMITS = {"silence_after": 6.0, "min_gap": 25.0, "max_takes": 1}


def state(**over) -> FloorState:
    base = {"in_call": True, "listeners": 2, "she_is_speaking": False,
            "silence_seconds": 10.0, "seconds_since_she_took": None, "takes_in_window": 0}
    base.update(over)
    return FloorState(**base)


# --- the decision ------------------------------------------------------------


def test_a_long_enough_silence_opens_the_door():
    assert decide(state(), **LIMITS) is FloorDecision.TAKE_SILENCE


def test_outside_a_call_there_is_no_floor_to_take():
    assert decide(state(in_call=False), **LIMITS) is FloorDecision.HOLD


def test_an_empty_room_is_not_a_silence_worth_filling():
    assert decide(state(listeners=0), **LIMITS) is FloorDecision.HOLD


def test_she_never_talks_over_her_own_voice():
    assert decide(state(she_is_speaking=True), **LIMITS) is FloorDecision.HOLD


def test_a_pause_is_not_a_silence():
    assert decide(state(silence_seconds=3.0), **LIMITS) is FloorDecision.HOLD


def test_filling_two_silences_in_a_row_is_a_tic():
    assert decide(state(seconds_since_she_took=8.0), **LIMITS) is FloorDecision.HOLD


def test_the_hard_limit_is_what_stops_her_becoming_the_loudest_one_there():
    assert decide(state(takes_in_window=1), **LIMITS) is FloorDecision.HOLD


def test_the_limit_can_be_lifted_entirely():
    assert decide(state(takes_in_window=99), **{**LIMITS, "max_takes": 0}) \
        is FloorDecision.TAKE_SILENCE


def test_a_decision_carries_no_words():
    """The type is the guardrail: the mind stays the only thing that can talk."""
    assert not hasattr(FloorDecision.TAKE_SILENCE, "text")
    assert set(FloorDecision) == {FloorDecision.HOLD, FloorDecision.TAKE_SILENCE}


# --- the controller ----------------------------------------------------------


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class Channel:
    def __init__(self, live=True, listeners=2):
        self.live = live
        self.listeners = listeners


class Speaker:
    def __init__(self, speaking=False):
        self.is_speaking = speaking


class Config:
    def __init__(self, **discord):
        self.skills = {"discord": {"enabled": True, "silence_seconds": 6.0,
                                   "silence_jitter_seconds": 0.0,
                                   "silence_min_gap_seconds": 25.0,
                                   "unprompted_per_minute": 1, **discord}}
        self.attention = {}


def controller(clock, bus=None, channel=None, speaker=None, **discord) -> FloorController:
    return FloorController(
        config=Config(**discord), bus=bus or PerceptionBus(window=0.0),
        channel=channel or Channel(), expression=speaker or Speaker(),
        clock=clock, rng=random.Random(7),
    )


def test_before_anyone_has_spoken_there_is_no_silence_yet():
    """Walking into a call and talking into the void is not presence."""
    clock = Clock()
    floor = controller(clock)
    clock.advance(60)

    assert floor.tick() is FloorDecision.HOLD


def test_a_room_that_goes_quiet_puts_a_perception_on_the_bus():
    clock, bus = Clock(), PerceptionBus(window=0.0)
    floor = controller(clock, bus=bus)

    floor.heard()
    clock.advance(3)
    assert floor.tick() is FloorDecision.HOLD
    clock.advance(5)
    assert floor.tick() is FloorDecision.TAKE_SILENCE

    (p,) = bus.drain_nowait()
    assert p.kind is PerceptionKind.VOICE
    assert p.meta["addressed"] == "silence"
    assert "8 seconds" in p.content


def test_the_perception_reaches_the_mind_past_the_cooldown():
    """A silence she may not answer is a door that was never opened."""
    clock, bus = Clock(), PerceptionBus(window=0.0)
    floor = controller(clock, bus=bus)
    floor.heard()
    clock.advance(10)
    floor.tick()

    gate = Attention(Config())
    gate.mark_spoke()  # she spoke a moment ago: the general cooldown is on
    react, _ = gate.judge(bus.drain_nowait())

    assert len(react) == 1


def test_someone_speaking_resets_the_room():
    clock = Clock()
    floor = controller(clock)
    floor.heard()
    clock.advance(5)
    floor.heard()
    clock.advance(3)

    assert floor.tick() is FloorDecision.HOLD


def test_she_does_not_fill_the_next_silence_straight_after_the_last():
    clock = Clock()
    floor = controller(clock)
    floor.heard()
    clock.advance(10)
    assert floor.tick() is FloorDecision.TAKE_SILENCE

    clock.advance(10)
    assert floor.tick() is FloorDecision.HOLD


def test_no_more_than_the_configured_openings_a_minute():
    clock = Clock()
    floor = controller(clock, silence_min_gap_seconds=0.0, unprompted_per_minute=2)

    # five silences inside one rolling minute; only two may be taken
    taken = 0
    for _ in range(5):
        floor.heard()
        clock.advance(10)
        if floor.tick() is FloorDecision.TAKE_SILENCE:
            taken += 1
    assert taken == 2


def test_the_limit_lets_go_once_the_window_has_passed():
    clock = Clock()
    floor = controller(clock, silence_min_gap_seconds=0.0)

    floor.heard()
    clock.advance(10)
    assert floor.tick() is FloorDecision.TAKE_SILENCE

    clock.advance(90)
    floor.heard()
    clock.advance(10)
    assert floor.tick() is FloorDecision.TAKE_SILENCE


def test_switching_it_off_leaves_her_exactly_as_she_was():
    clock = Clock()
    floor = controller(clock, fill_silences=False)
    floor.heard()
    clock.advance(60)

    assert floor.tick() is FloorDecision.HOLD


def test_the_wait_is_never_exactly_the_same_twice():
    """A fixed threshold sounds like a timer, because it is one."""
    floor = controller(Clock(), silence_jitter_seconds=2.0)
    drawn = {round(floor._draw_threshold(), 4) for _ in range(20)}

    assert len(drawn) > 1
    assert all(4.0 <= t <= 8.0 for t in drawn)


# --- the cooldown a call deserves --------------------------------------------


def voice(content: str = "[ema] (voice): allora") -> Perception:
    return Perception(PerceptionKind.VOICE, "voice:discord", content, salience=0.85)


def chat(content: str = "[ema]: allora") -> Perception:
    return Perception(PerceptionKind.CHAT, "chat:ui", content, salience=0.85)


def test_a_call_gets_a_shorter_cooldown_than_a_chat():
    gate = Attention(Config())
    assert gate.cooldown_for(voice()) < gate.cooldown_for(chat())


def test_the_call_cooldown_is_configurable_on_its_own():
    class Cfg(Config):
        def __init__(self):
            super().__init__()
            self.attention = {"voice_cooldown_seconds": 3.0, "cooldown_seconds": 40}

    gate = Attention(Cfg())
    assert gate.cooldown_for(voice()) == 3.0
    assert gate.cooldown_for(chat()) == 40.0
