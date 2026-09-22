"""Writing back happens at a human pace, and not on the mind's clock.

Every line goes out with a typing pause in front of it — up to four seconds
each, on purpose. Waiting for that inside the tool call held the whole loop for
as long as the answer was long, and everything arriving meanwhile piled up
behind it and came back as a second reply.
"""

import asyncio

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.events import EventCategory
from src.core.expression.humanizer import TextHumanizer
from src.core.memory.store import MemoryStore
from src.core.mind.tools import MindTools
from src.core.perception.bus import PerceptionBus
from src.core.skills.base import SkillRegistry
from src.core.skills.platform import PlatformSkill
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents


class Config:
    consciousness = {"enabled": True, "idle_after": 3600.0, "burst_steps": 3,
                     "correlation_timeout": 5.0, "turn_log": False,
                     "window_persist_after_turn": False}
    attention: dict = {}
    skills: dict = {}
    language = ""


class Slow(PlatformSkill):
    """A platform that types like a person: one beat per message."""

    name = "chat:telegram"
    skill_name = "telegram"
    platform = "telegram"

    def __init__(self, beat: float = 0.15):
        super().__init__(Config(), bus=None, expression=None)
        self.initialize()
        self.humanizer = TextHumanizer(sleep=self._beat)
        self.active = True
        self.sent: list = []
        self.beat = beat

    async def _beat(self, _seconds: float) -> None:
        await asyncio.sleep(self.beat)

    async def send_text(self, channel_id, text, reply_to=None):
        self.sent.append(text)
        return True


class Mute(Slow):
    """Everything it is handed is lost."""

    async def send_text(self, channel_id, text, reply_to=None):
        return False


def mind(platform) -> Consciousness:
    surfaces = SkillRegistry()
    surfaces.register(platform)
    config = Config()
    return Consciousness(
        config=config, llm=FakeLLMClient(), bus=PerceptionBus(window=0.0),
        expression=FakeExpression(), surfaces=surfaces,
        history_manager=FakeHistory(), event_manager=RecordingEvents(),
        soul_getter=lambda: "soul", operating_getter=lambda: "rules",
        memory=MemoryStore(":memory:"), profiler=None, attention=Attention(config),
    )


# --- the mind is not held --------------------------------------------------


async def test_the_turn_does_not_wait_for_three_typing_pauses():
    platform = Slow(beat=0.15)
    m = mind(platform)
    started = asyncio.get_running_loop().time()
    answer = await m._send_text("telegram", "99", "hey\nallora\ntutto bene?")
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 0.1, f"the mind waited {elapsed:.2f}s for the typing"
    assert answer == "Sending (3 message(s))."


async def test_every_line_still_goes_out():
    platform = Slow(beat=0.01)
    m = mind(platform)
    await m._send_text("telegram", "99", "hey\nallora\ntutto bene?")
    await asyncio.sleep(0.2)
    assert platform.sent == ["hey", "allora", "tutto bene?"]


async def test_the_turn_records_what_she_wrote_before_it_lands():
    """The window, the follow-up gate and `_answered` all read this."""
    m = mind(Slow())
    m._sent = []
    await m._send_text("telegram", "99", "ciao")
    assert m._sent == [{"platform": "telegram", "channel": "99", "text": "ciao"}]


# --- and a message that is lost is not quietly lost ------------------------


async def test_a_delivery_that_failed_reaches_the_log():
    m = mind(Mute(beat=0.01))
    await m._send_text("telegram", "99", "ciao")
    await asyncio.sleep(0.1)
    errors = [e for e in m.events.events if e[0] is EventCategory.ERROR]
    assert errors and "telegram:99" in errors[0][2]


async def test_an_empty_answer_is_refused_outright():
    assert (await mind(Slow())._send_text("telegram", "99", "   ")).startswith("FAILED")


# --- only somewhere she can actually write ---------------------------------


async def test_a_platform_that_cannot_take_text_is_not_a_destination():
    """Donations have a platform and no channel to answer in."""
    from src.core.skills.base import Skill

    class Donation(Skill):
        name = "donation"
        platform = "donation"

    donation = Donation(Config(), bus=None, expression=None)
    donation.active = True
    surfaces = SkillRegistry()
    surfaces.register(donation)
    m = mind(Slow())
    m.surfaces = surfaces
    assert (await m._send_text("donation", "1", "grazie")).startswith("FAILED")


def test_the_tool_names_the_destinations_that_exist():
    platform = Slow()
    surfaces = SkillRegistry()
    surfaces.register(platform)
    box = MindTools(surfaces, speak=lambda **k: "", stay_silent=lambda **k: "",
                    send_text=lambda **k: "")
    schema = next(s for s in box.schemas() if s["function"]["name"] == "send_message")
    assert schema["function"]["parameters"]["properties"]["platform"]["enum"] == ["telegram"]
    assert "telegram" in schema["function"]["description"]


def test_there_is_no_tool_when_there_is_nowhere_to_write():
    """An absent tool is a stronger guarantee than a rule in the prompt."""
    box = MindTools(SkillRegistry(), speak=lambda **k: "", stay_silent=lambda **k: "",
                    send_text=lambda **k: "")
    assert "send_message" not in box.names()


# --- and shutdown waits for what is still going out ------------------------


async def test_stopping_lets_the_last_lines_land():
    """Handing the delivery over means it can still be mid-sentence when the
    engine is asked to stop; dropping it ends a conversation halfway."""
    platform = Slow(beat=0.05)
    m = mind(platform)
    await m._send_text("telegram", "99", "aspetta\nsto scrivendo\necco")
    assert platform.sent != ["aspetta", "sto scrivendo", "ecco"]

    await m.stop()
    assert platform.sent == ["aspetta", "sto scrivendo", "ecco"]


async def test_a_delivery_that_hangs_does_not_hold_the_shutdown():
    class Hangs(Slow):
        async def send_text(self, channel_id, text, reply_to=None):
            await asyncio.sleep(3600)

    m = mind(Hangs(beat=0.01))
    m._DELIVERY_GRACE = 0.1
    await m._send_text("telegram", "99", "ciao")
    started = asyncio.get_running_loop().time()
    await m.stop()
    assert asyncio.get_running_loop().time() - started < 1.0
