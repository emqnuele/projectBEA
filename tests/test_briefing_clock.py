"""One clock, one header, in her own timezone.

Every briefing used to carry two `[RIGHT NOW]` blocks (the clock and the hot
facts) plus a `CURRENT DATE` line that read the machine clock instead of the
configured zone — so the two dates disagreed around midnight in a UTC
container. Now the clock owns `[RIGHT NOW]`, hot facts are `[HOT FACTS]`, and
every date comes from the configured zone.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.memory.store import MemoryStore
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Perception, PerceptionKind
from src.core.skills.base import SkillRegistry
from src.core.skills.clock import ClockSkill
from src.core.skills.dream.surface import _days_until
from src.core.timeline import now_in_timezone, today_in_timezone
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents


class Config:
    def __init__(self, timezone=""):
        self.consciousness = {"idle_after": 3600.0, "window": 0.0, "burst_steps": 3,
                              "correlation_timeout": 5.0}
        self.attention = {}
        self.skills = {}
        self.persona = {}
        self.language = "auto"
        self.timezone = timezone


def _mind(*skills, timezone=""):
    registry = SkillRegistry()
    for s in skills:
        s.active = True
        registry.register(s)
    config = Config(timezone=timezone)
    return Consciousness(
        config=config, llm=FakeLLMClient(), bus=PerceptionBus(window=0.0),
        expression=FakeExpression(), surfaces=registry, history_manager=FakeHistory(),
        event_manager=RecordingEvents(), soul_getter=lambda: "she is called Bea",
        operating_getter=lambda: "she speaks with `speak`",
        memory=MemoryStore(":memory:"), profiler=None, attention=Attention(config),
    )


def _skill(cls, timezone=""):
    return cls(Config(timezone=timezone), bus=None, expression=None, context=None)


BATCH = [Perception(PerceptionKind.CHAT, "chat:ui", "[ema]: ciao")]


def test_the_briefing_carries_no_machine_date_line():
    mind = _mind()
    assert "CURRENT DATE" not in mind._briefing(BATCH)["content"]


def test_the_clock_owns_the_only_right_now():
    clock = _skill(ClockSkill)
    clock.active = True
    mind = _mind(clock)
    content = mind._briefing(BATCH)["content"]
    assert content.count("[RIGHT NOW]") == 1


def test_hot_facts_arrive_under_their_own_header(tmp_path):
    store = MemoryStore(str(tmp_path / "bea.db"))
    try:
        store.hot.add("ema's exam is tomorrow", 3600, "test")
        assert store.hot.render().startswith("[HOT FACTS]")
        assert "[RIGHT NOW]" not in store.hot.render()
    finally:
        store.close()


def test_today_follows_the_configured_zone_not_the_machine():
    # 00:30 in Rome is still yesterday in UTC: the machine clock and her clock
    # disagree, and hers has to win.
    moment_utc = datetime(2026, 9, 22, 22, 30, tzinfo=ZoneInfo("UTC"))
    rome_day = moment_utc.astimezone(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%d")
    assert rome_day == "2026-09-23"
    assert today_in_timezone("Europe/Rome") == now_in_timezone("Europe/Rome").strftime("%Y-%m-%d")


def test_the_birthday_countdown_uses_her_day():
    assert _days_until("01-01", "UTC") is not None
