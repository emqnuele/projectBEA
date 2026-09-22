"""The prompt and the schema say the same thing, or the log says so."""

from src.core.mind.operating import promised_tools, unarmed


def test_a_tool_named_in_prose_is_found():
    assert promised_tools("call `discord_leave_voice` when you are bored") == \
        ["discord_leave_voice"]


def test_a_call_with_arguments_is_found_by_its_name():
    assert promised_tools("`objective_done(objective, how)` when it is finished") == \
        ["objective_done"]


def test_the_two_the_mind_always_has_are_recognised():
    assert promised_tools("`speak` is your voice; `react` instead of writing") == \
        ["speak", "react"]


def test_ordinary_prose_names_no_tools():
    assert promised_tools("Keep spoken lines short and punchy — quips, not paragraphs.") == []


def test_a_word_without_backticks_is_prose():
    assert promised_tools("you can speak or stay silent") == []


def test_each_tool_is_reported_once():
    assert promised_tools("`send_message` here, and `send_message` there") == ["send_message"]


def test_a_promise_the_schema_keeps_is_not_reported():
    assert unarmed("call `speak`", ["speak", "stay_silent"]) == []


def test_a_promise_the_schema_does_not_keep_is_reported():
    assert unarmed("call `discord_leave_voice`", ["speak"]) == ["discord_leave_voice"]


def test_every_skill_section_agrees_with_the_toolbox_it_is_shipped_with():
    """The check that would have caught it: a section describing a door she is
    not given is always a bug, whatever state the world is in."""
    import types

    from src.core.memory.store import MemoryStore
    from src.core.mind.tools import MindTools
    from src.core.skills.base import SkillRegistry
    from src.core.skills.plan.surface import StreamPlanSkill
    from src.core.skills.voice.surface import VoiceSurface

    class Cfg:
        skills = {"discord": {"enabled": True}}
        attention: dict = {}

    class Transport:
        async def leave_voice(self):
            return {"ok": True}

    store = MemoryStore(":memory:")
    context = types.SimpleNamespace(memory=store, event_manager=None)

    voice = VoiceSurface(Cfg(), bus=None, expression=None, context=context)
    voice.initialize()
    voice.transport = Transport()
    voice.active = True
    plan = StreamPlanSkill(Cfg(), bus=None, expression=None, context=context)
    plan.active = True

    registry = SkillRegistry()
    registry.register(voice)
    registry.register(plan)
    box = MindTools(registry, speak=lambda **k: "", stay_silent=lambda **k: "",
                    send_text=lambda **k: "", react_to=lambda **k: "",
                    say_nothing=lambda **k: "")

    # the world moves mid-session: she is pulled into a call, the owner writes a plan
    voice.channel.on_message({"type": "joined", "channel_id": "vc1", "listeners": 2})
    store.plan.set_directive("build a house")
    store.plan.add("get 64 logs")

    promised = "\n".join(registry.context_sections())
    assert unarmed(promised, box.names()) == []
