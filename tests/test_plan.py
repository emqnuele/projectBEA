"""The owner's plan: what she is told to do, and what makes her do it.

The nudge is the part that matters. Without it Bea reacts and never acts: the
game heartbeat is noise, so nothing on a quiet server ever wakes her up.
"""

import asyncio
import time

import pytest

from src.core.agent.types import AssistantMessage, ToolCall
from src.core.attention.gate import Attention
from src.core.attention.types import Reaction
from src.core.consciousness import Consciousness
from src.core.memory.plan import DONE, StreamPlan
from src.core.memory.store import MemoryStore
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import PerceptionKind
from src.core.skills.base import SkillRegistry
from src.core.skills.minecraft.surface import MinecraftSurface
from src.core.skills.plan.surface import StreamPlanSkill
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents


@pytest.fixture
def plan() -> StreamPlan:
    return MemoryStore(":memory:").plan


class Config:
    def __init__(self, **skills):
        self.skills = skills
        self.attention = {}
        self.consciousness = {}


class Context:
    def __init__(self, memory):
        self.memory = memory


# --- the store ---------------------------------------------------------------


def test_an_empty_plan_renders_nothing(plan):
    assert plan.render() == ""


def test_the_directive_survives_a_read(plan):
    plan.set_directive("today you play minecraft")
    assert plan.directive == "today you play minecraft"
    assert "today you play minecraft" in plan.render()


def test_objectives_keep_the_order_they_were_added(plan):
    for text in ("first", "second", "third"):
        plan.add(text)
    assert [o.text for o in plan.all()] == ["first", "second", "third"]


def test_an_objective_needs_text(plan):
    assert plan.add("   ") is None
    assert plan.all() == []


def test_closing_an_objective_takes_it_off_the_open_list(plan):
    a = plan.add("build a base")
    plan.add("find diamonds")
    plan.update(a.id, status=DONE, outcome="it's ugly")

    assert [o.text for o in plan.open()] == ["find diamonds"]
    assert "it's ugly" in plan.render()


def test_an_unknown_status_is_refused(plan):
    objective = plan.add("build a base")
    with pytest.raises(ValueError):
        plan.update(objective.id, status="vibing")


def test_updating_a_missing_objective_returns_none(plan):
    assert plan.update(999, status=DONE) is None


def test_reorder_moves_the_objectives(plan):
    a, b = plan.add("first"), plan.add("second")
    plan.reorder([b.id, a.id])
    assert [o.text for o in plan.all()] == ["second", "first"]


def test_clearing_starts_an_empty_stream(plan):
    plan.set_directive("today you play minecraft")
    plan.add("build a base")
    plan.clear()
    assert plan.render() == ""


def test_the_number_shown_is_the_number_she_types(plan):
    objective = plan.add("build a base")
    assert f"#{objective.id} build a base" in plan.render()


# --- the skill ---------------------------------------------------------------


def skill(memory) -> StreamPlanSkill:
    s = StreamPlanSkill(Config(), PerceptionBus(), None, Context(memory))
    s.initialize()
    s.active = True
    return s


def test_no_plan_means_no_rules_and_no_tools():
    memory = MemoryStore(":memory:")
    s = skill(memory)
    assert s.context_section is None
    assert s.tools() == []
    assert s.live_state() is None


def test_a_plan_arms_the_objective_tools():
    memory = MemoryStore(":memory:")
    memory.plan.add("build a base")
    s = skill(memory)

    assert s.context_section is not None
    assert {t.name for t in s.tools()} == {
        "objective_started", "objective_done", "objective_dropped",
    }


def test_she_can_tick_an_objective_off():
    memory = MemoryStore(":memory:")
    objective = memory.plan.add("build a base")
    s = skill(memory)

    tools = {t.name: t for t in s.tools()}
    observation = tools["objective_done"].handler(objective=objective.id, how="done, badly")

    assert "last one" in observation
    assert memory.plan.get(objective.id).status == DONE
    assert memory.plan.get(objective.id).outcome == "done, badly"


def test_a_made_up_objective_number_fails_cleanly():
    memory = MemoryStore(":memory:")
    memory.plan.add("build a base")
    s = skill(memory)

    tools = {t.name: t for t in s.tools()}
    assert "FAILED" in tools["objective_done"].handler(objective=42)


# --- the nudge ---------------------------------------------------------------


class IdleAgent:
    busy = False

    def describe(self):
        return ""


class BusyAgent:
    busy = True

    def describe(self):
        return "working on: something"


def minecraft(memory, agent, nudge_seconds=90) -> MinecraftSurface:
    config = Config(minecraft={"enabled": True, "idle_nudge_seconds": nudge_seconds})
    surface = MinecraftSurface(config, PerceptionBus(), None, Context(memory))
    surface.initialize()
    surface.agent = agent
    surface.active = True
    return surface


def test_no_nudge_without_a_plan():
    surface = minecraft(MemoryStore(":memory:"), IdleAgent())
    assert surface._idle_nudge() is None


def test_no_nudge_while_the_body_is_working():
    memory = MemoryStore(":memory:")
    memory.plan.add("build a base")
    surface = minecraft(memory, BusyAgent())
    assert surface._idle_nudge() is None


def test_a_standing_body_with_a_plan_gets_nudged():
    memory = MemoryStore(":memory:")
    memory.plan.add("build a base")
    surface = minecraft(memory, IdleAgent())
    # idle for longer than the threshold
    surface._idle_since = time.time() - 200

    nudge = surface._idle_nudge()
    assert nudge is not None
    assert "build a base" in nudge.content
    assert nudge.meta["addressed"] == "idle-body"


def test_the_nudge_does_not_repeat_every_heartbeat():
    memory = MemoryStore(":memory:")
    memory.plan.add("build a base")
    surface = minecraft(memory, IdleAgent())
    surface._idle_since = time.time() - 200

    assert surface._idle_nudge() is not None
    assert surface._idle_nudge() is None


def test_the_nudge_can_be_turned_off():
    memory = MemoryStore(":memory:")
    memory.plan.add("build a base")
    surface = minecraft(memory, IdleAgent(), nudge_seconds=0)
    surface._idle_since = time.time() - 5000
    assert surface._idle_nudge() is None


def test_a_finished_plan_stops_the_nudging():
    memory = MemoryStore(":memory:")
    objective = memory.plan.add("build a base")
    memory.plan.update(objective.id, status=DONE)
    surface = minecraft(memory, IdleAgent())
    surface._idle_since = time.time() - 200
    assert surface._idle_nudge() is None


def test_the_gate_always_wakes_her_for_the_nudge():
    """A nudge the attention gate files under "noticed" is a nudge that never
    happened — she would go straight back to waiting to be spoken to."""
    memory = MemoryStore(":memory:")
    memory.plan.add("build a base")
    surface = minecraft(memory, IdleAgent())
    surface._idle_since = time.time() - 200
    nudge = surface._idle_nudge()

    gate = Attention(Config())
    gate.mark_spoke()  # she has just spoken: the cooldown would normally apply
    react, noted = gate.judge([nudge])

    assert react == [nudge] and noted == []


# --- what the mind sees ------------------------------------------------------


def test_the_plan_is_live_state_not_a_perception():
    """It is what she is supposed to be doing, always true — not an event."""
    memory = MemoryStore(":memory:")
    memory.plan.set_directive("today you play minecraft")
    s = skill(memory)
    assert "TODAY'S PLAN" in s.live_state()


def test_closing_an_objective_reports_how_many_are_left():
    memory = MemoryStore(":memory:")
    first = memory.plan.add("build a base")
    memory.plan.add("find diamonds")
    s = skill(memory)

    tools = {t.name: t for t in s.tools()}
    observation = tools["objective_done"].handler(objective=first.id, how="ok")
    assert "1 left" in observation


def test_a_nudge_is_a_game_perception_on_the_stage():
    memory = MemoryStore(":memory:")
    memory.plan.add("build a base")
    surface = minecraft(memory, IdleAgent())
    surface._idle_since = time.time() - 200

    nudge = surface._idle_nudge()
    assert nudge.kind is PerceptionKind.GAME
    assert nudge.surface == "game:mc"


def test_the_gate_reports_why_it_woke_her():
    memory = MemoryStore(":memory:")
    memory.plan.add("build a base")
    surface = minecraft(memory, IdleAgent())
    surface._idle_since = time.time() - 200

    gate = Attention(Config())
    verdict = gate._judge_one(surface._idle_nudge())
    assert verdict.reaction is Reaction.REACT
    assert verdict.reason == "addressed:idle-body"


def test_an_objective_tool_call_round_trips_through_the_registry():
    """The model calls these by name with `objective`, so the schema must match."""
    memory = MemoryStore(":memory:")
    objective = memory.plan.add("build a base")
    s = skill(memory)
    tool = next(t for t in s.tools() if t.name == "objective_done")

    call = ToolCall(id="c1", name="objective_done",
                    arguments={"objective": objective.id, "how": "fine"})
    assert set(call.arguments) <= set(tool.parameters["properties"])


# --- through the real loop ---------------------------------------------------


async def test_the_nudge_reaches_the_mind_with_the_plan_in_hand():
    """The whole point, end to end: a standing body and an open plan wake her
    up on their own, with the plan and the objective tools already in front of
    her, and nobody having said a word."""
    memory = MemoryStore(":memory:")
    memory.plan.set_directive("today you play minecraft")
    memory.plan.add("build a base")

    surfaces = SkillRegistry()
    surfaces.register(skill(memory))
    mc = minecraft(memory, IdleAgent())
    surfaces.register(mc)

    llm = FakeLLMClient([AssistantMessage(content="fine, I'll do it")])
    config = Config(minecraft={"enabled": True})
    config.attention = {"enabled": True, "cooldown_seconds": 20, "trigger_words": ["bea"]}
    bus = PerceptionBus(window=0.0)

    mind = Consciousness(
        config=config, llm=llm, bus=bus, expression=FakeExpression(),
        surfaces=surfaces, history_manager=FakeHistory(), event_manager=RecordingEvents(),
        soul_getter=lambda: "you are bea", operating_getter=lambda: "call speak to talk",
        attention=Attention(config),
    )
    mind.context = [mind._system_message([])]

    mc._idle_since = time.time() - 200
    bus.put(mc._idle_nudge())

    mind.alive = True
    task = asyncio.create_task(mind.run())
    for _ in range(50):
        await asyncio.sleep(0.005)
        if llm.calls:
            break
    mind.alive = False
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert llm.calls, "the nudge never reached the mind"
    assert "TODAY'S PLAN" in llm.last_system_prompt
    assert "build a base" in llm.last_system_prompt
    assert "objective_done" in llm.tools_seen[-1]


# --- the dashboard endpoints -------------------------------------------------


@pytest.fixture
def client():
    """The plan API against a brain stub: only `plan` and `plan_changed` are used."""
    from fastapi.testclient import TestClient

    from src.web import app as web

    class BrainStub:
        def __init__(self):
            self.memory = MemoryStore(":memory:")
            self.invalidations = 0

        @property
        def plan(self):
            return self.memory.plan

        def plan_changed(self):
            self.invalidations += 1

    stub = BrainStub()
    previous = web.brain_instance
    web.brain_instance = stub
    try:
        yield TestClient(web.app), stub
    finally:
        web.brain_instance = previous


def test_the_plan_starts_empty(client):
    api, _ = client
    assert api.get("/plan").json() == {"directive": "", "objectives": []}


def test_the_owner_writes_the_directive(client):
    api, stub = client
    body = api.post("/plan/directive", json={"text": "today you play minecraft"}).json()
    assert body["directive"] == "today you play minecraft"
    assert stub.invalidations == 1


def test_adding_an_objective_returns_the_whole_plan(client):
    api, _ = client
    body = api.post("/plan/objectives", json={"text": "build a base"}).json()
    assert [o["text"] for o in body["objectives"]] == ["build a base"]


def test_an_empty_objective_is_refused(client):
    api, _ = client
    assert api.post("/plan/objectives", json={"text": "   "}).status_code == 422


def test_an_unknown_status_is_refused_over_http(client):
    api, _ = client
    objective = api.post("/plan/objectives", json={"text": "build a base"}).json()["objectives"][0]
    assert api.patch(f"/plan/objectives/{objective['id']}",
                     json={"status": "vibing"}).status_code == 422


def test_the_owner_can_close_an_objective_herself(client):
    api, _ = client
    objective = api.post("/plan/objectives", json={"text": "build a base"}).json()["objectives"][0]
    body = api.patch(f"/plan/objectives/{objective['id']}", json={"status": "done"}).json()
    assert body["objectives"][0]["status"] == "done"


def test_deleting_a_missing_objective_is_a_404(client):
    api, _ = client
    assert api.delete("/plan/objectives/999").status_code == 404


def test_resetting_empties_the_plan(client):
    api, _ = client
    api.post("/plan/directive", json={"text": "today you play minecraft"})
    api.post("/plan/objectives", json={"text": "build a base"})
    assert api.post("/plan/reset").json() == {"directive": "", "objectives": []}
