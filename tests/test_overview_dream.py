"""The home screen knows when she last dreamt.

The nightly guard date lived on disk where only the dream skill looked: the
dashboard showed the dream hour and nothing about whether a night ever ran.
`/overview` now carries `dream.last_night` — `""` before the first pass —
so the memory tile can say it.
"""

from types import SimpleNamespace

from src.web.routers.status import overview


def brain(last_night=""):
    config = SimpleNamespace(
        llm_provider="openrouter", openrouter_model="m", openai_model="",
        groq_model="", google_model="", claude_model="", openai_compat_model="",
        anthropic_compat_model="", local_model="", tts_provider="edge",
        stt_provider="groq", language="en",
    )
    memory = SimpleNamespace(
        people=SimpleNamespace(all=lambda: []),
        roster=SimpleNamespace(all=lambda: []),
        rag=None,
        hot=SimpleNamespace(active=lambda: []),
        selflore=SimpleNamespace(facts=lambda: []),
    )
    return SimpleNamespace(
        config=config, memory=memory, skill_registry=None, stt=None,
        obs=SimpleNamespace(client=None), is_speaking=False, is_sleeping=False,
        consciousness=None,
        history_manager=SimpleNamespace(session_id="s1", title="", history=[]),
        plan=SimpleNamespace(all=lambda: [], directive=""),
        dream_skill=SimpleNamespace(last_night=lambda: last_night),
    )


def test_overview_carries_the_last_dream_date():
    assert overview(brain("2026-09-20"))["dream"] == {"last_night": "2026-09-20"}


def test_overview_before_the_first_dream_is_empty_not_missing():
    assert overview(brain())["dream"] == {"last_night": ""}
