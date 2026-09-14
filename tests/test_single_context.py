"""The window breathes: one log, hot kept verbatim, cold handed off."""

from src.core.mind.handoff import (
    build_handoff_payload,
    format_turns,
    normalize_handoff,
    render_handoff,
)
from src.core.mind.single_context import SingleContext
from src.core.mind.token_budget import (
    BudgetEntry,
    TokenBudget,
    conversation_tokens,
    estimate_tokens,
    message_tokens,
    split_hot_cold,
)


def test_estimating_nothing_costs_nothing():
    assert estimate_tokens("") == 0
    assert estimate_tokens("x" * 400) >= 90


def test_a_message_carries_framing_overhead():
    assert message_tokens({"role": "user", "content": ""}) == 8
    assert conversation_tokens([{"role": "user", "content": "hello"}]) > 8


def test_the_handoff_trigger_sits_below_the_ceiling():
    budget = TokenBudget(max_tokens=150_000, trigger_tokens=120_000, target_tokens=50_000)
    assert not budget.needs_handoff(119_999)
    assert budget.needs_handoff(120_000)
    assert not budget.over_max(150_000)
    assert budget.over_max(150_001)


def test_the_ongoing_present_is_never_compressed():
    now = 10_000.0
    entries = [BudgetEntry(tokens=10_000, ts=now - 7200, payload=f"old-{i}") for i in range(8)]
    entries += [BudgetEntry(tokens=5_000, ts=now - 600, payload="right-now") for _ in range(4)]
    cold, hot = split_hot_cold(entries, hot_tokens=30_000, hot_seconds=1800.0, now=now)
    assert [e.payload for e in hot] == ["right-now"] * 4
    assert len(cold) == 8


def test_an_empty_window_hands_off_nothing():
    ctx = SingleContext()
    assert ctx.total_tokens == 0
    assert ctx.status()["needs_handoff"] is False


def test_the_window_breathes_instead_of_pinning_at_the_ceiling():
    """0 -> 120k -> ~42k: cold compressed to a bridge, hot carried verbatim."""
    ctx = SingleContext(TokenBudget(max_tokens=150_000, trigger_tokens=120_000, target_tokens=50_000),
                        hot_tokens=30_000, hot_seconds=3600.0)
    now = 50_000.0
    for i in range(130):
        ctx.append("user", "x" * 4000, ts=now - 7200 + i)
    for i in range(8):
        ctx.append("user", "y" * 4000, ts=now - 300 + i)
    assert ctx.status()["needs_handoff"] is True
    report = ctx.swap("[CONTINUITY FROM EARLIER]\nidentity: bea", now=now)
    assert report["version"] == 1
    assert report["total_tokens"] <= 50_000
    assert report["carried_hot"] == 8


def test_perceptions_arriving_mid_handoff_are_not_lost():
    ctx = SingleContext()
    ctx.append("user", "before")
    report = ctx.swap("bridge", incoming=[{"role": "user", "content": "arrived-mid-handoff"}])
    assert report["version"] == 1
    assert any(m["content"] == "arrived-mid-handoff" for m in ctx.messages())


def test_a_broken_worker_reply_becomes_an_empty_bridge():
    assert normalize_handoff(None) == ""
    assert normalize_handoff("  you talked about food  ") == "you talked about food"
    assert render_handoff("") == ""
    assert render_handoff(None) == ""  # type: ignore[arg-type]


def test_the_bridge_renders_as_prose_under_a_header():
    text = render_handoff("you talked about food for two hours.")
    assert text.startswith("[EARLIER]")
    assert "you talked about food" in text


def test_the_previous_recap_travels_with_the_cold_turns():
    payload = build_handoff_payload("cold stuff", previous_handoff="old recap")
    assert "PREVIOUS RECAP" in payload and "cold stuff" in payload
    assert build_handoff_payload("cold stuff") == "cold stuff"


def test_hot_turns_stay_verbatim_with_speakers():
    text = format_turns([
        {"role": "user", "content": "[marco] ciao"},
        {"role": "assistant", "content": "ei"},
    ])
    assert text == "[marco] ciao\nyou: ei"


def _full_window():
    from src.core.mind.token_budget import TokenBudget

    ctx = SingleContext(TokenBudget(max_tokens=150_000, trigger_tokens=120_000,
                                    target_tokens=50_000),
                        hot_tokens=30_000, hot_seconds=3600.0)
    now = 50_000.0
    for i in range(130):
        ctx.append("user", "[marco] " + "x" * 4000, ts=now - 7200 + i)
    for i in range(8):
        ctx.append("user", "[lu] " + "y" * 4000, ts=now - 300 + i)
    return ctx, now


async def test_the_worker_hands_off_when_due():
    from src.core.agent.types import AssistantMessage
    from src.core.mind.handoff import HandoffWorker
    from tests.fakes import FakeLLMClient

    ctx, _ = _full_window()
    worker = HandoffWorker(FakeLLMClient([AssistantMessage(content="you talked about food.")]))
    prose = await worker.maybe_swap(ctx)
    assert prose == "you talked about food."
    assert worker.swaps == 1
    assert ctx.status()["total_tokens"] <= 50_000
    assert any("[lu]" in m["content"] for m in ctx.messages())
    assert "[EARLIER]" in ctx.messages()[0]["content"]


async def test_nothing_arriving_mid_handoff_is_lost():
    from src.core.agent.types import AssistantMessage
    from src.core.mind.handoff import HandoffWorker
    from tests.fakes import FakeLLMClient

    ctx, _ = _full_window()
    llm = FakeLLMClient([AssistantMessage(content="you talked about food.")])
    worker = HandoffWorker(llm)

    real_complete = llm.complete

    async def intruding(messages, tools=None):
        ctx.append("user", "[marco] arrived mid-handoff")
        return await real_complete(messages, tools=tools)

    llm.complete = intruding  # type: ignore[method-assign]
    await worker.maybe_swap(ctx)
    assert any("arrived mid-handoff" in m["content"] for m in ctx.messages())


async def test_the_worker_stays_idle_when_not_due_or_llmless():
    from src.core.mind.handoff import HandoffWorker
    from tests.fakes import FakeLLMClient

    ctx = SingleContext()
    ctx.append("user", "ciao")
    assert await HandoffWorker().maybe_swap(ctx) == ""
    assert await HandoffWorker(FakeLLMClient()).maybe_swap(ctx) == ""


async def test_the_live_loop_mirrors_turns_and_reports_budget():
    """The loop feeds the window every turn and the dashboard can read it."""
    from src.core.attention.gate import Attention
    from src.core.consciousness import Consciousness
    from src.core.perception.bus import PerceptionBus
    from src.core.perception.types import Author, Perception, PerceptionKind
    from src.core.skills.base import SkillRegistry
    from tests.fakes import FakeExpression, FakeHistory, FakeLLMClient, RecordingEvents

    class Config:
        consciousness = {"enabled": True, "idle_after": 3600.0, "window": 0.0,
                         "burst_steps": 3, "history_limit": 30, "correlation_timeout": 5.0}
        attention = {}
        skills = {}

    mind = Consciousness(
        config=Config(), llm=FakeLLMClient(), bus=PerceptionBus(window=0.0),
        expression=FakeExpression(), surfaces=SkillRegistry(), history_manager=FakeHistory(),
        event_manager=RecordingEvents(), soul_getter=lambda: "", operating_getter=lambda: "",
        attention=Attention(Config()),
    )
    assert mind.window_status()["total_tokens"] == 0
    assert mind._continuity_block() == ""
    mind._record_window([Perception(
        kind=PerceptionKind.CHAT, surface="chat:telegram", content="[marco] ciao",
        salience=0.9, meta={}, author=Author(platform="telegram", native_id="1",
                                             display_name="marco"))])
    assert mind.window_status()["total_tokens"] > 0
    mind._continuity = "you talked about food."
    assert "[EARLIER]" in mind._continuity_block()
