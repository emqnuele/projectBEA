"""She is a streamer, and a streamer who goes quiet is broken.

The game heartbeats every few seconds, and the heartbeat was keeping the idle
timer permanently reset, so with Minecraft on she could never notice a silence
at all. What breaks the silences inside the game is the skill's own business
(`test_minecraft_playing.py`).
"""

import asyncio

from src.core.perception.bus import PerceptionBus
from src.core.perception.types import Perception, PerceptionKind


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
