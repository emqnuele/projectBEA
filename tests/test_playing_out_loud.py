"""She is a streamer, and a streamer who goes quiet is broken.

Two separate silences. The bus one: the game body heartbeats every few seconds,
and the heartbeat was keeping the idle timer permanently reset, so with
Minecraft on she could never notice a silence at all. The skill one: mid-goal
the only thing that reached her was a milestone, minutes apart.
"""

import asyncio
import time
import types

import pytest

from src.core.agent.types import AssistantMessage, ToolCall
from src.core.brain import AIVtuberBrain
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Perception, PerceptionKind
from src.core.skills.minecraft.agent import GameAgent
from src.core.skills.minecraft.notebook import Notebook
from src.core.skills.minecraft.surface import MinecraftSurface
from src.core.skills.minecraft.tools import build_minecraft_tools
from tests.fakes import FakeLLMClient

STATE = {
    "player": {"health": 20, "food": 20, "position": {"x": 0, "y": 64, "z": 0}, "uuid": "bea"},
    "inventory": {"hand_main": {"item": "minecraft:air", "count": 0}, "hotbar": [], "main": []},
}


def heartbeat() -> Perception:
    return Perception(PerceptionKind.GAME, "game:mc", "(still playing)",
                      salience=0.15, meta={"noise": True})


def said(text: str) -> Perception:
    return Perception(PerceptionKind.CHAT, "chat:mc", text, salience=0.7)


# --- the bus: texture is not something happening ----------------------------


async def test_the_game_heartbeat_no_longer_holds_off_the_silence():
    """With this broken she never monologued again once Minecraft was on."""
    bus = PerceptionBus(window=0.0)

    async def beating():
        for _ in range(8):
            bus.put(heartbeat())
            await asyncio.sleep(0.01)

    beat = asyncio.create_task(beating())
    batch = await bus.wait_or_idle(0.05)
    await beat

    assert [p.kind for p in batch] == [PerceptionKind.IDLE]


async def test_something_real_still_reaches_her_at_once():
    bus = PerceptionBus(window=0.0)
    bus.put(said("ciao bea"))
    batch = await bus.wait_or_idle(30.0)
    assert [p.content for p in batch] == ["ciao bea"]


async def test_a_heartbeat_alongside_something_real_is_still_delivered():
    """Only an all-texture batch is swallowed; a mixed one arrives whole."""
    bus = PerceptionBus(window=0.0)
    bus.put(heartbeat())
    bus.put(said("ciao bea"))
    batch = await bus.wait_or_idle(30.0)
    assert len(batch) == 2


# --- the body thinking out loud ---------------------------------------------


class FakeClient:
    def __init__(self):
        self.latest_state = dict(STATE)
        self.calls = []

    async def execute(self, action, params, timeout=None):
        self.calls.append((action, params))
        return "SUCCESS"


def body(llm, on_milestone=None) -> GameAgent:
    client = FakeClient()
    return GameAgent(
        llm=llm, registry=build_minecraft_tools(client, Notebook()),
        notebook=Notebook(), state_getter=lambda: client.latest_state,
        rules="you are the body", on_milestone=on_milestone,
    )


def thinking(text: str, tool: str, **args) -> AssistantMessage:
    return AssistantMessage(content=text,
                            tool_calls=[ToolCall(id="c1", name=tool, arguments=args)])


def finished(summary: str) -> AssistantMessage:
    return AssistantMessage(
        tool_calls=[ToolCall(id="c9", name="goal_done", arguments={"summary": summary})])


async def play(agent: GameAgent, goal: str, timeout: float = 2.0) -> None:
    """Runs the body's real loop until the goal closes."""
    closed = asyncio.Event()
    agent.on_goal_closed = lambda _g: closed.set()
    agent.tick_seconds = 0
    agent.start()
    agent.set_goal(goal)
    try:
        await asyncio.wait_for(closed.wait(), timeout)
    finally:
        await agent.stop()


async def test_the_body_thinking_out_loud_is_kept_for_her():
    """It reasoned in prose at every step and all of it was thrown away."""
    seen = []
    agent = body(FakeLLMClient([thinking("the iron is under the lava", "find_block",
                                         block="iron_ore"),
                                finished("Found it.")]))
    agent.on_milestone = lambda _: seen.append(agent.last_thought)
    await play(agent, "find iron")
    assert seen == ["the iron is under the lava"]


async def test_a_new_goal_starts_without_the_last_one_thought():
    agent = body(FakeLLMClient())
    agent.last_thought = "the iron is under the lava"
    agent.set_goal("build a shelter")
    assert agent.last_thought == ""


# --- the skill: saying something while the body works -----------------------


class Plan:
    def open(self):
        return [types.SimpleNamespace(id=1, text="beat the game")]


class Context:
    memory = types.SimpleNamespace(plan=Plan())


class Config:
    def __init__(self):
        self.skills = {"minecraft": {"enabled": True}}
        self.attention = {"trigger_words": ["bea"]}


class Bus:
    def __init__(self):
        self.items = []

    def put(self, perception):
        self.items.append(perception)


@pytest.fixture
def surface():
    s = MinecraftSurface(Config(), bus=Bus(), expression=None, context=Context())
    s.initialize()
    s.active = True
    s.client = FakeClient()
    s._registry = build_minecraft_tools(s.client, s.notebook)
    s.agent = GameAgent(llm=FakeLLMClient(), registry=s._registry, notebook=s.notebook,
                        state_getter=s._latest_state, rules="body", tick_seconds=0)
    return s


def working(surface, since: float) -> None:
    """Her body mid-goal, set `since` seconds ago. No loop, no model calls."""
    surface.agent.set_goal("get a stone pickaxe")
    surface.agent.goal.set_at = time.time() - since


def test_she_is_asked_to_say_something_while_her_body_works(surface):
    working(surface, since=30)
    assert "get a stone pickaxe" in surface._nudge().content


def test_the_commentary_carries_what_the_body_is_thinking(surface):
    working(surface, since=30)
    surface.agent.last_thought = "the iron is under the lava"
    assert "the iron is under the lava" in surface._nudge().content


def test_the_commentary_is_declared_so_the_gate_cannot_drop_it(surface):
    working(surface, since=30)
    assert surface._nudge().meta.get("addressed")


def test_she_is_not_asked_to_comment_the_moment_the_goal_is_set(surface):
    """The turn that handed the body the goal already said something."""
    working(surface, since=0)
    assert surface._nudge() is None


def test_the_commentary_keeps_its_distance(surface):
    working(surface, since=30)
    assert surface._nudge() is not None
    assert surface._nudge() is None


def test_the_commentary_can_be_turned_off(surface):
    surface.skill_config["commentary_seconds"] = 0
    working(surface, since=300)
    assert surface._nudge() is None


def test_a_working_body_is_never_handed_another_goal(surface):
    """A second goal replaces the running one: the plan must not reach her here."""
    working(surface, since=300)
    assert "play_minecraft" not in surface._nudge().content


def test_a_body_standing_still_with_the_plan_open_is_still_sent_to_work(surface):
    surface._idle_since = time.time() - 300
    assert "play_minecraft" in surface._nudge().content


def test_the_idle_clock_only_starts_once_the_body_stops(surface):
    surface._idle_since = time.time() - 300
    working(surface, since=30)
    surface._nudge()
    assert surface._idle_since == 0.0


# --- the owner asking, off the clock ----------------------------------------


def test_the_button_asks_her_without_waiting_for_the_clock(surface):
    working(surface, since=0)
    assert surface._nudge() is None
    assert surface.ask_for_a_word() is True
    assert "get a stone pickaxe" in surface.bus.items[-1].content


def test_the_button_works_with_the_body_standing_still(surface):
    """A fair question to ask of someone standing around doing nothing."""
    assert surface.ask_for_a_word() is True
    assert "standing still" in surface.bus.items[-1].content


def test_the_button_says_so_when_she_is_not_in_the_game(surface):
    surface.active = False
    assert surface.ask_for_a_word() is False
    assert surface.bus.items == []


def test_asking_pushes_the_next_automatic_word_back(surface):
    """Answering the owner and then commenting a second later is babbling."""
    working(surface, since=300)
    surface.ask_for_a_word()
    assert surface._nudge() is None


# --- and from the dashboard --------------------------------------------------


@pytest.fixture
def api(surface):
    from fastapi.testclient import TestClient

    from src.web import app as web
    from src.web import deps

    class BrainStub:
        def __init__(self):
            self.surface = surface

        def _surface(self, name):
            return self.surface if name == "game:mc" else None

        # borrowed, not reimplemented: a stub of its own would not notice the
        # day the surface stops being called "game:mc"
        ask_minecraft_for_a_word = AIVtuberBrain.ask_minecraft_for_a_word

    stub = BrainStub()
    previous = deps.brain_instance
    deps.brain_instance = stub
    try:
        yield TestClient(web.app), surface
    finally:
        deps.brain_instance = previous


def test_the_dashboard_can_ask_her(api):
    client, surface = api
    working(surface, since=0)
    assert client.post("/minecraft/ask").status_code == 200
    assert surface.bus.items


def test_the_dashboard_is_told_when_she_is_not_in_the_game(api):
    """A button that silently does nothing is worse than one that says why."""
    client, surface = api
    surface.active = False
    assert client.post("/minecraft/ask").status_code == 409
