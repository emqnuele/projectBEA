"""The two concerns lifted out of the mind: waiting callers, and the toolbox."""

from src.core.agent.messages import assistant_to_message, tool_result_message
from src.core.agent.tools import Tool
from src.core.agent.types import AssistantMessage, ToolCall
from src.core.mind.correlation import CorrelationRegistry
from src.core.mind.tools import MindTools
from src.core.perception.types import Perception, PerceptionKind


def waiting(cid: str) -> Perception:
    return Perception(PerceptionKind.CHAT, "chat:ui", "ciao", salience=0.8,
                      meta={"correlation_id": cid})


# --- correlation ------------------------------------------------------------


async def test_a_caller_is_answered():
    registry = CorrelationRegistry()
    cid, future = registry.register("local")
    registry.start_batch([waiting(cid)])
    registry.resolve(lambda r: True, {"mood": "normal", "message": "eccomi"})
    assert future.result()["message"] == "eccomi"


async def test_a_caller_is_always_freed_even_when_ignored():
    """Silence is an answer; a hang is a bug."""
    registry = CorrelationRegistry()
    cid, future = registry.register("local")
    registry.start_batch([waiting(cid)])
    registry.release()
    assert future.result() == {"mood": "normal", "message": ""}


async def test_a_discord_caller_gets_the_shape_it_expects():
    registry = CorrelationRegistry()
    cid, future = registry.register("discord")
    registry.start_batch([waiting(cid)])
    registry.release()
    assert future.result() == {"status": "ignored", "text": "", "audio": b""}


async def test_only_the_matching_route_is_answered():
    registry = CorrelationRegistry()
    local_cid, local = registry.register("local")
    discord_cid, discord = registry.register("discord")
    registry.start_batch([waiting(local_cid), waiting(discord_cid)])

    registry.resolve(lambda r: r == "discord", {"status": "success"})
    assert discord.done() and not local.done()


async def test_the_routes_of_the_batch_are_reported():
    registry = CorrelationRegistry()
    a, _ = registry.register("local")
    b, _ = registry.register("discord")
    registry.start_batch([waiting(a), waiting(b)])
    assert registry.routes == {"local", "discord"}


async def test_a_caller_arriving_mid_turn_is_picked_up():
    registry = CorrelationRegistry()
    first, _ = registry.register("local")
    registry.start_batch([waiting(first)])
    second, future = registry.register("local")
    registry.extend_batch([waiting(second)])

    registry.release()
    assert future.done()


async def test_answering_twice_does_not_raise():
    registry = CorrelationRegistry()
    cid, future = registry.register("local")
    registry.start_batch([waiting(cid)])
    registry.resolve(lambda r: True, {"message": "uno"})
    registry.release()
    assert future.result() == {"message": "uno"}


async def test_a_perception_nobody_waits_on_is_ignored():
    registry = CorrelationRegistry()
    assert registry.start_batch([waiting("never-registered")]) == []


# --- the toolbox ------------------------------------------------------------


class Skills:
    def __init__(self, *skills):
        self._skills = list(skills)

    def active(self):
        return [s for s in self._skills if s.active]

    def tools(self):
        out = []
        for s in self.active():
            out.extend(s.tools())
        return out


class Capability:
    def __init__(self, name, tool_names, active=True):
        self.name = name
        self.active = active
        self._tool_names = tool_names

    def tools(self):
        return [Tool(n, "does a thing", {"type": "object", "properties": {}}, lambda: "ok")
                for n in self._tool_names]


def toolbox(*skills) -> MindTools:
    return MindTools(Skills(*skills), speak=lambda **k: "spoken",
                     stay_silent=lambda **k: "silent")


def test_the_mind_always_has_its_own_two():
    names = {t.name for t in toolbox().registry().tools()}
    assert names == {"speak", "stay_silent"}


def test_active_capabilities_add_their_tools():
    box = toolbox(Capability("discord", ["discord_reply"]))
    assert "discord_reply" in {t.name for t in box.registry().tools()}


def test_an_inactive_capability_is_disarmed():
    box = toolbox(Capability("discord", ["discord_reply"], active=False))
    assert "discord_reply" not in {t.name for t in box.registry().tools()}


def test_the_registry_is_built_once_not_twice_per_step():
    """It used to be rebuilt on every schema lookup AND every dispatch."""
    box = toolbox(Capability("discord", ["discord_reply"]))
    assert box.registry() is box.registry()
    assert box.registry() is box.registry()


def test_toggling_a_capability_rebuilds_it():
    capability = Capability("discord", ["discord_reply"])
    box = toolbox(capability)
    first = box.registry()

    capability.active = False
    box.invalidate()
    assert box.registry() is not first
    assert "discord_reply" not in {t.name for t in box.registry().tools()}


def test_the_cache_notices_a_changed_capability_set_on_its_own():
    capability = Capability("discord", ["discord_reply"])
    box = toolbox(capability)
    box.registry()
    capability.active = False
    assert "discord_reply" not in {t.name for t in box.registry().tools()}


def test_schemas_carry_every_armed_tool():
    box = toolbox(Capability("discord", ["discord_reply"]))
    names = {s["function"]["name"] for s in box.schemas()}
    assert names == {"speak", "stay_silent", "discord_reply"}


# --- message serialization --------------------------------------------------


def test_a_plain_answer_serializes():
    assert assistant_to_message(AssistantMessage(content="ciao")) == \
        {"role": "assistant", "content": "ciao"}


def test_an_empty_answer_still_has_content():
    assert assistant_to_message(AssistantMessage())["content"] == ""


def test_tool_calls_are_serialized_as_the_api_expects():
    msg = AssistantMessage(tool_calls=[ToolCall("c1", "speak", {"mood": "normal"})])
    out = assistant_to_message(msg)
    assert out["tool_calls"][0]["function"]["name"] == "speak"
    assert out["tool_calls"][0]["function"]["arguments"] == '{"mood": "normal"}'
    assert out["tool_calls"][0]["type"] == "function"


def test_a_tool_result_is_addressed_to_its_call():
    out = tool_result_message(ToolCall("c1", "speak", {}), "Spoken.")
    assert out == {"role": "tool", "tool_call_id": "c1", "name": "speak",
                   "content": "Spoken."}
