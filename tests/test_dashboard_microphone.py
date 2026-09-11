"""The microphone on the dashboard is the owner talking, in the same room.

It was handed to the discord surface, for no better reason than that being
where voice had been implemented first. So it arrived as an unknown person
speaking in a call she was not in — which the attention gate is entitled to let
go by, and did. The mic worked, the transcript came back, and she said nothing:
from the outside, indistinguishable from voice being broken.
"""

from src.core.attention.gate import Attention
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import PerceptionKind
from src.core.skills.chat import ChatSurface


class Config:
    def __init__(self):
        self.skills = {}
        self.attention = {"enabled": True, "cooldown_seconds": 0, "interject_threshold": 0.45,
                          "quiet_hours": [], "trigger_words": ["bea"], "hot_names": [],
                          "self_ids": [], "digest_max_lines": 8}
        self.persona = {}


def _surface():
    surface = ChatSurface(Config(), bus=PerceptionBus(window=0.0), expression=None)
    surface.active = True
    return surface


def test_a_spoken_line_arrives_as_voice():
    p = _surface().perceive_voice("ciao, come stai?")
    assert p.kind is PerceptionKind.VOICE
    assert "ciao, come stai?" in p.content


def test_it_arrives_on_the_dashboard_not_on_discord():
    p = _surface().perceive_voice("ciao")
    assert p.surface == "chat:ui"
    assert p.author.platform == "ui"


def test_the_person_at_the_microphone_is_the_owner():
    """Anyone else and the gate may decide she has better things to do."""
    assert _surface().perceive_voice("ciao").author.is_owner


def test_the_gate_lets_her_own_voice_through():
    """The bug in one line: as a stranger on discord this was dropped here."""
    p = _surface().perceive_voice("ciao")
    kept, noted = Attention(Config()).judge([p])
    assert kept == [p]
    assert noted == []


def test_she_knows_nobody_else_is_in_the_room():
    """`listeners` is what stops the gate rolling dice over a single speaker."""
    p = _surface().perceive_voice("ciao")
    assert p.meta["listeners"] == 1
    assert p.meta["alone_with_speaker"] is True


def test_typing_still_arrives_as_chat():
    p = _surface().perceive("ciao")
    assert p.kind is PerceptionKind.CHAT
    assert p.surface == "chat:ui"
