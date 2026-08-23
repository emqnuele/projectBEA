"""The stateful half of attention: routing, cooldowns, activity and the digest.

`rng` and `clock` are injected, so every case here is deterministic.
"""

import datetime
import random

import pytest

from src.core.attention.gate import Attention
from src.core.attention.types import Reaction
from src.core.perception.types import Author, Perception, PerceptionKind

# 14:00 *local* time: outside quiet hours whatever timezone the tests run in
AFTERNOON = datetime.datetime(2026, 6, 15, 14, 0, 0).timestamp()


class FakeClock:
    def __init__(self, start: float = AFTERNOON):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Config:
    """Minimal stand-in for BrainConfig: the gate only reads `.attention`."""

    def __init__(self, **overrides):
        self.attention = {
            "enabled": True,
            "cooldown_seconds": 20,
            "interject_threshold": 0.45,
            "quiet_hours": [3, 9],
            "trigger_words": ["bea", "beatrice"],
            "hot_names": [],
            "self_ids": [],
            "digest_max_lines": 8,
        }
        self.attention.update(overrides)


def gate(clock=None, rng_value: float = 0.0, **cfg) -> Attention:
    rng = random.Random()
    rng.uniform = lambda a, b: rng_value  # no variance unless a test wants it
    return Attention(Config(**cfg), rng=rng, clock=clock or FakeClock())


def chat(content="just chatting", **kwargs) -> Perception:
    base = dict(
        kind=PerceptionKind.CHAT, surface="voice:discord", content=content, salience=0.5,
        author=Author(platform="discord", native_id="4711", display_name="marco"),
    )
    base.update(kwargs)
    return Perception(**base)


# --- routing ----------------------------------------------------------------


def test_an_empty_batch_decides_nothing():
    assert gate().judge([]) == ([], [])


def test_being_named_always_reacts():
    react, noted = gate().judge([chat("[marco] ciao bea")])
    assert len(react) == 1 and noted == []


def test_idle_chatter_is_only_noted():
    react, noted = gate().judge([chat("[marco] boh vediamo")])
    assert react == [] and len(noted) == 1


def test_noise_is_dropped_entirely():
    snapshot = Perception(PerceptionKind.GAME, "game:mc", "(still playing)",
                          salience=0.15, meta={"noise": True})
    react, noted = gate().judge([snapshot])
    assert react == [] and noted == []


def test_a_reacted_batch_carries_its_neighbours_along():
    # answering "ciao bea" without the line that came with it strips the context
    g = gate()
    react, noted = g.judge([chat("[marco] guarda qua"), chat("[marco] ciao bea")])
    assert len(react) == 2 and noted == []


def test_a_reacted_batch_still_drops_the_noise():
    g = gate()
    snapshot = Perception(PerceptionKind.GAME, "game:mc", "(still playing)",
                          salience=0.15, meta={"noise": True})
    react, _ = g.judge([snapshot, chat("[marco] ciao bea")])
    assert len(react) == 1


def test_the_carried_batch_stays_in_time_order():
    g = gate()
    first, second = chat("[marco] uno"), chat("[marco] ciao bea")
    first.ts, second.ts = 100.0, 200.0
    react, _ = g.judge([second, first])
    assert [p.content for p in react] == ["[marco] uno", "[marco] ciao bea"]


def test_a_disabled_gate_lets_everything_through():
    react, noted = gate(enabled=False).judge([chat("[marco] whatever")])
    assert len(react) == 1 and noted == []


# --- idle -------------------------------------------------------------------


def idle() -> Perception:
    return Perception(PerceptionKind.IDLE, "idle", "(nothing is happening)", salience=0.1)


def test_idle_reacts_because_the_timer_is_already_the_gate():
    react, _ = gate().judge([idle()])
    assert len(react) == 1


def test_idle_is_dropped_during_quiet_hours():
    clock = FakeClock()
    g = gate(clock=clock, quiet_hours=[0, 24])
    react, noted = g.judge([idle()])
    assert react == [] and noted == []


# --- cooldown and activity --------------------------------------------------


def test_speaking_starts_a_cooldown():
    clock = FakeClock()
    g = gate(clock=clock)
    assert g.seconds_since_spoke() is None
    g.mark_spoke()
    clock.advance(5)
    assert g.seconds_since_spoke() == pytest.approx(5.0)


def test_she_does_not_interject_right_after_speaking():
    clock = FakeClock()
    g = gate(clock=clock)
    for _ in range(5):
        g.judge([chat("[marco] chiacchiere")])
    g.mark_spoke()
    clock.advance(2)
    react, noted = g.judge([chat("[marco] altre chiacchiere")])
    assert react == [] and len(noted) == 1


def test_being_named_beats_the_cooldown():
    clock = FakeClock()
    g = gate(clock=clock)
    g.mark_spoke()
    clock.advance(1)
    react, _ = g.judge([chat("[marco] bea!!")])
    assert len(react) == 1


def test_activity_is_counted_per_place():
    g = gate()
    g.judge([chat(), chat(), chat(surface="game:mc")])
    assert g.activity("voice:discord") == 2
    assert g.activity("game:mc") == 1
    assert g.activity("nowhere") == 0


def test_activity_expires_outside_the_window():
    clock = FakeClock()
    g = gate(clock=clock)
    g.judge([chat()])
    clock.advance(500)
    assert g.activity("voice:discord") == 0


def test_a_busy_room_eventually_makes_her_speak_up():
    g = gate()
    for _ in range(6):
        g.judge([chat("[marco] messaggio qualunque")])
    react, _ = g.judge([chat("[marco] ma davvero?")])
    assert len(react) == 1


# --- the digest -------------------------------------------------------------


def test_an_empty_digest_is_empty():
    assert gate().digest() == ""


def test_noted_items_reach_the_digest():
    g = gate()
    _, noted = g.judge([chat("[marco] tanto per dire")])
    g.remember(noted)
    digest = g.digest()
    assert "WHILE YOU WERE BUSY" in digest and "tanto per dire" in digest


def test_the_digest_empties_when_read():
    g = gate()
    _, noted = g.judge([chat("[marco] una cosa")])
    g.remember(noted)
    assert g.digest() != ""
    assert g.digest() == ""


def test_a_chatty_surface_gets_one_aggregated_line():
    g = gate()
    for i in range(6):
        g.remember([chat(f"[marco] messaggio {i}")])
    digest = g.digest()
    assert "6 messages" in digest and "messaggio 5" in digest
    assert "messaggio 0" not in digest


def test_the_digest_respects_its_line_cap():
    g = gate(digest_max_lines=2)
    for surface in ["a", "b", "c", "d", "e"]:
        g.remember([chat("qualcosa", surface=surface)])
    digest = g.digest()
    assert digest.count("\n- ") == 3  # 2 lines + the "more" marker
    assert "more you didn't catch" in digest


def test_long_lines_are_truncated():
    g = gate()
    g.remember([chat("x" * 500)])
    assert "…" in g.digest()


def test_pending_counts_what_is_waiting():
    g = gate()
    g.remember([chat("uno"), chat("due")])
    assert g.pending() == 2
    g.digest()
    assert g.pending() == 0


# --- observability ----------------------------------------------------------


def test_every_decision_is_reported():
    seen = []
    g = Attention(Config(), clock=FakeClock(), on_verdict=lambda p, v: seen.append(v))
    g.judge([chat("[marco] ciao bea"), chat("[marco] niente di che")])
    assert [v.reaction for v in seen] == [Reaction.REACT, Reaction.NOTE]
    assert seen[0].reason == "addressed:name"


def test_a_zero_score_reports_why():
    clock = FakeClock()
    seen = []
    g = Attention(Config(), rng=random.Random(0), clock=clock,
                  on_verdict=lambda p, v: seen.append(v))
    g.mark_spoke()
    clock.advance(1)
    g.judge([chat("[marco] niente")])
    assert seen[0].reason == "cooldown"


# --- per-conversation rhythm -------------------------------------------------


def in_channel(channel: str, text: str = "chiacchiere") -> Perception:
    return chat(text, meta={"channel_id": channel})


def test_activity_is_counted_per_channel_not_per_surface():
    """One busy discord channel must not drag her into a quiet one."""
    g = gate()
    for _ in range(6):
        g.judge([in_channel("1")])
    assert g.activity("discord:1") == 6
    assert g.activity("discord:2") == 0


def test_a_busy_channel_does_not_make_her_speak_up_in_a_quiet_one():
    g = gate()
    for _ in range(6):
        g.judge([in_channel("1")])
    react, noted = g.judge([in_channel("2", "prima cosa detta qui")])
    assert react == [] and len(noted) == 1


def test_speaking_in_one_channel_does_not_silence_the_others_forever():
    clock = FakeClock()
    g = gate(clock=clock)
    g.mark_spoke("discord:1")
    clock.advance(1)
    # the global cooldown still applies (she just spoke somewhere), and being
    # addressed still overrides it
    react, _ = g.judge([in_channel("2", "bea?")])
    assert len(react) == 1
