"""Each platform has its own ceiling, and its own idea of "too fast".

The humanizer used to cut at 2000 characters — Discord's limit — everywhere.
On Twitch, where the ceiling is 500 and the chat throttles at 20 messages per
30 seconds, that meant truncated lines and, worse, a half-hour timeout for the
whole account.
"""

import random

import pytest

from src.core.expression.humanizer import TextHumanizer
from src.core.skills.platform import PlatformSkill
from src.core.skills.telegram.surface import TelegramSkill
from src.core.skills.twitch.surface import TwitchSkill
from src.utils.rate_limit import SlidingWindow


async def _instant(seconds):
    return None


def _humanizer(limit: int) -> TextHumanizer:
    rng = random.Random()
    rng.uniform = lambda a, b: 1.0
    return TextHumanizer(sleep=_instant, rng=rng, hard_limit=limit)


# --- the humanizer's ceiling is a parameter ----------------------------------


def test_the_ceiling_defaults_to_the_safe_one():
    assert TextHumanizer().hard_limit == 2000


def test_a_lower_ceiling_splits_earlier():
    h = _humanizer(50)
    chunks = h.split("a" * 120)
    assert all(len(c.value) <= 50 for c in chunks)
    assert len(chunks) == 3


def test_nothing_is_lost_when_a_line_is_cut():
    h = _humanizer(50)
    assert "".join(c.value for c in h.split("b" * 120)) == "b" * 120


# --- every platform declares its own ----------------------------------------


def test_the_base_platform_assumes_the_discord_ceiling():
    assert PlatformSkill.message_limit == 2000


def test_twitch_declares_its_own():
    assert TwitchSkill.message_limit == 500


def test_telegram_may_write_longer_messages():
    assert TelegramSkill.message_limit == 4096


def test_a_skill_hands_its_ceiling_to_the_humanizer():
    class Tiny(PlatformSkill):
        name = "chat:tiny"
        skill_name = "tiny"
        platform = "tiny"
        message_limit = 42

    skill = Tiny(_Config(), bus=None, expression=None)
    skill.initialize()
    assert skill.humanizer.hard_limit == 42


class _Config:
    def __init__(self):
        self.skills = {}
        self.attention = {}


# --- the sliding window ------------------------------------------------------


def test_a_fresh_window_lets_everything_through():
    w = SlidingWindow(limit=3, per_seconds=30, clock=lambda: 0.0)
    assert [w.allow() for _ in range(3)] == [True, True, True]


def test_one_over_the_limit_is_refused():
    w = SlidingWindow(limit=3, per_seconds=30, clock=lambda: 0.0)
    for _ in range(3):
        w.allow()
    assert w.allow() is False


def test_the_window_slides():
    now = [0.0]
    w = SlidingWindow(limit=2, per_seconds=30, clock=lambda: now[0])
    w.allow()
    w.allow()
    assert w.allow() is False
    now[0] = 31.0
    assert w.allow() is True


def test_it_reports_how_long_to_wait():
    now = [0.0]
    w = SlidingWindow(limit=1, per_seconds=30, clock=lambda: now[0])
    w.allow()
    now[0] = 10.0
    assert w.retry_after() == pytest.approx(20.0)


def test_nothing_to_wait_for_when_there_is_room():
    w = SlidingWindow(limit=2, per_seconds=30, clock=lambda: 0.0)
    w.allow()
    assert w.retry_after() == 0.0


# --- twitch actually uses it -------------------------------------------------


class FakeIRC:
    def __init__(self):
        self.said = []
        self.connected = True

    async def say(self, text: str) -> bool:
        self.said.append(text)
        return True


def _twitch(**cfg) -> TwitchSkill:
    class Config:
        def __init__(self):
            self.skills = {"twitch": {"enabled": True, "channel": "ema", **cfg}}
            self.attention = {}

    skill = TwitchSkill(Config(), bus=None, expression=None)
    skill.initialize()
    skill.irc = FakeIRC()
    skill.active = True
    return skill


async def test_twitch_stops_writing_at_the_rate_limit():
    skill = _twitch()
    skill.limiter = SlidingWindow(limit=2, per_seconds=30, clock=lambda: 0.0)
    assert await skill.send_text("ema", "uno") is True
    assert await skill.send_text("ema", "due") is True
    assert await skill.send_text("ema", "tre") is False
    assert skill.irc.said == ["uno", "due"]


async def test_a_dropped_line_is_not_reported_as_sent():
    skill = _twitch()
    skill.limiter = SlidingWindow(limit=1, per_seconds=30, clock=lambda: 0.0)
    sent = await skill.deliver("ema", "prima riga\nseconda riga")
    assert sent == ["prima riga"]


async def test_a_twitch_line_never_exceeds_five_hundred_characters():
    skill = _twitch()
    skill.humanizer = _humanizer(skill.message_limit)
    await skill.deliver("ema", "x" * 1200)
    assert skill.irc.said
    assert all(len(line) <= 500 for line in skill.irc.said)
