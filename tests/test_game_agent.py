"""The mind decides an intention, the body pursues it.

What matters is what the mind stops carrying: twenty-five tools, crafting
trees, and a stream of `FINISHED: SUCCESS` in the conversation's context.
"""

import pytest

from src.core.agent.types import AssistantMessage, ToolCall
from src.core.skills.minecraft.agent import GameAgent
from src.core.skills.minecraft.notebook import Notebook
from src.core.skills.minecraft.surface import MinecraftSurface
from src.core.skills.minecraft.tools import build_minecraft_tools
from tests.fakes import FakeLLMClient

STATE = {
    "player": {"health": 20, "food": 20, "position": {"x": 0, "y": 64, "z": 0}, "uuid": "bea"},
    "inventory": {"hand_main": {"item": "minecraft:air", "count": 0}, "hotbar": [], "main": []},
}


class FakeClient:
    def __init__(self, results=None):
        self.latest_state = dict(STATE)
        self.calls = []
        self.results = results or {}

    async def execute(self, action, params, instant=False):
        self.calls.append((action, params))
        return self.results.get(action, "SUCCESS")


def agent(llm, client=None, on_milestone=None, **kwargs) -> GameAgent:
    client = client or FakeClient()
    return GameAgent(
        llm=llm, registry=build_minecraft_tools(client, Notebook()),
        notebook=Notebook(), state_getter=lambda: client.latest_state,
        rules="you are the body", on_milestone=on_milestone, **kwargs,
    )


def calls(name, **args) -> AssistantMessage:
    return AssistantMessage(tool_calls=[ToolCall(id="c1", name=name, arguments=args)])


def done(text: str) -> AssistantMessage:
    return AssistantMessage(content=text)


# --- pursuing a goal ---------------------------------------------------------


async def test_a_goal_is_pursued_and_reported():
    llm = FakeLLMClient([calls("find_block", block="log"), done("Got 4 logs.")])
    assert await agent(llm).pursue("get wood") == "Got 4 logs."


async def test_the_goal_reaches_the_body():
    llm = FakeLLMClient([done("ok")])
    await agent(llm).pursue("get a stone pickaxe")
    assert "get a stone pickaxe" in llm.last_system_prompt


async def test_an_empty_goal_is_refused():
    llm = FakeLLMClient()
    assert await agent(llm).pursue("  ") == "You didn't say what you wanted."
    assert llm.call_count == 0


async def test_the_body_gets_the_game_tools():
    llm = FakeLLMClient([done("ok")])
    await agent(llm).pursue("get wood")
    tools = llm.tools_seen[0]
    assert "find_block" in tools and "craft_item" in tools and "update_notebook" in tools


async def test_the_body_never_gets_her_voice():
    """It is a body, not a personality: it does not speak to anyone."""
    llm = FakeLLMClient([done("ok")])
    await agent(llm).pursue("get wood")
    assert "speak" not in llm.tools_seen[0]


async def test_the_body_sees_the_world_it_is_in():
    llm = FakeLLMClient([done("ok")])
    await agent(llm).pursue("get wood")
    first_user = llm.calls[0][1]["content"]
    assert "GAME STATE" in first_user and "health 20/20" in first_user


async def test_a_stuck_goal_stops_instead_of_grinding():
    llm = FakeLLMClient([calls("find_block", block="log")] * 20)
    result = await agent(llm, max_steps=3).pursue("get wood")
    assert llm.call_count == 3
    assert "stopped working on 'get wood'" in result


async def test_a_broken_model_does_not_take_her_down():
    llm = FakeLLMClient()
    llm.fail_with = RuntimeError("provider is down")
    assert "gave up" in await agent(llm).pursue("get wood")


# --- what comes back to her --------------------------------------------------


async def test_finishing_something_is_worth_telling_her():
    seen = []
    llm = FakeLLMClient([calls("craft_item", item="stone_pickaxe"), done("Done.")])
    await agent(llm, on_milestone=seen.append).pursue("get a pickaxe")
    assert any("craft_item" in m for m in seen)


async def test_walking_around_is_not():
    """She does not need to hear that a pathfind succeeded."""
    seen = []
    llm = FakeLLMClient([calls("move_to", x=1, y=64, z=1), done("Done.")])
    await agent(llm, on_milestone=seen.append).pursue("go over there")
    assert seen == []


async def test_notebook_edits_are_never_reported():
    seen = []
    llm = FakeLLMClient([calls("update_notebook", notes="plan"), done("Done.")])
    await agent(llm, on_milestone=seen.append).pursue("think")
    assert seen == []


async def test_being_interrupted_always_reaches_her():
    seen = []
    client = FakeClient({"mine_block": "INTERRUPTED: lava ahead"})
    llm = FakeLLMClient([calls("mine_block", x=0, y=63, z=0), done("Stopped.")])
    await agent(llm, client=client, on_milestone=seen.append).pursue("dig down")
    assert any("interrupted" in m for m in seen)


async def test_a_real_failure_reaches_her():
    seen = []
    client = FakeClient({"craft_item": "FAILURE_MISSING_MATERIALS"})
    llm = FakeLLMClient([calls("craft_item", item="pickaxe"), done("No luck.")])
    await agent(llm, client=client, on_milestone=seen.append).pursue("craft a pickaxe")
    assert any("couldn't craft_item" in m for m in seen)


async def test_she_can_see_what_her_body_is_up_to():
    llm = FakeLLMClient([done("ok")])
    a = agent(llm)
    assert a.describe() == ""
    a.goal = "get a stone pickaxe"
    a.started_at = __import__("time").time()
    a._task = _NeverDone()
    assert "get a stone pickaxe" in a.describe()


class _NeverDone:
    def done(self):
        return False


# --- what the mind is left holding ------------------------------------------


class Config:
    def __init__(self):
        self.skills = {"minecraft": {"enabled": True}}
        self.attention = {"trigger_words": ["bea"]}


@pytest.fixture
def surface():
    s = MinecraftSurface(Config(), bus=_Bus(), expression=None)
    s.initialize()
    s.active = True
    s.client = FakeClient()
    s._registry = build_minecraft_tools(s.client, s.notebook)
    s.agent = GameAgent(
        llm=FakeLLMClient(), registry=s._registry, notebook=s.notebook,
        state_getter=s._latest_state, rules="body", on_milestone=s._emit_milestone,
    )
    return s


class _Bus:
    def __init__(self):
        self.items = []

    def put(self, perception):
        self.items.append(perception)


def test_the_mind_holds_seven_tools_not_twenty_five(surface):
    names = [t.name for t in surface.tools()]
    assert len(names) == 7
    assert "play_minecraft" in names
    assert "mine_block" not in names and "craft_item" not in names


def test_the_body_actions_are_attributed_to_the_game(surface):
    """A hardcoded surface mislabelled the result of every non-minecraft action."""
    for tool in surface.tools():
        if tool.long_running:
            assert tool.surface == "game:mc"


def test_typing_in_chat_does_not_tie_up_the_body(surface):
    chat = next(t for t in surface.tools() if t.name == "mc_chat")
    assert chat.long_running is False


async def test_typing_in_chat_reaches_the_game(surface):
    await next(t for t in surface.tools() if t.name == "mc_chat").handler(message="quella era mia")
    assert surface.client.calls == [("chat", {"message": "quella era mia"})]


async def test_stopping_puts_the_body_down(surface):
    await next(t for t in surface.tools() if t.name == "mc_stop").handler()
    assert surface.client.calls == [("stop_moving", {})]


async def test_going_to_a_player_names_them(surface):
    tool = next(t for t in surface.tools() if t.name == "mc_goto_player")
    await tool.handler(name="Marco")
    assert surface.client.calls == [("goto_player", {"name": "Marco"})]


async def test_looking_at_a_player_uses_the_look_skill(surface):
    """The mod's LookSkill takes `player`; the tool takes `name`."""
    tool = next(t for t in surface.tools() if t.name == "mc_look_at_player")
    await tool.handler(name="Marco")
    assert surface.client.calls == [("look_at", {"player": "Marco"})]


def test_the_mind_no_longer_carries_the_notebook(surface):
    """The crafting chains are the body's problem now."""
    state = surface.live_state() or ""
    assert "NOTEBOOK" not in state


def test_the_mind_sees_what_the_body_is_doing(surface):
    surface.agent.goal = "get iron"
    surface.agent.started_at = __import__("time").time()
    surface.agent._task = _NeverDone()
    assert "get iron" in (surface.live_state() or "")
