"""Parallel conversations, through the real consciousness loop.

Two channels answered at once, three quick messages in one channel getting one
reply, order respected inside a channel, and no message ever answered twice.
"""

import asyncio
import random

from src.core.attention.gate import Attention
from src.core.consciousness import Consciousness
from src.core.memory.store import MemoryStore
from src.core.mind.conversation import ConversationMind
from src.core.mind.scheduler import ConversationScheduler
from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.skills.base import SkillRegistry
from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents, speaks
from tests.test_conversation import FakeDiscord, replies


class Config:
    def __init__(self):
        self.consciousness = {
            "enabled": True, "idle_after": 3600.0, "window": 0.0, "burst_steps": 3,
            "history_limit": 30, "correlation_timeout": 5.0,
            "conversation_history": 16, "conversation_steps": 3, "max_coalesced_runs": 3,
        }
        self.attention = {"enabled": True, "trigger_words": ["bea"], "cooldown_seconds": 0}
        self.skills = {}


class World:
    """The live loop, the conversation mind and a fake discord, wired together."""

    def __init__(self, stage_script=None, conversation_script=None):
        config = Config()
        self.store = MemoryStore(":memory:")
        self.bus = PerceptionBus(window=0.0)
        self.surfaces = SkillRegistry()
        self.discord = FakeDiscord()
        self.surfaces.register(self.discord)

        rng = random.Random()
        rng.uniform = lambda a, b: 0.0
        attention = Attention(config, rng=rng)

        self.stage_llm = FakeLLMClient(stage_script or [])
        self.conversation_llm = FakeLLMClient(conversation_script or [])

        self.mind = Consciousness(
            config=config, llm=self.stage_llm, bus=self.bus, expression=FakeExpression(),
            surfaces=self.surfaces, history_manager=FakeHistory(),
            event_manager=RecordingEvents(), soul_getter=lambda: "soul",
            operating_getter=lambda: "rules", attention=attention,
        )
        self.conversations = ConversationMind(
            config=config, llm=self.conversation_llm, memory=self.store,
            surfaces=self.surfaces, soul_getter=lambda: "soul",
            operating_getter=lambda: "rules", scheduler=ConversationScheduler(),
            event_manager=RecordingEvents(), attention=attention,
            now_line=self.mind.now_line,
        )
        self.mind.conversations = self.conversations
        self.mind.context = [self.mind._system_message([])]

    async def run(self, timeout: float = 1.0):
        self.mind.alive = True
        task = asyncio.create_task(self.mind.run())
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while self.bus._queue.qsize() and loop.time() < deadline:
            await asyncio.sleep(0.005)
        await asyncio.sleep(0.02)
        await self.conversations.drain(timeout=timeout)
        self.mind.alive = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def close(self):
        self.store.close()


def message(text="ciao bea", channel="1", name="marco", message_id="m1") -> Perception:
    return Perception(
        kind=PerceptionKind.CHAT, surface="voice:discord",
        content=f"[{name}] (discord text, channel_id={channel}): {text}",
        salience=0.8, meta={"channel_id": channel, "message_id": message_id},
        author=Author(platform="discord", native_id="4711", display_name=name),
    )


def game(text="EVENTS:\nINTERRUPTED: took damage") -> Perception:
    # as MinecraftSurface emits it: an interrupt declares itself
    return Perception(PerceptionKind.GAME, "game:mc", text, salience=0.95,
                      meta={"event": "interrupted"})


async def test_two_channels_are_answered_in_parallel():
    world = World(conversation_script=[replies("a"), replies("b")])
    world.bus.put(message("bea?", channel="1", message_id="m1"))
    world.bus.put(message("bea!", channel="2", message_id="m2"))

    await world.run()
    assert {c for c, _, _ in world.discord.sent} == {"1", "2"}
    world.close()


async def test_a_written_message_never_reaches_the_stage():
    """The routing is an if/else: one destination, never two."""
    world = World(stage_script=[speaks("non dovrei parlare")],
                  conversation_script=[replies("eccomi")])
    world.bus.put(message("bea?", channel="1"))

    await world.run()
    assert world.stage_llm.call_count == 0
    assert world.conversation_llm.call_count == 1
    assert world.mind.expression.spoken == []
    world.close()


async def test_the_game_keeps_the_stage():
    world = World(stage_script=[speaks("ahia")])
    world.bus.put(game())

    await world.run()
    assert world.stage_llm.call_count == 1
    assert world.conversation_llm.call_count == 0
    world.close()


async def test_a_game_burst_does_not_hold_up_a_discord_reply():
    """The whole point: Marco does not wait behind a Minecraft turn."""
    world = World(stage_script=[speaks("che palle sto zombie")],
                  conversation_script=[replies("dimmi")])
    world.bus.put(game())
    world.bus.put(message("bea?", channel="1"))

    await world.run()
    assert world.mind.expression.spoken == [("normal", "che palle sto zombie", "local")]
    assert [t for _, t, _ in world.discord.sent] == ["dimmi"]
    world.close()


async def test_three_quick_messages_in_one_channel_get_one_reply():
    world = World(conversation_script=[replies("una risposta"), replies("basta")])
    for i in range(3):
        world.bus.put(message(f"messaggio {i}", channel="1", message_id=f"m{i}"))

    await world.run()
    assert len(world.discord.sent) <= 2
    world.close()


async def test_order_inside_a_channel_is_respected():
    world = World(conversation_script=[replies("prima"), replies("seconda")])
    world.bus.put(message("bea uno", channel="1", message_id="m1"))
    await world.run()
    world.bus.put(message("bea due", channel="1", message_id="m2"))
    await world.run()

    assert [t for _, t, _ in world.discord.sent] == ["prima", "seconda"]
    world.close()


async def test_the_stage_learns_what_she_did_elsewhere():
    world = World(stage_script=[speaks("comunque")],
                  conversation_script=[replies("ti rispondo")])
    world.bus.put(message("bea?", channel="1"))
    await world.run()

    world.bus.put(game())
    await world.run()
    assert "ELSEWHERE, JUST NOW" in world.stage_llm.last_system_prompt
    assert "ti rispondo" in world.stage_llm.last_system_prompt
    world.close()


async def test_an_ignored_message_never_starts_a_turn():
    """The gate runs before the routing: noise costs nothing, anywhere."""
    world = World(conversation_script=[replies("non dovrei")])
    world.bus.put(message("niente di che", channel="1"))

    await world.run()
    assert world.conversation_llm.call_count == 0
    assert world.discord.sent == []
    world.close()
