import time

from src.core.mind.handoff import HandoffWorker, format_turns, render_handoff
from src.core.mind.single_context import SingleContext
from src.core.mind.token_budget import TokenBudget, estimate_tokens, split_hot_cold


def test_token_budget_initialization():
    budget = TokenBudget(max_tokens=10000, trigger_tokens=8000, target_tokens=5000)
    assert budget.max_tokens == 10000
    assert budget.trigger_tokens == 8000
    assert budget.target_tokens == 5000
    assert budget.needs_handoff(8000) is True
    assert budget.needs_handoff(7999) is False
    assert budget.over_max(10001) is True


def test_single_context_append_and_status():
    ctx = SingleContext(TokenBudget(max_tokens=10000, trigger_tokens=8000, target_tokens=5000))
    entry = ctx.append("user", "hello world", key="stage")
    assert entry.tokens == estimate_tokens("hello world") + 8

    status = ctx.status()
    assert status["total_tokens"] == entry.tokens
    assert status["needs_handoff"] is False


def test_single_context_emergency_valve_in_append():
    budget = TokenBudget(max_tokens=2000, trigger_tokens=1800, target_tokens=1500)
    ctx = SingleContext(budget)

    # Fill context exactly to max
    ctx.append("user", "a" * (1800 * 4)) # Approx 1800 tokens + 8
    assert ctx.total_tokens <= 2000

    # Append another, exceeding max_tokens
    ctx.append("user", "b" * (400 * 4)) # Approx 400 + 8

    # The first message should be popped out to maintain max_tokens
    assert ctx.total_tokens <= 2000
    assert len(ctx._entries) == 1


def test_single_context_turns_for():
    ctx = SingleContext()
    ctx.append("user", "hi", key="discord:123", author="alice", addressee="bea")
    ctx.append("assistant", "hello", key="discord:123")
    ctx.append("user", "ignored", key="stage")

    turns = ctx.turns_for("discord:123")
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[0]["identity"] == "alice"
    assert turns[1]["role"] == "bea"
    assert turns[1]["content"] == "hello"


def test_single_context_swap():
    budget = TokenBudget(max_tokens=200, trigger_tokens=150, target_tokens=100)
    ctx = SingleContext(budget, hot_tokens=50, hot_seconds=3600.0)

    # Add old cold message
    ctx.append("user", "cold stuff", ts=time.time() - 4000)
    # Add hot message
    ctx.append("user", "hot stuff", ts=time.time())

    assert len(ctx.messages()) == 2

    handoff_prose = "you talked about cold stuff"
    ctx.swap(handoff_prose)

    messages = ctx.messages()
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == handoff_prose
    assert messages[1]["content"] == "hot stuff"
    assert ctx.version == 1


def test_swap_handoff_visible_in_scoped_reads():
    ctx = SingleContext(TokenBudget(max_tokens=500, trigger_tokens=400, target_tokens=200),
                        hot_tokens=50, hot_seconds=3600.0)
    ctx.append("user", "cold stuff", ts=time.time() - 4000)
    ctx.append("user", "hot stuff", ts=time.time())
    ctx.swap("you talked about cold stuff")
    scoped = ctx.messages(key="discord:888")
    assert any(m["content"] == "you talked about cold stuff" for m in scoped)


def test_swap_settles_near_target_not_at_trigger():
    budget = TokenBudget(max_tokens=6000, trigger_tokens=4000, target_tokens=1000)
    ctx = SingleContext(budget, hot_tokens=100, hot_seconds=60.0)
    old = time.time() - 4000
    for i in range(20):
        ctx.append("user", f"old line {i} " + "word " * 300, ts=old)
    ctx.append("user", "live now", ts=time.time())
    assert ctx.status()["needs_handoff"] is True
    ctx.swap("recap of the old lines")
    assert ctx.total_tokens <= budget.target_tokens


def test_oversized_single_message_cannot_pin_window():
    budget = TokenBudget(max_tokens=2000, trigger_tokens=1800, target_tokens=1500)
    ctx = SingleContext(budget)
    ctx.append("user", "z " * 5000)
    assert len(ctx._entries) == 1
    assert ctx.total_tokens <= budget.max_tokens


def test_valve_pins_system_bridge_first():
    budget = TokenBudget(max_tokens=500, trigger_tokens=400, target_tokens=200)
    ctx = SingleContext(budget)
    ctx.append("system", "[EARLIER] the bridge", key="stage")
    for i in range(30):
        ctx.append("user", f"filler {i} " + "word " * 30, key="stage")
    assert ctx.total_tokens <= budget.max_tokens
    assert ctx.messages()[0]["content"] == "[EARLIER] the bridge"


def test_split_defaults_to_wall_clock():
    old_ts = time.time() - 7200
    from src.core.mind.token_budget import BudgetEntry
    entries = [BudgetEntry(tokens=10, ts=old_ts, payload={}),
               BudgetEntry(tokens=10, ts=time.time(), payload={})]
    cold, hot = split_hot_cold(entries, hot_tokens=10_000, hot_seconds=1800.0)
    assert len(cold) == 1
    assert len(hot) == 1


def test_apply_overlap_carries_cold_tail_verbatim():
    from src.core.mind.token_budget import BudgetEntry
    cold = [BudgetEntry(tokens=4000, ts=1.0, payload={"content": "a"}),
            BudgetEntry(tokens=4000, ts=2.0, payload={"content": "b"})]
    hot = [BudgetEntry(tokens=100, ts=3.0, payload={"content": "c"})]
    rest, carried = SingleContext.apply_overlap(cold, hot)
    assert [e.payload["content"] for e in carried] == ["b", "c"]
    assert [e.payload["content"] for e in rest] == ["a"]


def test_format_turns_skips_scaffolding():
    text = ("[PERCEPTIONS — answer here]\n"
            "[WHERE YOU ARE]\n"
            "You are on discord in conversation 1 with alice.\n"
            "(CHAT) [via discord] hello")
    out = format_turns([{"role": "user", "content": text}])
    assert "PERCEPTIONS" not in out
    assert "You are on" not in out
    assert "hello" in out


class _Reply:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, ctx=None, arrive=None, fail=False, empty=False):
        self.ctx = ctx
        self.arrive = arrive or []
        self.fail = fail
        self.empty = empty
        self.calls = 0

    async def complete(self, messages, tools=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError("worker down")
        for role, content, key in self.arrive:
            self.ctx.append(role, content, key=key, author="bob")
        if self.empty:
            return _Reply("   ")
        return _Reply("you talked at length about pasta")


def _full_window(**kw):
    budget = TokenBudget(max_tokens=6000, trigger_tokens=3000, target_tokens=2000)
    ctx = SingleContext(budget, hot_tokens=100, hot_seconds=60.0, **kw)
    old = time.time() - 4000
    for i in range(10):
        ctx.append("user", f"cold line {i} " + "word " * 400, ts=old)
    ctx.append("user", "live now", ts=time.time())
    assert ctx.status()["needs_handoff"] is True
    return ctx


async def test_handoff_keeps_keys_and_never_duplicates():
    ctx = _full_window()
    before = ctx.total_tokens
    llm = _FakeLLM(ctx, arrive=[("user", "mid-flight telegram", "telegram:1"),
                               ("user", "mid-flight discord", "discord:2")])
    worker = HandoffWorker(llm)
    prose = await worker.maybe_swap(ctx)
    assert prose
    contents = [m["content"] for m in ctx.messages()]
    assert len(contents) == len(set(contents)), "mid-flight turn stored twice"
    assert sum("mid-flight" in c for c in contents) == 2
    assert ctx.turns_for("telegram:1"), "telegram key lost in flight"
    assert ctx.turns_for("discord:2"), "discord key lost in flight"
    assert ctx.total_tokens < before
    assert worker.swaps == 1


async def test_handoff_failure_keeps_old_window():
    ctx = _full_window()
    snapshot = [(m["role"], m["content"]) for m in ctx.messages()]
    worker = HandoffWorker(_FakeLLM(fail=True))
    assert await worker.maybe_swap(ctx) == ""
    assert [(m["role"], m["content"]) for m in ctx.messages()] == snapshot
    assert worker.swaps == 0


async def test_handoff_empty_prose_keeps_old_window():
    ctx = _full_window()
    n = len(ctx.messages())
    worker = HandoffWorker(_FakeLLM(empty=True))
    assert await worker.maybe_swap(ctx) == ""
    assert len(ctx.messages()) == n
    assert worker.swaps == 0


async def test_handoff_cold_empty_backs_off():
    ctx = SingleContext(TokenBudget(max_tokens=2000, trigger_tokens=1000, target_tokens=1000),
                        hot_tokens=100_000, hot_seconds=10_000.0)
    ctx.append("user", "one live line " + "word " * 1500, ts=time.time())
    assert ctx.status()["needs_handoff"] is True
    llm = _FakeLLM()
    worker = HandoffWorker(llm)
    assert await worker.maybe_swap(ctx) == ""
    assert await worker.maybe_swap(ctx) == ""
    assert llm.calls <= 1, "cold-empty trigger must back off, not snapshot per turn"


async def test_handoff_render_system_block():
    assert render_handoff("  ").strip() == ""
    assert render_handoff("you talked").startswith("[EARLIER]")


def test_swap_never_stacks_continuity_bridges():
    budget = TokenBudget(max_tokens=6000, trigger_tokens=3000, target_tokens=5000)
    ctx = SingleContext(budget, hot_tokens=100_000, hot_seconds=100_000.0)
    ctx.append("user", "hello world", key="stage")
    _, hot = ctx.snapshot_for_handoff()
    ctx.swap_with_snapshot("[EARLIER]\nfirst bridge", hot, [])
    _, hot2 = ctx.snapshot_for_handoff()
    ctx.swap_with_snapshot("[EARLIER]\nsecond bridge", hot2, [])
    bridges = [m for m in ctx.messages() if m.get("role") == "system"]
    assert len(bridges) == 1
    assert "second bridge" in bridges[0]["content"]
    assert "first bridge" not in " ".join(m["content"] for m in ctx.messages()
                                          if m.get("role") != "system")


def test_hot_tokens_clamped_to_the_ceiling():
    budget = TokenBudget(max_tokens=2000, trigger_tokens=1800, target_tokens=1500)
    ctx = SingleContext(budget, hot_tokens=500_000)
    assert ctx.hot_tokens <= budget.max_tokens


def test_valve_evictions_are_counted_in_status():
    budget = TokenBudget(max_tokens=500, trigger_tokens=400, target_tokens=200)
    ctx = SingleContext(budget)
    for i in range(30):
        ctx.append("user", f"filler {i} " + "word " * 30, key="stage")
    assert ctx.total_tokens <= budget.max_tokens
    assert ctx.status()["valve_evicted_tokens"] > 0


def test_format_turns_keeps_user_lines_with_scaffolding_prefixes():
    out = format_turns([{"role": "user", "content": "You are on fire today, bea!"}])
    assert "You are on fire today" in out
    out = format_turns([{"role": "user", "content": "[EARLIER] i literally typed this"}])
    assert "i literally typed this" in out


def test_format_turns_still_skips_real_scaffolding():
    orientation = ("You are on discord in conversation 1 with alice. Answer here with "
                   "send_message(platform='discord', channel='1') — never claim otherwise.")
    out = format_turns([{"role": "user", "content": f"[WHERE YOU ARE]\n{orientation}\nhello"}])
    assert "hello" in out
    assert "You are on discord" not in out
    assert "WHERE YOU ARE" not in out
    out = format_turns([{"role": "system", "content": "[EARLIER]\nold bridge prose"}])
    assert "EARLIER" not in out


async def test_handoff_cold_excludes_old_bridge_entries():
    budget = TokenBudget(max_tokens=6000, trigger_tokens=3000, target_tokens=2000)
    ctx = SingleContext(budget, hot_tokens=100, hot_seconds=60.0)
    old = time.time() - 4000
    ctx.append("system", "[EARLIER]\nprevious bridge prose", key="stage", ts=old)
    for i in range(10):
        ctx.append("user", f"cold line {i} " + "word " * 400, ts=old)
    ctx.append("user", "live now", ts=time.time())
    assert ctx.status()["needs_handoff"] is True
    seen_payloads = []

    class _SpyLLM:
        async def complete(self, messages, tools=None):
            seen_payloads.append(messages[1]["content"])
            return _Reply("fresh recap of the cold lines")

    worker = HandoffWorker(_SpyLLM())
    assert await worker.maybe_swap(ctx)
    assert seen_payloads, "worker never called the llm"
    assert "previous bridge prose" not in seen_payloads[0]
    bridges = [m for m in ctx.messages() if m.get("role") == "system"]
    assert len(bridges) == 1
    assert "fresh recap" in bridges[0]["content"]
