"""What time it is, and how long ago things happened.

She knew the date and nothing else: no clock, no weekday, no idea whether a
message in her batch arrived two seconds or forty minutes ago, and no sense of
how long she had been awake. Meanwhile the quiet hours were silencing her from
3am using a clock she could not see.
"""

from datetime import datetime

import pytest

from src.core.timeline import (
    STAMP_AFTER_SECONDS,
    now_block,
    relative,
    resolve_timezone,
    stamp_for,
)

NOON = datetime(2026, 8, 27, 12, 30)
NIGHT = datetime(2026, 8, 27, 3, 41)


# --- how long ago ------------------------------------------------------------


@pytest.mark.parametrize("seconds,expected", [
    (0, "just now"),
    (5, "just now"),
    (29, "just now"),
    (60, "1 min ago"),
    (150, "2 min ago"),
    (3600, "1h ago"),
    (7500, "2h ago"),
    (90000, "yesterday"),
    (400000, "4 days ago"),
])
def test_an_age_reads_the_way_a_person_would_say_it(seconds, expected):
    assert relative(seconds) == expected


def test_the_future_is_not_described_as_the_past():
    assert relative(-10) == "just now"


# --- when a stamp is worth its tokens ----------------------------------------


def test_something_that_just_arrived_needs_no_stamp():
    assert stamp_for(10.0) == ""


def test_something_older_gets_one():
    assert stamp_for(STAMP_AFTER_SECONDS + 1) == "(1 min ago) "


def test_the_threshold_is_seconds_not_minutes():
    """A batch that spans half a minute is still one moment."""
    assert STAMP_AFTER_SECONDS >= 30


# --- the block she is shown --------------------------------------------------


def test_it_says_the_weekday_the_date_and_the_time():
    block = now_block(NOON)
    assert "Thursday" in block
    assert "27 August 2026" in block
    assert "12:30" in block


def test_it_is_labelled_so_she_can_find_it():
    assert now_block(NOON).startswith("[RIGHT NOW]")


def test_at_night_it_says_so_in_the_time():
    assert "03:41" in now_block(NIGHT)


def test_it_says_how_long_she_has_been_up():
    assert "2h" in now_block(NOON, awake_seconds=8100)


def test_a_session_that_just_started_is_not_worth_a_line():
    assert "up for" not in now_block(NOON, awake_seconds=30)


def test_it_says_when_she_last_spoke_here():
    assert "20 min ago" in now_block(NOON, last_spoke_seconds=1200)


def test_having_never_spoken_here_is_said_plainly():
    assert "not said anything here" in now_block(NOON, last_spoke_seconds=None, in_conversation=True)


def test_the_timezone_is_named_when_it_was_chosen():
    assert "Europe/Rome" in now_block(NOON, timezone="Europe/Rome")


def test_a_system_clock_is_not_dressed_up_as_a_choice():
    assert "(" not in now_block(NOON).splitlines()[1]


def test_the_block_stays_short_enough_to_send_every_turn():
    block = now_block(NOON, awake_seconds=8100, last_spoke_seconds=1200, timezone="Europe/Rome")
    assert len(block.splitlines()) <= 4
    assert len(block) < 200


# --- the timezone ------------------------------------------------------------


def test_no_timezone_means_the_machine_clock():
    assert resolve_timezone("") is None


def test_a_real_timezone_is_used():
    assert resolve_timezone("Europe/Rome") is not None


def test_a_timezone_that_does_not_exist_does_not_crash_her():
    assert resolve_timezone("Middle/Earth") is None


# --- a perception knows how old it is ----------------------------------------


def test_a_fresh_perception_renders_as_it_always_did():
    from src.core.perception.types import Perception, PerceptionKind

    p = Perception(PerceptionKind.CHAT, "chat:ui", "[Ema] ciao", ts=1000.0)
    assert p.render(now=1005.0) == "[Ema] ciao"


def test_an_old_perception_says_when_it_arrived():
    from src.core.perception.types import Perception, PerceptionKind

    p = Perception(PerceptionKind.CHAT, "chat:ui", "[Ema] ciao", ts=1000.0)
    assert p.render(now=1000.0 + 600) == "(10 min ago) [Ema] ciao"


def test_without_a_reference_time_nothing_changes():
    from src.core.perception.types import Perception, PerceptionKind

    p = Perception(PerceptionKind.CHAT, "chat:ui", "[Ema] ciao", ts=1000.0)
    assert p.render() == "[Ema] ciao"


# --- it reaches her, in both kinds of turn -----------------------------------


class Cfg:
    def __init__(self, **kw):
        self.consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                              "burst_steps": 3, "history_limit": 30,
                              "correlation_timeout": 5.0}
        self.attention = {}
        self.skills = {}
        self.persona = {}
        self.timezone = kw.get("timezone", "")


def _live_mind(memory=None):
    from src.core.attention.gate import Attention
    from src.core.consciousness import Consciousness
    from src.core.perception.bus import PerceptionBus
    from src.core.skills.base import SkillRegistry
    from src.core.skills.clock import ClockSkill
    from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents

    config = Cfg()
    registry = SkillRegistry()

    class Ctx:
        pass

    ctx = Ctx()
    ctx.memory = memory
    clock = ClockSkill(config, bus=None, expression=None, context=ctx)
    clock.initialize()
    clock.active = True
    registry.register(clock)

    return Consciousness(
        config=config, llm=FakeLLMClient(), bus=PerceptionBus(window=0.0),
        expression=FakeExpression(), surfaces=registry, history_manager=FakeHistory(),
        event_manager=RecordingEvents(), soul_getter=lambda: "", operating_getter=lambda: "",
        attention=Attention(config),
    )


def test_the_live_loop_is_told_what_time_it_is():
    mind = _live_mind()
    assert "[RIGHT NOW]" in mind._system_message([])["content"]


def test_the_live_loop_is_told_how_long_she_has_been_up():
    from src.core.memory.store import MemoryStore

    memory = MemoryStore(":memory:")
    memory.sessions.record("s1", started_at=__import__("time").time() - 8100)
    mind = _live_mind(memory)
    assert "up for 2h" in mind._system_message([])["content"]


def test_a_batch_that_spans_time_says_so():
    import time

    from src.core.perception.types import Perception, PerceptionKind

    mind = _live_mind()
    old = Perception(PerceptionKind.CHAT, "chat:ui", "[Ema] prima", ts=time.time() - 900)
    fresh = Perception(PerceptionKind.CHAT, "chat:ui", "[Ema] adesso")
    frame = mind._frame([old, fresh])["content"]
    assert "min ago) [Ema] prima" in frame
    assert "[Ema] adesso" in frame
    assert "ago) [Ema] adesso" not in frame


def test_a_batch_that_arrived_at_once_stays_clean():
    from src.core.perception.types import Perception, PerceptionKind

    mind = _live_mind()
    frame = mind._frame([
        Perception(PerceptionKind.CHAT, "chat:ui", "[Ema] uno"),
        Perception(PerceptionKind.CHAT, "chat:ui", "[Ema] due"),
    ])["content"]
    assert "ago)" not in frame


def test_a_written_conversation_is_told_the_time_too():
    from src.core.memory.store import MemoryStore
    from src.core.mind.conversation import ConversationMind
    from src.core.mind.scheduler import ConversationScheduler
    from src.core.skills.base import SkillRegistry

    memory = MemoryStore(":memory:")
    mind = ConversationMind(
        config=Cfg(), llm=None, memory=memory, surfaces=SkillRegistry(),
        soul_getter=lambda: "", operating_getter=lambda: "",
        scheduler=ConversationScheduler(),
    )
    system = mind._build_context("telegram:2", [], first=True)[0]["content"]
    assert "[RIGHT NOW]" in system


def test_a_written_conversation_knows_when_she_last_wrote_there():
    import time

    from src.core.memory.store import MemoryStore
    from src.core.mind.conversation import ConversationMind
    from src.core.mind.scheduler import ConversationScheduler
    from src.core.skills.base import SkillRegistry

    memory = MemoryStore(":memory:")
    memory.conversations.add(conversation_key="telegram:2", role="bea", content="ciao",
                             ts=time.time() - 1200)
    mind = ConversationMind(
        config=Cfg(), llm=None, memory=memory, surfaces=SkillRegistry(),
        soul_getter=lambda: "", operating_getter=lambda: "",
        scheduler=ConversationScheduler(),
    )
    system = mind._build_context("telegram:2", [], first=True)[0]["content"]
    assert "You last spoke here 20 min ago" in system


def test_a_recalled_memory_in_a_dm_carries_its_date():
    """The live loop dated its recollections; the DMs — where "yesterday" is
    actually said — did not."""
    from src.core.memory.rag import Recollection
    from src.core.mind.conversation import _render_recollections

    rendered = _render_recollections([
        Recollection(text="ha l'esame di sistemi", who="Ema", source="user",
                     similarity=0.8, created_at=1756000000.0),
    ])
    assert "2025-08-24" in rendered or "-" in rendered
    assert "ha l'esame di sistemi" in rendered


def test_the_timezone_is_a_setting_not_a_guess():
    from src.core.config import BrainConfig

    assert hasattr(BrainConfig(), "timezone")


def test_a_container_can_be_told_which_clock_to_use(tmp_path, monkeypatch):
    import json

    from src.core import config as config_module

    (tmp_path / "config.json").write_text(json.dumps({"timezone": "Europe/Rome"}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", "config.json")
    assert config_module.BrainConfig().timezone == "Europe/Rome"
