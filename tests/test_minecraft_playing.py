"""She plays Minecraft herself: the game is one more place she lives in.

There is no second agent holding the controller for her. The skill hands her the
game's tools the way telegram hands her a way to write, what she does comes back
to her as what happened, and everything she reads about the game is about *her*:
"you are chopping wood", never "your body is". A player who narrates a body
working for her ends up giving it orders out loud instead of playing.
"""

import asyncio
import re
import time
import types
from pathlib import Path

import pytest

from src.core.skills.minecraft.surface import MinecraftSurface
from src.core.skills.minecraft.tools import build_minecraft_tools

BEA = "11111111-2222-3333-4444-555555555555"


def state(**inventory) -> dict:
    return {
        "player": {"uuid": BEA, "name": "Bea", "health": 20, "food": 20,
                   "position": {"x": 0, "y": 64, "z": 0}},
        "inventory": {"hand_main": {"item": "minecraft:air", "count": 0}, "hotbar": [],
                      "main": [{"slot": i, "item": f"minecraft:{name}", "count": count}
                               for i, (name, count) in enumerate(inventory.items())]},
    }


class FakeClient:
    def __init__(self):
        self.latest_state = state()
        self.calls = []
        self.results = {}
        self.is_connected = True
        self.mod_version = "test"
        self.protocol = 2
        self.concurrent = {"chat", "check_death_log", "request_screenshot", "look_at", "scan"}
        # an action waits here until the test lets it finish
        self.hold = None

    async def execute(self, action, params, timeout=None):
        self.calls.append((action, params))
        if self.hold is not None and action not in self.concurrent and action != "stop_moving":
            await self.hold.wait()
        return self.results.get(action, "SUCCESS")


class Plan:
    def __init__(self, *objectives):
        self.objectives = [types.SimpleNamespace(id=i + 1, text=t) for i, t in enumerate(objectives)]

    def open(self):
        return list(self.objectives)


class Config:
    def __init__(self, **minecraft):
        self.skills = {"minecraft": {"enabled": True, **minecraft}}
        self.attention = {"trigger_words": ["bea"]}


class Bus:
    def __init__(self):
        self.items = []

    def put(self, perception):
        self.items.append(perception)


def make(plan=None, **minecraft) -> MinecraftSurface:
    context = types.SimpleNamespace(memory=types.SimpleNamespace(plan=plan))
    s = MinecraftSurface(Config(**minecraft), bus=Bus(), expression=None, context=context)
    s.initialize()
    s.active = True
    s.client = FakeClient()
    s._registry = build_minecraft_tools(s.client)
    return s


@pytest.fixture
def surface():
    return make()


def tool(surface, name):
    return next(t for t in surface.tools() if t.name == name)


async def start(surface, action="find_block", **args):
    """Her hands on something that takes a while; returns the running task."""
    surface.client.hold = asyncio.Event()
    task = asyncio.create_task(tool(surface, action).handler(**args))
    await asyncio.sleep(0)
    return task


async def finish(surface, task):
    surface.client.hold.set()
    return await task


THIRD_PERSON = re.compile(r"\b(she|her|hers|herself|body)\b", re.IGNORECASE)


# --- the game's tools are hers --------------------------------------------------


def test_the_game_tools_are_in_her_hands(surface):
    names = {t.name for t in surface.tools()}
    assert {"find_block", "craft_item", "move_to", "attack_entity", "build_template",
            "go_to_surface", "crafting_plan", "scan", "mc_chat", "stop_moving"} <= names


def test_nothing_is_left_of_a_body_she_gives_orders_to(surface):
    names = {t.name for t in surface.tools()}
    assert not names & {"play_minecraft", "mc_stop", "mc_goto_player", "mc_follow_player",
                        "mc_look_at_player", "mc_give_item", "goal_done", "goal_blocked",
                        "update_notebook", "chat"}


def test_what_takes_time_runs_beside_her_and_a_glance_does_not(surface):
    assert tool(surface, "find_block").long_running
    assert tool(surface, "craft_item").long_running
    assert not tool(surface, "scan").long_running
    assert not tool(surface, "crafting_plan").long_running
    assert not tool(surface, "mc_chat").long_running


def test_every_action_says_where_it_happened(surface):
    assert {t.surface for t in surface.tools() if t.long_running} == {"game:mc"}


async def test_typing_in_game_chat_is_an_answer_somebody_reads(surface):
    chat = tool(surface, "mc_chat")
    assert chat.reaches
    await chat.handler(message="ciao marco")
    assert surface.client.calls == [("chat", {"message": "ciao marco"})]


def test_every_tool_talks_to_her_as_you(surface):
    """"She puts on armour" taught her there was a she doing it."""
    for t in surface.tools():
        found = THIRD_PERSON.findall(t.description)
        assert not found, f"{t.name}: {found} in {t.description!r}"


def test_the_instructions_are_about_her_playing():
    rules = Path("data/prompts/minecraft.md").read_text(encoding="utf-8")
    assert not re.search(r"\bbody\b", rules, re.IGNORECASE)
    # the survival guide the second agent used to keep to itself is hers now
    assert "go_to_surface" in rules and "crafting_plan" in rules


@pytest.mark.parametrize("scripts", [True, False])
def test_the_rules_only_name_tools_she_has(scripts):
    """A tool the prompt names and the schema lacks is a call she makes into nothing."""
    from src.core.mind.operating import unarmed

    s = make(build_scripts=scripts)
    s._registry = build_minecraft_tools(s.client, build_scripts=scripts)
    s.places = None
    mind = ["speak", "stay_silent", "objective_done", "objective_started"]
    armed = [t.name for t in s.tools()] + mind + ["remember_place", "go_to_place"]
    assert unarmed(s.context_section, armed) == []


def test_the_rules_are_in_her_context(surface):
    assert "go_to_surface" in surface.context_section


# --- what she is doing, in her own frame ---------------------------------------


async def test_she_sees_what_she_is_in_the_middle_of(surface):
    task = await start(surface, block="log", count=16)
    now = surface.live_state()
    assert "find_block" in now and "log" in now
    assert not THIRD_PERSON.search(now.replace("Bea", ""))
    await finish(surface, task)


async def test_when_it_is_over_she_is_not_doing_it_any_more(surface):
    task = await start(surface, block="log")
    await finish(surface, task)
    assert "find_block" not in surface.live_state().split("\n")[1]
    assert surface.doing is None


async def test_a_cancelled_action_is_not_still_going(surface):
    """She changed her mind: the old action is gone, not stuck in her frame."""
    task = await start(surface, block="log")
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert surface.doing is None


async def test_a_replaced_action_does_not_clear_the_one_that_replaced_it(surface):
    first = await start(surface, block="log")
    second = asyncio.create_task(tool(surface, "move_to").handler(x=1, y=64, z=1))
    await asyncio.sleep(0)
    first.cancel()
    await asyncio.gather(first, return_exceptions=True)
    assert surface.doing is not None and surface.doing.name == "move_to"
    await finish(surface, second)


def test_the_live_state_carries_the_game_and_her_places(surface):
    surface.places = types.SimpleNamespace(render=lambda *a: "home (10, 64, 3) 10m")
    now = surface.live_state()
    assert "health" in now.lower() and "home (10, 64, 3)" in now


async def test_a_build_reporting_in_is_what_she_reads_next(surface):
    task = await start(surface, "build_template", name="dirt_shelter", x=0, y=64, z=0)
    surface._on_mod_event("progress", {"type": "progress", "action": "build", "done": 10,
                                       "total": 48, "message": "building: 10 placed, 38 to go"})
    assert "10 placed, 38 to go" in surface.live_state()
    await finish(surface, task)


# --- standing around -----------------------------------------------------------


def test_standing_around_too_long_makes_her_do_something():
    s = make(plan=Plan("get wood"), idle_nudge_seconds=90)
    s._idle_since = time.time() - 100
    p = s._nudge()
    assert p is not None and "get wood" in p.content
    assert p.meta.get("addressed")


def test_she_is_nudged_with_no_plan_too():
    """With nothing on the list she is still a player standing in a field."""
    s = make(plan=Plan(), idle_nudge_seconds=90)
    s._idle_since = time.time() - 100
    assert s._nudge() is not None


def test_the_idle_nudge_waits_its_time():
    s = make(plan=Plan("get wood"), idle_nudge_seconds=90)
    s._idle_since = time.time() - 10
    assert s._nudge() is None


def test_the_idle_nudge_can_be_turned_off():
    s = make(plan=Plan("get wood"), idle_nudge_seconds=0)
    s._idle_since = time.time() - 1000
    assert s._nudge() is None


async def test_the_idle_clock_starts_when_her_hands_stop():
    s = make(plan=Plan("get wood"), idle_nudge_seconds=90)
    s._idle_since = time.time() - 1000
    task = await start(s, block="log")
    assert s._idle_nudge() is None
    await finish(s, task)
    assert time.time() - s._idle_since < 5


# --- saying something while she works ------------------------------------------


async def test_nothing_new_is_not_a_reason_to_talk():
    """Measured: five nudges in a row with the same stale line, while one
    find_block ran for two minutes. Every one of them became filler."""
    s = make(commentary_seconds=20)
    task = await start(s, block="log", count=16)
    s.doing.started -= 30
    s._last_commentary -= 30
    assert s._nudge() is None
    await finish(s, task)


async def test_something_changing_while_she_works_is():
    s = make(commentary_seconds=20)
    task = await start(s, block="log", count=16)
    s.doing.started -= 30
    s._last_commentary -= 30
    s.client.latest_state = state(oak_log=9)
    p = s._nudge()
    assert p is not None and "9 oak_log" in p.content and "find_block" in p.content
    assert not THIRD_PERSON.search(p.content)
    await finish(s, task)


async def test_the_same_change_is_only_worth_it_once():
    s = make(commentary_seconds=20)
    task = await start(s, block="log", count=16)
    s.doing.started -= 30
    s._last_commentary -= 30
    s.client.latest_state = state(oak_log=9)
    assert s._nudge() is not None
    s._last_commentary -= 30
    assert s._nudge() is None
    await finish(s, task)


async def test_commentary_keeps_its_distance():
    s = make(commentary_seconds=20)
    task = await start(s, block="log", count=16)
    s.client.latest_state = state(oak_log=9)
    assert s._nudge() is None
    await finish(s, task)


async def test_commentary_can_be_turned_off():
    s = make(commentary_seconds=0)
    task = await start(s, block="log", count=16)
    s.doing.started -= 300
    s._last_commentary -= 300
    s.client.latest_state = state(oak_log=9)
    assert s._nudge() is None
    await finish(s, task)


# --- asked from the dashboard ----------------------------------------------------


def test_asking_her_works_standing_still(surface):
    assert surface.ask_for_a_word()
    p = surface.bus.items[-1]
    assert p.meta.get("addressed") and not THIRD_PERSON.search(p.content)


async def test_asking_her_names_what_she_is_doing(surface):
    task = await start(surface, block="log")
    assert surface.ask_for_a_word()
    assert "find_block" in surface.bus.items[-1].content
    await finish(surface, task)


def test_asking_says_so_when_she_is_not_in_the_game(surface):
    surface.active = False
    assert not surface.ask_for_a_word()


# --- what the game does on its own ------------------------------------------------


def test_fighting_back_on_reflex_reaches_her(surface):
    surface._on_mod_event("reflex", {"type": "reflex", "reflex": "defend", "event": "started",
                                     "message": "defending against Zombie"})
    p = surface.bus.items[-1]
    assert "Zombie" in p.content and not THIRD_PERSON.search(p.content)


def test_eating_on_reflex_does_not_wake_her_but_she_knows(surface):
    surface._on_mod_event("reflex", {"type": "reflex", "reflex": "eat", "event": "started",
                                     "message": "eating: food was 13/20"})
    assert not surface.bus.items
    assert "eating: food was 13/20" in surface.live_state()


def test_losing_someone_she_followed_reaches_her(surface):
    surface._on_mod_event("activity", {"type": "activity", "action": "follow_player",
                                       "result": "FAILURE_LOST", "message": "lost Marco"})
    p = surface.bus.items[-1]
    assert "lost Marco" in p.content and not THIRD_PERSON.search(p.content)


def test_stopping_a_follow_herself_is_not_news(surface):
    surface._on_mod_event("activity", {"type": "activity", "action": "follow_player",
                                       "result": "INTERRUPTED", "message": "stopped following"})
    assert not surface.bus.items


def test_waking_up_in_the_game_is_hers(surface):
    surface._joined()
    assert not THIRD_PERSON.search(surface.bus.items[-1].content)


# --- the dashboard -----------------------------------------------------------------


async def test_the_dashboard_sees_what_she_is_doing(surface):
    task = await start(surface, block="log")
    snap = surface.snapshot()
    assert snap["active"] and snap["connected"]
    assert snap["doing"].startswith("find_block") and snap["elapsed"] >= 0
    await finish(surface, task)
    assert surface.snapshot()["doing"] == ""
    assert surface.snapshot()["last"].startswith("find_block")


async def test_the_dashboard_can_stop_her_hands(surface):
    assert await surface.stop_doing() is not None
    assert surface.client.calls[-1] == ("stop_moving", {})


# --- the skill coming up and going down ----------------------------------------------


class LiveClient(FakeClient):
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


async def test_the_skill_comes_up_with_her_hands_ready(monkeypatch, tmp_path):
    from src.core.skills.minecraft import surface as module
    from src.core.skills.minecraft.places import Places

    client = LiveClient()
    monkeypatch.setattr(module, "MinecraftClient", lambda *a, **k: client)
    monkeypatch.setattr(module, "Places", lambda: Places(tmp_path / "places.json"))
    skill = MinecraftSurface(Config(), bus=Bus(), expression=None,
                             context=types.SimpleNamespace(memory=None))
    skill.initialize()
    await skill.start()
    try:
        assert "find_block" in {t.name for t in skill.tools()}
        await asyncio.sleep(0.05)
        assert skill.bus.items and "Minecraft" in skill.bus.items[0].content
    finally:
        await skill.stop()
    assert client.stopped and skill.tools() == []


# --- and over http -------------------------------------------------------------------


@pytest.fixture
def api(surface):
    from fastapi.testclient import TestClient

    from src.core.brain import AIVtuberBrain
    from src.web import app as web
    from src.web import deps

    class BrainStub:
        def _surface(self, name):
            return surface if name == "game:mc" else None

        # borrowed, not reimplemented: a stub of its own would not notice the
        # day the surface stops being called "game:mc"
        ask_minecraft_for_a_word = AIVtuberBrain.ask_minecraft_for_a_word
        minecraft_now = AIVtuberBrain.minecraft_now
        stop_minecraft = AIVtuberBrain.stop_minecraft

    previous = deps.brain_instance
    deps.brain_instance = BrainStub()
    try:
        yield TestClient(web.app)
    finally:
        deps.brain_instance = previous


def test_the_dashboard_can_ask_her(api, surface):
    assert api.post("/minecraft/ask").status_code == 200
    assert surface.bus.items


def test_the_dashboard_reads_what_she_is_doing(api):
    body = api.get("/minecraft/now").json()
    assert body["active"] and body["doing"] == ""


def test_the_dashboard_stops_her_hands(api, surface):
    assert api.post("/minecraft/stop").status_code == 200
    assert surface.client.calls[-1] == ("stop_moving", {})


def test_the_dashboard_is_told_when_she_is_not_in_the_game(api, surface):
    """A button that silently does nothing is worse than one that says why."""
    surface.active = False
    assert api.post("/minecraft/ask").status_code == 409
    assert api.post("/minecraft/stop").status_code == 409
    assert api.get("/minecraft/now").json()["active"] is False


def test_there_is_no_goal_to_hand_her_any_more(api):
    assert api.post("/minecraft/goal", json={"goal": "x"}).status_code in (404, 405)


# --- a turn about the game that did nothing in it ----------------------------------


def game_turn(content="You are standing still in Minecraft."):
    from src.core.perception.types import Perception, PerceptionKind
    return Perception(PerceptionKind.GAME, "game:mc", content, salience=0.8)


def spoke():
    return {"tool": "speak", "result": "Spoken."}


def test_talking_with_empty_hands_leaves_something_undone(surface):
    undone = surface.left_undone([game_turn()], [spoke()])
    assert undone and "find_block" not in undone and not THIRD_PERSON.search(undone)


def test_starting_an_action_is_doing_something(surface):
    started = {"tool": "find_block", "result": "find_block started (running in the background…)"}
    assert surface.left_undone([game_turn()], [spoke(), started]) is None


def test_an_action_that_failed_to_start_is_not(surface):
    failed = {"tool": "find_block", "result": "ERROR: invalid arguments for 'find_block'"}
    assert surface.left_undone([game_turn()], [failed])


async def test_hands_already_busy_leave_nothing_undone(surface):
    task = await start(surface, block="log")
    assert surface.left_undone([game_turn()], [spoke()]) is None
    await finish(surface, task)


def test_someone_in_game_chat_counts_as_the_game(surface):
    from src.core.perception.types import Perception, PerceptionKind
    said = Perception(PerceptionKind.CHAT, "chat:mc", "[marco] (in game): ciao", salience=0.7)
    assert surface.left_undone([said], [spoke()])


def test_a_turn_about_something_else_is_not_the_games_business(surface):
    from src.core.perception.types import Perception, PerceptionKind
    telegram = Perception(PerceptionKind.CHAT, "chat:telegram", "ciao", salience=0.7)
    assert surface.left_undone([telegram], [spoke()]) is None


def test_keeping_quiet_is_not_choosing_to_stand_there(surface):
    """Silence answers the room, not the game: her hands are still empty."""
    assert surface.left_undone([game_turn()], [{"tool": "stay_silent", "result": "Staying silent."}])


def test_not_in_the_game_leaves_nothing_undone(surface):
    surface.active = False
    assert surface.left_undone([game_turn()], [spoke()]) is None


# --- the whole turn, the way it went wrong live ------------------------------------


async def test_a_turn_that_only_talked_about_chopping_ends_up_chopping():
    """14:57 live: "let me just start punching some birch logs", one speak, turn over."""
    from src.core.agent.types import AssistantMessage, ToolCall
    from src.core.attention.gate import Attention
    from src.core.consciousness import Consciousness
    from src.core.memory.store import MemoryStore
    from src.core.perception.bus import PerceptionBus
    from src.core.skills.base import SkillRegistry
    from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents

    class MindConfig:
        consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                         "burst_steps": 3, "correlation_timeout": 5.0, "stream_speech": False,
                         "turn_log": False, "window_persist_after_turn": False}
        attention = {"enabled": True, "trigger_words": ["bea"]}
        skills = {"minecraft": {"enabled": True}}
        language = ""

    game = make(plan=Plan("you need to get wood"))
    surfaces = SkillRegistry()
    surfaces.register(game)
    llm = FakeLLMClient(script=[
        AssistantMessage(tool_calls=[ToolCall(id="s", name="speak", arguments={
            "mood": "bored", "message": "let me just start punching some birch logs"})]),
        AssistantMessage(tool_calls=[ToolCall(id="f", name="find_block",
                                              arguments={"block": "birch_log", "count": 4})]),
        AssistantMessage(content="should not be asked"),
    ])
    config = MindConfig()
    m = Consciousness(
        config=config, llm=llm, bus=PerceptionBus(window=0.0), expression=FakeExpression(),
        surfaces=surfaces, history_manager=FakeHistory(), event_manager=RecordingEvents(),
        soul_getter=lambda: "soul", operating_getter=lambda: "rules",
        memory=MemoryStore(":memory:"), profiler=None, attention=Attention(config),
    )
    game.bus = m.bus
    game._idle_since = time.time() - 100
    await m._run_turn([game._nudge()])
    for _ in range(20):
        if ("find_block", {"block": "birch_log", "count": 4}) in game.client.calls:
            break
        await asyncio.sleep(0.01)
    assert ("find_block", {"block": "birch_log", "count": 4}) in game.client.calls
    assert llm.call_count == 2
