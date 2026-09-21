"""Saving the diary must not stall the event loop.

Embedding a diary entry is tens of milliseconds of cpu on the calling thread.
`_process_session_async` runs on the loop, so the save has to hop to a worker
thread — the assertion is that the loop kept turning, not how it got there.
"""

import asyncio
import threading
import time
from types import SimpleNamespace

from src.core.memory.db import Database
from src.core.memory.rag import Rag
from src.core.memory.store import Conversations
from src.core.skills.memory.memory import MemorySkill

WORK_SECONDS = 0.2


class SlowEmbedder:
    def __init__(self):
        self.thread = None

    def embed(self, texts):
        self.thread = threading.current_thread()
        time.sleep(WORK_SECONDS)
        return [[1.0, 0.0] for _ in texts]

    @property
    def dim(self):
        return 2


class FakeGenerator:
    async def generate_diary(self, transcript):
        return {"diary_content": "marco adora minecraft e la pizza",
                "tags": ["marco"], "user_id": "u1"}


def _skill(rag, conversations):
    config = SimpleNamespace(skills={"memory": {"enabled": True}})
    context = SimpleNamespace(memory=SimpleNamespace(rag=rag, conversations=conversations))
    skill = MemorySkill(config, None, None, context)
    skill.initialize()
    skill.generator = FakeGenerator()
    return skill


def _an_evening(conversations, session="s1"):
    conversations.add(conversation_key="stage", role="user", kind="chat",
                      content="[marco] ciao bea, parliamo di minecraft",
                      author_identity="ui:marco", display_name="marco",
                      session_id=session)
    conversations.add(conversation_key="stage", role="bea", kind="voice",
                      content="volentieri, raccontami", display_name="bea",
                      session_id=session)


async def _ticks_during(coro) -> int:
    counter = 0

    async def tick():
        nonlocal counter
        while True:
            await asyncio.sleep(0.005)
            counter += 1

    ticker = asyncio.create_task(tick())
    try:
        await coro
    finally:
        ticker.cancel()
        await asyncio.gather(ticker, return_exceptions=True)
    return counter


async def test_saving_the_diary_does_not_stall_the_loop():
    db = Database(":memory:").init()
    try:
        conversations = Conversations(db)
        _an_evening(conversations)
        rag = Rag(db, SlowEmbedder(), min_similarity=0.2)
        skill = _skill(rag, conversations)
        ticks = await _ticks_during(skill._process_session_async("s1"))
        assert ticks > 5
        assert rag.exists("diary", "s1")
    finally:
        db.close()


async def test_the_diary_is_embedded_off_the_main_thread():
    db = Database(":memory:").init()
    try:
        conversations = Conversations(db)
        _an_evening(conversations)
        embedder = SlowEmbedder()
        rag = Rag(db, embedder, min_similarity=0.2)
        skill = _skill(rag, conversations)
        await skill._process_session_async("s1")
        assert embedder.thread is not threading.main_thread()
    finally:
        db.close()
