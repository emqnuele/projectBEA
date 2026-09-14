import time

from src.core.mind.single_context import SingleContext
from src.core.mind.spontaneous import SpontaneousPresence
from src.core.mind.token_budget import TokenBudget


class _Bus:
    def __init__(self):
        self.put_perceptions = []

    def put(self, perception):
        self.put_perceptions.append(perception)


class _Rng:
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


def _config():
    class Config:
        rhythm = {}
        attention = {}
    return Config()


def _window(now):
    ctx = SingleContext(TokenBudget(max_tokens=6000, trigger_tokens=5000,
                                    target_tokens=2000))
    for i in range(4):
        ctx.append("user", f"discord line {i}", ts=now - 600,
                   key="discord:123", author="bob")
    ctx.append("user", "stage noise", ts=now - 600, key="stage")
    return ctx


def test_candidates_come_from_the_window_never_sqlite():
    now = 1_700_000_000.0
    presence = SpontaneousPresence(config=_config(), memory=object(),
                                   bus=_Bus(), window=_window(now),
                                   clock=lambda: now)
    assert presence.candidates() == ["discord:123"]


def test_no_window_means_no_candidates():
    presence = SpontaneousPresence(config=_config(), memory=object(),
                                   bus=_Bus(), window=None)
    assert presence.candidates() == []


async def test_run_once_opens_a_quiet_but_live_conversation():
    now = 1_700_000_000.0
    bus = _Bus()
    presence = SpontaneousPresence(config=_config(), memory=object(), bus=bus,
                                   window=_window(now), rng=_Rng(0.0),
                                   clock=lambda: now)
    assert await presence.run_once() == 1
    assert bus.put_perceptions[0].meta["conversation_key"] == "discord:123"


async def test_run_once_stays_quiet_when_she_just_spoke():
    now = 1_700_000_000.0
    ctx = _window(now)
    ctx.append("assistant", "she just answered", ts=now - 10,
               key="discord:123", addressee="bob")
    bus = _Bus()
    presence = SpontaneousPresence(config=_config(), memory=object(), bus=bus,
                                   window=ctx, rng=_Rng(0.0),
                                   clock=lambda: now)
    assert await presence.run_once() == 0
    assert bus.put_perceptions == []


def test_window_helpers_agree_with_spontaneous_needs():
    now = time.time()
    ctx = SingleContext()
    ctx.append("user", "hi", key="tg:1", author="amy", ts=now - 30)
    ctx.append("assistant", "hey", key="tg:1", addressee="amy", ts=now - 20)
    assert ctx.seconds_since_bea("tg:1", now=now) == 20.0
    assert ctx.activity_count("tg:1", window_seconds=120.0, now=now) == 1
    assert ctx.live_keys(now=now) == ["tg:1"]
