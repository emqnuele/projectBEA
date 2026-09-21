"""The rolling summary is refreshed after answering, never during it.

`Profiler.maybe_summarize` exists and the morning pass reads `summaries`,
but nothing called it outside the dreamer: a busy evening never produced a
summary until tomorrow. The background pass that already refreshes person
cards now refreshes the touched conversations too, throttled by `summary_due`
so a quiet turn costs no model call.
"""

import asyncio
from types import SimpleNamespace

from src.core.consciousness import Consciousness
from src.core.memory.profiler import SUMMARY_EVERY, Profiler
from src.core.memory.store import MemoryStore
from src.core.perception.types import Author, Perception, PerceptionKind


class ScriptedLLM:
    def __init__(self, reply=None):
        self.reply = reply if reply is not None else {"summary": "user aspetta la patch"}
        self.calls = 0

    async def complete_json(self, payload, system=None, history=None):
        self.calls += 1
        return dict(self.reply)


def mind(memory, llm):
    config = SimpleNamespace(consciousness={}, language="")
    profiler = Profiler(llm, memory)
    return Consciousness(
        config=config, llm=None, bus=None, expression=None, surfaces=None,
        history_manager=SimpleNamespace(session_id="s1"), event_manager=None,
        soul_getter=lambda: "", operating_getter=lambda: "",
        memory=memory, profiler=profiler,
    )


def batch(n, key_meta=None):
    out = []
    for i in range(n):
        out.append(Perception(
            kind=PerceptionKind.CHAT, surface="chat:ui", content=f"[user] riga {i}",
            author=Author(platform="ui", native_id="user", display_name="user"),
            meta=dict(key_meta or {}),
        ))
    return out


async def drain(consc):
    tasks = list(consc._bg_tasks)
    if tasks:
        await asyncio.gather(*tasks)


async def test_a_busy_conversation_is_summarized_in_background():
    memory = MemoryStore(":memory:")
    try:
        llm = ScriptedLLM()
        consc = mind(memory, llm)
        for i in range(SUMMARY_EVERY):
            memory.conversations.add(conversation_key="stage", role="user", kind="chat",
                                     content=f"[user] riga {i}", platform="ui",
                                     author_identity="ui:user", display_name="user",
                                     surface="chat:ui", session_id="s1")
        consc._profile_background(batch(2))
        await drain(consc)

        assert memory.conversations.summary("stage") == "user aspetta la patch"
        assert llm.calls >= 1
    finally:
        memory.close()


async def test_a_quiet_turn_costs_no_summary_call():
    memory = MemoryStore(":memory:")
    try:
        llm = ScriptedLLM()
        consc = mind(memory, llm)
        for i in range(3):
            memory.conversations.add(conversation_key="stage", role="user", kind="chat",
                                     content=f"[user] riga {i}", platform="ui",
                                     author_identity="ui:user", display_name="user",
                                     surface="chat:ui", session_id="s1")
        consc._profile_background(batch(1))
        await drain(consc)

        assert llm.calls == 0
        assert memory.conversations.summary("stage") == ""
    finally:
        memory.close()
