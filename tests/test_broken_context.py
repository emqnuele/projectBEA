"""A skill that breaks must cost its own block, not the whole turn.

Her context is assembled from a dozen independent sources. One of them raising
used to reach the loop's catch-all far away from where it happened: she went
silent on every message, and the log said `Invalid format string` and nothing
about which skill had said it or what it had been asked for.
"""

import pytest

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Perception, PerceptionKind
from src.core.skills.base import Skill, SkillRegistry
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents


class Config:
    def __init__(self):
        self.consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                              "burst_steps": 3, "history_limit": 30,
                              "correlation_timeout": 5.0}
        self.attention = {}
        self.skills = {}
        self.persona = {}


class Broken(Skill):
    """Every hook raises the way the clock did on windows."""

    name = "broken"

    @property
    def context_section(self):
        raise ValueError("Invalid format string")

    def live_state(self):
        raise ValueError("Invalid format string")

    def context_for(self, batch):
        raise ValueError("Invalid format string")


class Working(Skill):
    name = "working"

    @property
    def context_section(self):
        return "## RULES\nsomething she needs to know"

    def live_state(self):
        return "[RIGHT NOW]\nhalf past noon"

    def context_for(self, batch):
        return "[LONG TERM MEMORY]\n- she likes the sea"


def _mind(*skills):
    registry = SkillRegistry()
    for skill in skills:
        skill.active = True
        registry.register(skill)
    config = Config()
    return Consciousness(
        config=config, llm=FakeLLMClient(), bus=PerceptionBus(window=0.0),
        expression=FakeExpression(), surfaces=registry, history_manager=FakeHistory(),
        event_manager=RecordingEvents(), soul_getter=lambda: "she is called Bea",
        operating_getter=lambda: "she speaks with `speak`", attention=Attention(config),
    )


def _skill(cls):
    return cls(Config(), bus=None, expression=None, context=None)


BATCH = [Perception(PerceptionKind.CHAT, "chat:ui", "[ema]: ciao")]


def test_a_broken_skill_does_not_cost_the_system_prompt():
    mind = _mind(_skill(Broken), _skill(Working))
    content = mind._system_message()["content"]
    assert "she is called Bea" in content
    assert "something she needs to know" in content


def test_a_broken_skill_does_not_cost_the_briefing():
    mind = _mind(_skill(Broken), _skill(Working))
    content = mind._briefing(BATCH)["content"]
    assert "half past noon" in content
    assert "she likes the sea" in content


def test_the_whole_turn_is_not_lost_to_one_bad_block():
    """What actually happened: she answered nothing, to anyone, for an hour."""
    mind = _mind(_skill(Broken))
    assert mind._system_message()["content"]
    assert mind._briefing(BATCH) is not None


def test_the_log_names_the_skill_and_what_it_was_asked_for(caplog):
    mind = _mind(_skill(Broken))
    with caplog.at_level("ERROR", logger="bea.skills"):
        mind._briefing(BATCH)
    logged = caplog.text
    assert "broken" in logged
    assert "live state" in logged


@pytest.mark.parametrize("attribute", ["recap", "attention", "conversations"])
def test_a_broken_block_outside_the_skills_is_left_out_too(attribute):
    mind = _mind(_skill(Working))

    class Raises:
        def __getattr__(self, name):
            def boom(*args, **kwargs):
                raise ValueError("Invalid format string")
            return boom

    setattr(mind, attribute, Raises())
    assert "half past noon" in mind._briefing(BATCH)["content"]
