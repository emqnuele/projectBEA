"""The mind decides an intention, the body pursues it — and keeps pursuing it.

What matters is what the mind stops carrying: twenty-five tools, crafting
trees, and a stream of `FINISHED: SUCCESS` in the conversation's context. And
what the body stops needing: somebody to start it again every time it finishes.
"""

import asyncio
import types

import pytest

from src.core.agent.types import AssistantMessage, ToolCall
from src.core.skills.minecraft.agent import GameAgent
from src.core.skills.minecraft.goal import DONE, RUNNING, STUCK, SUSPENDED
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
        self.is_connected = True
        self.mod_version = "test"
        self.protocol = 2
        self.concurrent = {"chat", "check_death_log", "request_screenshot", "look_at"}

    async def execute(self, action, params, timeout=None):
        self.calls.append((action, params))
        return self.results.get(action, "SUCCESS")


def agent(llm, client=None, on_milestone=None, **kwargs) -> GameAgent:
    client = client or FakeClient()
    kwargs.setdefault("tick_seconds", 0)
    return GameAgent(
        llm=llm, registry=build_minecraft_tools(client, Notebook()),
        notebook=Notebook(), state_getter=lambda: client.latest_state,
        rules="you are the body", on_milestone=on_milestone, **kwargs,
    )


def calls(name, **args) -> AssistantMessage:
    return AssistantMessage(tool_calls=[ToolCall(id="c1", name=name, arguments=args)])


def done(text: str) -> AssistantMessage:
    """The body declaring the goal achieved, the only way it can."""
    return calls("goal_done", summary=text)


def prose(text: str) -> AssistantMessage:
    """The body writing instead of playing. Nobody sees it."""
    return AssistantMessage(content=text)


async def play(a: GameAgent, goal: str, timeout: float = 2.0, requires=None):
    """Runs the real loop until the goal closes, and returns it."""
    closed = asyncio.Event()
    previous = a.on_goal_closed

    def note(g):
        if previous is not None:
            previous(g)
        closed.set()

    a.on_goal_closed = note
    a.start()
    a.set_goal(goal, requires=requires)
    try:
        await asyncio.wait_for(closed.wait(), timeout)
    finally:
        await a.stop()
    return a.goal


# --- pursuing a goal ---------------------------------------------------------


async def test_a_goal_is_pursued_and_reported():
    llm = FakeLLMClient([calls("find_block", block="log"), done("Got 4 logs.")])
    goal = await play(agent(llm), "get wood")
    assert goal.status == DONE and goal.outcome == "Got 4 logs."


async def test_the_goal_reaches_the_body():
    llm = FakeLLMClient([done("ok")])
    await play(agent(llm), "get a stone pickaxe")
    assert "get a stone pickaxe" in llm.last_system_prompt


async def test_an_empty_goal_is_refused():
    a = agent(FakeLLMClient())
    assert a.set_goal("  ") == "You didn't say what you wanted."
    assert a.goal is None


async def test_the_body_gets_the_game_tools():
    llm = FakeLLMClient([done("ok")])
    await play(agent(llm), "get wood")
    tools = llm.tools_seen[0]
    assert "find_block" in tools and "craft_item" in tools and "update_notebook" in tools


async def test_the_body_can_say_it_is_done_or_stuck():
    """Ending is a decision it takes, not the model happening to go quiet."""
    llm = FakeLLMClient([done("ok")])
    await play(agent(llm), "get wood")
    assert "goal_done" in llm.tools_seen[0] and "goal_blocked" in llm.tools_seen[0]


async def test_the_body_never_gets_her_voice():
    """It is a body, not a personality: it does not speak to anyone."""
    llm = FakeLLMClient([done("ok")])
    await play(agent(llm), "get wood")
    assert "speak" not in llm.tools_seen[0]


async def test_the_body_sees_the_world_it_is_in():
    llm = FakeLLMClient([done("ok")])
    await play(agent(llm), "get wood")
    assert "GAME STATE" in _text(llm.calls[0]) and "health 20/20" in _text(llm.calls[0])


async def test_the_body_keeps_seeing_the_world():
    """It used to be handed the state once and then play blind for 24 steps.

    Health, hunger and what is standing next to it are exactly the things that
    change while it works, so the one snapshot it had was the one thing it
    could not trust.
    """
    client = FakeClient()
    llm = FakeLLMClient([calls("move_to", x=1, y=64, z=1)] * 3 + [done("ok")])
    a = agent(llm, client=client, refresh_every=2)

    async def hurt(*_a, **_k):
        client.latest_state["player"]["health"] = 4
        return "SUCCESS"

    client.execute = hurt
    await play(a, "walk about")
    assert "health 4/20" in _text(llm.calls[-1])


async def test_running_out_of_room_hands_it_back_instead_of_grinding():
    llm = FakeLLMClient([calls("find_block", block="log")] * 20)
    goal = await play(agent(llm, steps_per_goal=3), "get wood")
    assert goal.status == STUCK and llm.call_count == 3


async def test_failing_the_same_way_forever_stops():
    client = FakeClient({"craft_item": "FAILURE_MISSING_MATERIALS"})
    llm = FakeLLMClient([calls("craft_item", item="pickaxe")] * 30)
    goal = await play(agent(llm, client=client, steps_per_goal=50), "craft a pickaxe")
    assert goal.status == STUCK and llm.call_count < 20


async def test_the_body_saying_it_cannot_reaches_her_as_stuck():
    llm = FakeLLMClient([calls("goal_blocked", reason="there is no iron anywhere")])
    goal = await play(agent(llm), "get iron")
    assert goal.status == STUCK and "no iron" in goal.outcome


async def test_prose_is_not_an_ending():
    """A body that answers in words has done nothing, and is told so."""
    llm = FakeLLMClient([prose("I should probably get wood"), done("Got it.")])
    goal = await play(agent(llm), "get wood")
    assert goal.status == DONE
    assert any("NOTHING HAPPENED" in str(m.get("content", "")) for m in llm.calls[-1])


async def test_a_broken_model_does_not_take_the_loop_down():
    llm = FakeLLMClient()
    llm.fail_with = RuntimeError("provider is down")
    a = agent(llm, steps_per_goal=3)
    goal = await play(a, "get wood")
    assert goal.status == STUCK


async def test_the_loop_outlives_the_goal():
    """The whole point: finishing one thing does not end her body."""
    llm = FakeLLMClient([done("first"), done("second")])
    a = agent(llm)
    try:
        a.start()
        for label in ("get wood", "get stone"):
            a.set_goal(label)
            await _until(lambda: a.goal is not None and a.goal.status == DONE)
        assert a.goal.outcome == "second"
    finally:
        await a.stop()


async def test_a_new_goal_replaces_the_old_one():
    a = agent(FakeLLMClient())
    a.set_goal("get wood")
    first = a.goal
    a.set_goal("get stone")
    assert not first.open and a.goal.text == "get stone"
    assert a.ctx.rounds == 0  # the new goal starts on a clean window


async def test_calling_it_off_puts_the_body_down():
    a = agent(FakeLLMClient())
    a.set_goal("get wood")
    a.clear_goal("she changed her mind")
    assert not a.busy


# --- the mind borrowing the body --------------------------------------------


async def test_borrowing_the_body_does_not_destroy_the_goal():
    """Looking at somebody who said hello used to cost her the house."""
    a = agent(FakeLLMClient())
    a.set_goal("build a house")
    a.borrow()
    assert a.goal.status == SUSPENDED and a.goal.text == "build a house"
    a.give_back("she looked at Marco")
    assert a.goal.status == RUNNING


async def test_the_goal_only_resumes_once_everyone_is_done_with_the_body():
    a = agent(FakeLLMClient())
    a.set_goal("build a house")
    a.borrow()
    a.borrow()
    a.give_back()
    assert a.goal.status == SUSPENDED
    a.give_back()
    assert a.goal.status == RUNNING


async def test_coming_back_it_is_told_it_was_taken_away():
    a = agent(FakeLLMClient())
    a.set_goal("build a house")
    a.borrow()
    a.give_back("she walked over to Marco")
    text = " ".join(str(m.get("content", "")) for m in a.ctx.messages("rules"))
    assert "Marco" in text


# --- what comes back to her --------------------------------------------------


async def test_finishing_something_is_worth_telling_her():
    seen = []
    llm = FakeLLMClient([calls("craft_item", item="stone_pickaxe"), done("Done.")])
    await play(agent(llm, on_milestone=seen.append), "get a pickaxe")
    assert any("craft_item" in m for m in seen)


async def test_walking_around_is_not():
    """She does not need to hear that a pathfind succeeded."""
    seen = []
    llm = FakeLLMClient([calls("move_to", x=1, y=64, z=1), done("Done.")])
    await play(agent(llm, on_milestone=seen.append), "go over there")
    assert seen == []


async def test_notebook_edits_are_never_reported():
    seen = []
    llm = FakeLLMClient([calls("update_notebook", notes="plan"), done("Done.")])
    await play(agent(llm, on_milestone=seen.append), "think")
    assert seen == []


async def test_being_interrupted_always_reaches_her():
    seen = []
    client = FakeClient({"mine_block": "INTERRUPTED: lava ahead"})
    llm = FakeLLMClient([calls("mine_block", x=0, y=63, z=0), done("Stopped.")])
    await play(agent(llm, client=client, on_milestone=seen.append), "dig down")
    assert any("interrupted" in m for m in seen)


async def test_a_real_failure_reaches_her():
    seen = []
    client = FakeClient({"craft_item": "FAILURE_MISSING_MATERIALS"})
    llm = FakeLLMClient([calls("craft_item", item="pickaxe"), done("No luck.")])
    await play(agent(llm, client=client, on_milestone=seen.append), "craft a pickaxe")
    assert any("couldn't craft_item" in m for m in seen)


async def test_she_can_see_what_her_body_is_up_to():
    a = agent(FakeLLMClient())
    assert a.describe() == ""
    a.set_goal("get a stone pickaxe")
    assert "get a stone pickaxe" in a.describe()


# --- the body's own window ---------------------------------------------------


async def test_the_window_never_grows_forever():
    llm = FakeLLMClient([calls("move_to", x=1, y=64, z=1)] * 30)
    a = agent(llm, steps_per_goal=20, keep_rounds=4)
    await play(a, "walk about")
    assert a.ctx.rounds <= 4


async def test_trimming_never_orphans_a_tool_result():
    """A `tool` message whose `tool_calls` were trimmed away is a 400."""
    llm = FakeLLMClient([calls("move_to", x=1, y=64, z=1)] * 30)
    a = agent(llm, steps_per_goal=20, keep_rounds=3)
    await play(a, "walk about")
    sent = llm.calls[-1]
    answered = {m["tool_call_id"] for m in sent if m["role"] == "tool"}
    asked = {c["id"] for m in sent if m.get("tool_calls") for c in m["tool_calls"]}
    assert answered <= asked


async def test_the_notebook_survives_the_trim():
    """It is the one memory the body keeps on purpose."""
    a = agent(FakeLLMClient([done("ok")]))
    a.notebook.update("[x] got wood\n[ ] craft a pickaxe")
    await play(a, "carry on")
    assert "craft a pickaxe" in _text(a.llm.calls[-1])


def _text(messages) -> str:
    return "\n".join(str(m.get("content", "") or "") for m in messages)


async def _until(predicate, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("timed out waiting for the body")
        await asyncio.sleep(0.005)


# --- what the mind is left holding ------------------------------------------


class Config:
    def __init__(self):
        self.skills = {"minecraft": {"enabled": True}}
        self.attention = {"trigger_words": ["bea"]}


class _Bus:
    def __init__(self):
        self.items = []

    def put(self, perception):
        self.items.append(perception)


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
        on_goal_closed=s._on_goal_closed, tick_seconds=0,
    )
    return s


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


def test_giving_the_body_a_goal_comes_straight_back(surface):
    """It is a direction, not an errand she stands and waits through."""
    play_tool = next(t for t in surface.tools() if t.name == "play_minecraft")
    assert play_tool.long_running is False


async def test_giving_the_body_a_goal_sets_it(surface):
    tool = next(t for t in surface.tools() if t.name == "play_minecraft")
    await tool.handler(goal="build a shelter")
    assert surface.agent.goal.text == "build a shelter"


def test_typing_in_chat_does_not_tie_up_the_body(surface):
    chat = next(t for t in surface.tools() if t.name == "mc_chat")
    assert chat.long_running is False


async def test_typing_in_chat_reaches_the_game(surface):
    await next(t for t in surface.tools() if t.name == "mc_chat").handler(message="quella era mia")
    assert surface.client.calls == [("chat", {"message": "quella era mia"})]


async def test_stopping_puts_the_body_down(surface):
    surface.agent.set_goal("get wood")
    await next(t for t in surface.tools() if t.name == "mc_stop").handler()
    assert surface.client.calls == [("stop_moving", {})]
    assert not surface.agent.busy


async def test_going_to_a_player_names_them(surface):
    tool = next(t for t in surface.tools() if t.name == "mc_goto_player")
    await tool.handler(name="Marco")
    assert surface.client.calls == [("goto_player", {"name": "Marco"})]


async def test_looking_at_a_player_uses_the_look_skill(surface):
    """The mod's LookSkill takes `player`; the tool takes `name`."""
    tool = next(t for t in surface.tools() if t.name == "mc_look_at_player")
    await tool.handler(name="Marco")
    assert surface.client.calls == [("look_at", {"player": "Marco"})]


async def test_a_reflex_puts_the_goal_down_and_picks_it_back_up(surface):
    surface.agent.set_goal("build a house")
    tool = next(t for t in surface.tools() if t.name == "mc_goto_player")
    await tool.handler(name="Marco")
    assert surface.agent.goal.text == "build a house"
    assert surface.agent.goal.status == RUNNING


async def test_a_glance_leaves_the_body_on_its_goal(surface, monkeypatch):
    """The mod turns the head beside whatever the body does; taking the body for
    it cancelled the move the body was in the middle of."""
    surface.agent.set_goal("build a house")
    borrowed = []
    monkeypatch.setattr(surface.agent, "borrow", lambda: borrowed.append(True))
    await next(t for t in surface.tools() if t.name == "mc_look_at_player").handler(name="Marco")
    assert borrowed == []
    assert surface.client.calls == [("look_at", {"player": "Marco"})]


async def test_walking_to_someone_still_takes_the_body(surface, monkeypatch):
    surface.agent.set_goal("build a house")
    borrowed = []
    monkeypatch.setattr(surface.agent, "borrow", lambda: borrowed.append(True))
    await next(t for t in surface.tools() if t.name == "mc_goto_player").handler(name="Marco")
    assert borrowed == [True]


def test_what_the_body_did_on_its_own_reaches_the_body(surface):
    surface._on_mod_event("reflex", {"type": "reflex", "reflex": "eat", "event": "started",
                                     "message": "eating: food was 12/20", "interrupted_id": None})
    assert surface.agent.behaviour_log == ["eat: eating: food was 12/20"]
    assert surface.bus.items == []          # eating is the body's business, not news


def test_being_attacked_and_fighting_back_reaches_her(surface):
    surface._on_mod_event("reflex", {"type": "reflex", "reflex": "defend", "event": "started",
                                     "message": "defending against Zombie", "interrupted_id": "r4"})
    assert any("defending against Zombie" in p.content for p in surface.bus.items)
    assert surface.agent.behaviour_log == ["defend: defending against Zombie"]


async def test_the_body_reads_what_it_did_on_its_own_before_its_next_move():
    llm = FakeLLMClient([calls("move_to", x=1, y=64, z=1), done("Done.")])
    a = agent(llm)
    a.start()
    a.set_goal("go over there")
    a.note_reflex("defend: defending against Zombie")
    await _until(lambda: a.goal.status == DONE)
    await a.stop()
    assert "While you were working: defend: defending against Zombie" in _text(llm.calls[0])
    assert _text(llm.calls[1]).count("While you were working") == 1    # told once, not every move
    assert a.behaviour_log == []


def test_a_burst_of_reflexes_stays_a_short_paragraph():
    a = agent(FakeLLMClient())
    for i in range(30):
        a.note_reflex(f"defend: swing {i}")
    assert len(a.behaviour_log) == 8 and a.behaviour_log[-1] == "defend: swing 29"


def test_the_mind_no_longer_carries_the_notebook(surface):
    """The crafting chains are the body's problem now."""
    state = surface.live_state() or ""
    assert "NOTEBOOK" not in state


def test_the_mind_sees_what_the_body_is_doing(surface):
    surface.agent.set_goal("get iron")
    assert "get iron" in (surface.live_state() or "")


def test_the_mind_sees_an_idle_body_too(surface):
    """She cannot decide to start if nothing tells her she has stopped."""
    assert "no goal" in (surface.live_state() or "")


def test_the_mind_can_read_the_bodys_mind(surface):
    surface.agent.set_goal("get iron")
    surface.agent.last_thought = "the cave to the east looked promising"
    assert "cave to the east" in (surface.live_state() or "")


def test_finishing_a_goal_reaches_her(surface):
    surface.agent.set_goal("get iron")
    surface.agent._close(surface.agent.goal, DONE, "three iron")
    last = surface.bus.items[-1]
    assert "three iron" in last.content and last.meta["event"] == "goal_done"


def test_getting_stuck_reaches_her_louder(surface):
    surface.agent.set_goal("get iron")
    surface.agent._close(surface.agent.goal, STUCK, "no iron anywhere")
    last = surface.bus.items[-1]
    assert last.meta["event"] == "goal_stuck" and last.salience >= 0.9


def test_her_own_change_of_mind_is_not_news(surface):
    surface.agent.set_goal("get iron")
    surface.agent.set_goal("get wood")
    assert surface.bus.items == []


def test_the_same_milestone_twice_is_one_interruption(surface):
    surface._emit_milestone("your body finished craft_item: SUCCESS")
    surface._emit_milestone("your body finished craft_item: SUCCESS")
    assert len(surface.bus.items) == 1


# --- the races the two of them can now have ---------------------------------


async def test_a_late_finish_cannot_close_the_goal_that_replaced_it():
    """She changed her mind mid-round; the old round must not report on the new goal."""
    a = agent(FakeLLMClient())
    a.set_goal("get wood")
    stale = a.goal
    a._round_goal = stale
    a.set_goal("get stone")

    assert "Too late" in a._tool_done("four logs")
    assert a.goal.status == RUNNING and a.goal.text == "get stone"


async def test_a_goal_closes_once_however_many_times_it_is_told_to():
    closed = []
    a = agent(FakeLLMClient())
    a.on_goal_closed = closed.append
    a.set_goal("get wood")
    a._round_goal = a.goal
    a._tool_done("four logs")
    a._tool_blocked("actually no")
    assert len(closed) == 1 and a.goal.status == DONE


# --- the whole thing, started the way the brain starts it -------------------


class LiveClient(FakeClient):
    """Enough of the mod for the surface to come up and stay up."""

    def __init__(self):
        super().__init__()
        self.stopped = False

    def connect(self):
        pass

    def stop(self):
        self.stopped = True

    async def wait_until_ready(self):
        return None

    async def wait_for_event_or_timeout(self, timeout):
        await asyncio.sleep(0.01)

    def drain_events(self):
        return []


async def test_the_skill_comes_up_playing(monkeypatch):
    """The wiring: switch the skill on and the body is already looping."""
    from src.core.skills.minecraft import surface as module

    client = LiveClient()
    monkeypatch.setattr(module, "MinecraftClient", lambda *a, **k: client)

    llm = FakeLLMClient([calls("find_block", block="log"), done("Four logs.")])
    config = Config()
    config.skills["minecraft"]["tick_seconds"] = 0
    skill = MinecraftSurface(config, bus=_Bus(), expression=None,
                             context=types.SimpleNamespace(model_for=lambda role: llm,
                                                           memory=None))
    skill.initialize()
    await skill.start()
    try:
        assert skill.agent is not None
        skill.agent.set_goal("get wood")
        await _until(lambda: skill.agent is not None and not skill.agent.busy)
        assert skill.agent.goal.status == DONE
        assert any(p.meta.get("event") == "goal_done" for p in skill.bus.items)
    finally:
        await skill.stop()
    assert client.stopped


async def test_switching_the_skill_off_stops_the_body(monkeypatch):
    """A loop outliving the socket spends a minute timing out on every move."""
    from src.core.skills.minecraft import surface as module

    monkeypatch.setattr(module, "MinecraftClient", lambda *a, **k: LiveClient())
    skill = MinecraftSurface(Config(), bus=_Bus(), expression=None,
                             context=types.SimpleNamespace(model_for=lambda role: FakeLLMClient(),
                                                           memory=None))
    skill.initialize()
    await skill.start()
    body = skill.agent
    body.set_goal("get wood")
    await skill.stop()
    assert body._loop_task is None and not skill.active
