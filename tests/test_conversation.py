"""A scoped conversation turn: its context, its tools, and what it must not have."""

import pytest

from src.core.agent.types import AssistantMessage, ToolCall
from src.core.memory.store import MemoryStore
from src.core.mind.conversation import ConversationMind
from src.core.mind.scheduler import ConversationScheduler
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import Skill, SkillRegistry
from tests.fakes import FakeLLMClient, RecordingEvents


class Config:
    def __init__(self, **overrides):
        self.consciousness = {"conversation_history": 16, "conversation_steps": 3}
        self.consciousness.update(overrides)
        self.skills = {}


class FakeDiscord(Skill):
    """Stands in for VoiceSurface: records what she sent, exposes scoped tools."""

    name = "voice:discord"
    platform = "discord"
    skill_name = "discord"

    def __init__(self):
        super().__init__(config=Config(), bus=None, expression=None)
        self.active = True
        self.sent = []
        self.reactions = []

    def conversation_tools(self, channel_id, reply_to=None):
        from src.core.agent.tools import Tool
        if not channel_id:
            return []
        tools = [Tool(
            "send_message", "write here",
            {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
            lambda text: self._send(channel_id, text),
        )]
        if reply_to:
            tools.append(Tool(
                "reply", "answer directly",
                {"type": "object", "properties": {"text": {"type": "string"}},
                 "required": ["text"]},
                lambda text: self._send(channel_id, text, reply_to),
            ))
            tools.append(Tool(
                "react", "react with an emoji",
                {"type": "object", "properties": {"emoji": {"type": "string"}},
                 "required": ["emoji"]},
                lambda emoji: self._react(emoji),
            ))
        return tools

    def tools(self):
        return []

    async def _send(self, channel_id, text, reply_to=None):
        self.sent.append((channel_id, text, reply_to))
        return "Sent (1 message(s))."

    async def _react(self, emoji):
        self.reactions.append(emoji)
        return "Reacted."


@pytest.fixture
def setup():
    store = MemoryStore(":memory:")
    surfaces = SkillRegistry()
    discord = FakeDiscord()
    surfaces.register(discord)
    yield store, surfaces, discord
    store.close()


def build(setup, llm, now_line="", **kwargs):
    store, surfaces, _ = setup
    return ConversationMind(
        config=Config(), llm=llm, memory=store, surfaces=surfaces,
        soul_getter=lambda: "you are bea",
        operating_getter=lambda: "you speak with tools",
        scheduler=ConversationScheduler(), event_manager=RecordingEvents(),
        now_line=lambda: now_line, **kwargs,
    )


def message(text="ciao bea", name="marco", channel="123", message_id="m1") -> Perception:
    return Perception(
        kind=PerceptionKind.CHAT, surface="voice:discord",
        content=f"[{name}] (discord text, channel_id={channel}): {text}",
        salience=0.8,
        meta={"channel_id": channel, "message_id": message_id},
        author=Author(platform="discord", native_id="4711", display_name=name),
    )


def replies(text="eccomi", tool="reply") -> AssistantMessage:
    return AssistantMessage(tool_calls=[
        ToolCall(id="c1", name=tool, arguments={"text": text})
    ])


# --- the turn ---------------------------------------------------------------


async def test_she_answers_in_the_right_channel(setup):
    _, _, discord = setup
    mind = build(setup, FakeLLMClient([replies("che vuoi")]))
    await mind.turn_now("discord:123", [message()])
    assert discord.sent == [("123", "che vuoi", "m1")]


async def test_what_she_sent_is_recorded_as_history(setup):
    store, _, _ = setup
    mind = build(setup, FakeLLMClient([replies("che vuoi")]))
    await mind.turn_now("discord:123", [message("ciao bea")])

    history = store.conversations.history("discord:123")
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "ciao bea"), ("bea", "che vuoi")
    ]


async def test_the_routing_prefix_is_not_stored(setup):
    """The history is per-channel and already carries the author: repeating the
    ids on every line is noise the model would learn to imitate."""
    store, _, _ = setup
    mind = build(setup, FakeLLMClient([replies()]))
    await mind.turn_now("discord:123", [message("ciao bea")])
    assert store.conversations.history("discord:123")[0]["content"] == "ciao bea"


async def test_she_can_choose_to_say_nothing(setup):
    _, _, discord = setup
    silence = AssistantMessage(tool_calls=[ToolCall(id="c", name="say_nothing", arguments={})])
    mind = build(setup, FakeLLMClient([silence]))
    await mind.turn_now("discord:123", [message()])
    assert discord.sent == []


async def test_she_can_react_instead_of_writing(setup):
    _, _, discord = setup
    react = AssistantMessage(tool_calls=[ToolCall(id="c", name="react", arguments={"emoji": "💀"})])
    mind = build(setup, FakeLLMClient([react, replies("ok")]))
    await mind.turn_now("discord:123", [message()])
    assert discord.reactions == ["💀"]


async def test_a_turn_with_nothing_to_answer_does_nothing(setup):
    llm = FakeLLMClient()
    mind = build(setup, llm)
    await mind.turn("discord:123", first=True)
    assert llm.call_count == 0


# --- what a scoped turn must NOT have ---------------------------------------


async def test_there_is_no_speak_tool(setup):
    """Answering a written message out loud was a real failure mode. A rule in
    the prompt is something a model can ignore; a missing tool is not."""
    llm = FakeLLMClient([replies()])
    mind = build(setup, llm)
    await mind.turn_now("discord:123", [message()])
    assert "speak" not in llm.tools_seen[0]


async def test_there_are_no_body_actions(setup):
    llm = FakeLLMClient([replies()])
    mind = build(setup, llm)
    await mind.turn_now("discord:123", [message()])
    assert not any(name.startswith("mc_") or name == "play_minecraft"
                   for name in llm.tools_seen[0])


async def test_the_channel_is_context_not_an_argument(setup):
    """She is talking in one place: she should not have to name it every time."""
    llm = FakeLLMClient([replies()])
    mind = build(setup, llm)
    await mind.turn_now("discord:123", [message()])
    assert set(llm.tools_seen[0]) == {"reply", "send_message", "react", "say_nothing"}


# --- context ----------------------------------------------------------------


async def test_the_context_carries_her_soul(setup):
    llm = FakeLLMClient([replies()])
    await build(setup, llm).turn_now("discord:123", [message()])
    assert "you are bea" in llm.last_system_prompt


async def test_the_context_is_not_the_live_loops(setup):
    llm = FakeLLMClient([replies()])
    await build(setup, llm).turn_now("discord:123", [message()])
    assert "THIS IS A WRITTEN CONVERSATION" in llm.last_system_prompt


async def test_she_knows_who_she_is_talking_to(setup):
    store, _, _ = setup
    entry = store.roster.record(identity="discord:4711", display_name="marco",
                                platform="discord")
    card = store.people.create_from_entry(entry, reason="a regular")
    store.roster.set_promoted("discord:4711", card.person_id)
    store.people.add_fact(card.person_id, "gioca sempre a minecraft")

    llm = FakeLLMClient([replies()])
    await build(setup, llm).turn_now("discord:123", [message()])
    assert "WHO YOU'RE TALKING TO" in llm.last_system_prompt
    assert "gioca sempre a minecraft" in llm.last_system_prompt


async def test_the_rolling_summary_is_included(setup):
    store, _, _ = setup
    store.conversations.save_summary("discord:123", "parlano sempre di macchine")
    llm = FakeLLMClient([replies()])
    await build(setup, llm).turn_now("discord:123", [message()])
    assert "parlano sempre di macchine" in llm.last_system_prompt


async def test_she_knows_what_she_is_doing_on_stage(setup):
    llm = FakeLLMClient([replies()])
    mind = build(setup, llm, now_line="you're in Minecraft")
    await mind.turn_now("discord:123", [message()])
    assert "you're in Minecraft" in llm.last_system_prompt


async def test_cross_awareness_is_one_line_not_a_context_transfer(setup):
    llm = FakeLLMClient([replies()])
    mind = build(setup, llm, now_line="you're in Minecraft")
    await mind.turn_now("discord:123", [message()])
    block = llm.last_system_prompt.split("[WHAT YOU'RE DOING RIGHT NOW]")[1]
    assert len(block.strip().splitlines()) == 1


async def test_past_messages_of_that_channel_are_replayed(setup):
    store, _, _ = setup
    store.conversations.add(conversation_key="discord:123", role="user",
                            content="prima cosa", display_name="marco")
    store.conversations.add(conversation_key="discord:123", role="bea", content="mia risposta")

    llm = FakeLLMClient([replies()])
    await build(setup, llm).turn_now("discord:123", [message()])
    roles = [m["role"] for m in llm.calls[0]]
    contents = [m["content"] for m in llm.calls[0]]
    assert roles == ["system", "user", "assistant", "user"]
    assert "prima cosa" in contents[1] and contents[2] == "mia risposta"


async def test_another_channels_history_never_leaks_in(setup):
    store, _, _ = setup
    store.conversations.add(conversation_key="discord:999", role="user",
                            content="segreto di un altro canale", display_name="luca")
    llm = FakeLLMClient([replies()])
    await build(setup, llm).turn_now("discord:123", [message()])
    assert "segreto di un altro canale" not in str(llm.calls[0])


async def test_a_coalescing_rerun_says_so(setup):
    llm = FakeLLMClient([replies()])
    mind = build(setup, llm)
    mind._pending["discord:123"] = [message()]
    await mind.turn("discord:123", first=False)
    assert "MORE ARRIVED WHILE YOU WERE WRITING" in str(llm.calls[0][-1])


# --- cross-awareness back to the live loop ----------------------------------


async def test_the_live_loop_learns_what_she_did_elsewhere(setup):
    mind = build(setup, FakeLLMClient([replies("che vuoi")]))
    await mind.turn_now("discord:123", [message()])
    lines = mind.recent_lines()
    assert "ELSEWHERE, JUST NOW" in lines and "che vuoi" in lines


async def test_those_lines_are_consumed_once(setup):
    mind = build(setup, FakeLLMClient([replies()]))
    await mind.turn_now("discord:123", [message()])
    assert mind.recent_lines() != ""
    assert mind.recent_lines() == ""


async def test_nothing_happened_means_no_line(setup):
    assert build(setup, FakeLLMClient()).recent_lines() == ""


# --- concurrency ------------------------------------------------------------


async def test_two_channels_are_answered_in_parallel(setup):
    _, _, discord = setup
    mind = build(setup, FakeLLMClient([replies("a"), replies("b")]))
    mind.dispatch("discord:1", [message(channel="1", message_id="m1")])
    mind.dispatch("discord:2", [message(channel="2", message_id="m2")])
    await mind.drain(timeout=2.0)
    assert {c for c, _, _ in discord.sent} == {"1", "2"}


async def test_three_quick_messages_get_one_answer(setup):
    _, _, discord = setup
    mind = build(setup, FakeLLMClient([replies("una risposta"), replies("e basta")]))
    for i in range(3):
        mind.dispatch("discord:1", [message(f"msg {i}", channel="1", message_id=f"m{i}")])
    await mind.drain(timeout=2.0)
    assert len(discord.sent) <= 2
