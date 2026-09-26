"""Actions that take time run beside her, and come back to her as what happened.

She is the one playing: a game action is something she does with her own hands,
not an errand handed to someone else. It runs in the background so she can keep
talking, and its outcome reaches her as a perception. Two things she asks for in
the same breath happen one after the other, the way a person does them, and a
turn that only set her hands moving costs one call, not two.
"""

import asyncio

from src.core.agent.tools import Tool
from src.core.agent.types import AssistantMessage, ToolCall
from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.memory.store import MemoryStore
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import Skill, SkillRegistry
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents, settle


class Config:
    def __init__(self):
        self.consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                              "burst_steps": 3, "correlation_timeout": 5.0,
                              "stream_speech": False, "turn_log": False,
                              "window_persist_after_turn": False}
        self.attention = {"enabled": True, "trigger_words": ["bea"]}
        self.skills = {}
        self.language = ""


class Hands(Skill):
    """A skill whose actions take a while, and a record of what they did."""

    name = "game:test"

    def __init__(self, config, bus, expression, answers=None, delay=0.05):
        super().__init__(config, bus, expression)
        self.active = True
        self.done: list = []
        self.answers = answers or {}
        self.delay = delay

    def tools(self):
        def action(name):
            async def handler(**kwargs):
                await asyncio.sleep(self.delay)
                self.done.append(name)
                return self.answers.get(name, f"SUCCESS: {name} done")
            return Tool(name, name, {"type": "object", "properties": {}}, handler,
                        long_running=True, surface=self.name)
        return [action("chop"), action("craft"), action("walk")]


def mind(*script, hands=None):
    config = Config()
    surfaces = SkillRegistry()
    bus = PerceptionBus(window=0.0)
    hands = hands or Hands(config, bus, None)
    hands.bus = bus
    surfaces.register(hands)
    m = Consciousness(
        config=config, llm=FakeLLMClient(script=list(script)), bus=bus,
        expression=FakeExpression(), surfaces=surfaces, history_manager=FakeHistory(),
        event_manager=RecordingEvents(), soul_getter=lambda: "soul",
        operating_getter=lambda: "rules", memory=MemoryStore(":memory:"),
        profiler=None, attention=Attention(config),
    )
    return m, hands


def calls(*names) -> AssistantMessage:
    return AssistantMessage(tool_calls=[
        ToolCall(id=f"c{i}", name=n, arguments={}) for i, n in enumerate(names)])


def says(message: str, *also) -> AssistantMessage:
    return AssistantMessage(tool_calls=[
        *(ToolCall(id=f"a{i}", name=n, arguments={}) for i, n in enumerate(also)),
        ToolCall(id="s", name="speak", arguments={"mood": "neutral", "message": message})])


def game(text: str = "You are standing in a forest.") -> Perception:
    return Perception(PerceptionKind.GAME, "game:test", text, salience=0.8,
                      meta={"addressed": "test"})


def chat(text: str = "bea come stai") -> Perception:
    return Perception(PerceptionKind.CHAT, "chat:mc", f"[marco] (in game): {text}",
                      salience=0.9, meta={"conversation_key": "stage", "mentions_self": True},
                      author=Author(platform="minecraft", native_id="u1", display_name="marco"))


async def turn(m: Consciousness, *batch: Perception) -> None:
    await m._run_turn(list(batch))


async def until(check, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not check():
        assert loop.time() < end, "timed out"
        await asyncio.sleep(0.01)


async def drained_actions(m: Consciousness) -> list:
    return [p for p in m.bus.drain_nowait() if p.kind is PerceptionKind.ACTION]


# --- one after the other --------------------------------------------------------


async def test_two_actions_in_one_breath_both_happen_in_order():
    """The second used to cancel the first before it had even started."""
    m, hands = mind(calls("chop", "craft"))
    await turn(m, game())
    await until(lambda: hands.done == ["chop", "craft"])


async def test_what_they_did_comes_back_as_one_perception_in_order():
    m, hands = mind(calls("chop", "craft"))
    await turn(m, game())
    await until(lambda: len(hands.done) == 2)
    back = await drained_actions(m)
    assert len(back) == 1
    text = back[0].content
    assert text.index("chop") < text.index("craft")
    assert back[0].surface == "game:test"


async def test_a_failure_stops_the_rest_and_says_what_was_not_done():
    """A person whose first step failed does not do the second one blind."""
    config = Config()
    hands = Hands(config, None, None, answers={"chop": "FAILURE_NONE_FOUND: no logs within 48"})
    m, hands = mind(calls("chop", "craft"), hands=hands)
    await turn(m, game())
    await until(lambda: hands.done == ["chop"])
    back = await drained_actions(m)
    assert "FAILURE_NONE_FOUND" in back[0].content
    assert "craft" in back[0].content and "not done" in back[0].content
    await asyncio.sleep(0.1)
    assert hands.done == ["chop"]


async def test_a_new_decision_replaces_what_her_hands_were_still_doing():
    """Across turns the newest decision wins: that is what changing her mind is."""
    config = Config()
    hands = Hands(config, None, None, delay=0.3)
    m, hands = mind(calls("chop"), calls("walk"), hands=hands)
    await turn(m, game())
    await turn(m, game("A zombie is coming."))
    await until(lambda: hands.done == ["walk"])
    await asyncio.sleep(0.4)
    assert hands.done == ["walk"]


# --- act first, then talk --------------------------------------------------------


async def test_after_acting_she_goes_on_and_then_talks():
    """A loop, not a reply: the action starts, then she says something about it."""
    m, hands = mind(calls("chop"), says("ugh, alberi"), says("should not be asked"))
    await turn(m, game())
    await settle()
    assert m.llm.call_count == 2
    assert m.expression.spoken[-1][1] == "ugh, alberi"
    await until(lambda: hands.done == ["chop"])


async def test_acting_and_speaking_in_one_step_is_one_call():
    m, _ = mind(says("ugh, alberi", "chop"), says("should not be asked"))
    await turn(m, game())
    assert m.llm.call_count == 1


# --- a world that expects her to act -------------------------------------------


class Game(Hands):
    """A skill that says so when a turn ends with nothing happening in it."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.asked: list = []

    def left_undone(self, batch, acted):
        self.asked.append([c["tool"] for c in acted])
        if any(c["tool"] in ("chop", "craft", "walk") for c in acted):
            return None
        return "[your hands are empty: act now]"


def game_mind(*script):
    config = Config()
    return mind(*script, hands=Game(config, None, None))


async def test_talking_about_it_is_not_doing_it():
    """Measured live: three game turns, each one `speak` alone, and the turn was over."""
    m, hands = game_mind(says("ok, chopping this birch"), calls("chop"))
    await turn(m, game())
    assert m.llm.call_count == 2
    assert "act now" in str(m.llm.calls[1][-1]["content"])
    await until(lambda: hands.done == ["chop"])


async def test_she_is_pushed_once_not_forever():
    m, _ = game_mind(says("ok"), says("still just talking"), says("should not be asked"))
    await turn(m, game())
    assert m.llm.call_count == 2


async def test_acting_needs_no_push():
    m, hands = game_mind(calls("chop"), says("ugh, alberi"), says("should not be asked"))
    await turn(m, game())
    assert m.llm.call_count == 2


async def test_a_world_with_nothing_to_do_changes_nothing():
    """Every other skill answers None: a telegram reply still ends at the reply."""
    m, hands = mind(says("ciao"), says("should not be asked"))
    await turn(m, chat())
    assert m.llm.call_count == 1
