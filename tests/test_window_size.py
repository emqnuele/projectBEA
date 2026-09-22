"""How much she keeps is one number, and moving it moves the whole window.

The ceiling used to be the only thing anyone could raise, and raising it did
almost nothing: the handoff still fired at the same 120k and still settled at
the same 50k, so the window kept exactly as much past as before and only the
emergency valve grew. The ceiling now carries the trigger, the resting size
and the ongoing present with it — that is what makes the setting mean what it
says — while anyone who wants one of the three apart can still pin it.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from src.core.config import BrainConfig
from src.core.consciousness import Consciousness
from src.core.memory.store import MemoryStore
from src.core.mind.single_context import SingleContext
from src.core.mind.token_budget import (
    WINDOW_MAX_TOKENS,
    WINDOW_MIN_TOKENS,
    TokenBudget,
    budget_for,
    budget_from_config,
    clamp_ceiling,
)
from src.core.settings_schema import ValidationError, apply_section, section

# --- one number decides the shape ---------------------------------------------


def test_the_default_ceiling_derives_exactly_the_shape_it_always_had():
    budget, hot = budget_for(150_000)

    assert (budget.max_tokens, budget.trigger_tokens, budget.target_tokens) == (
        150_000, 120_000, 50_000)
    assert hot == 30_000


def test_raising_the_ceiling_raises_what_she_actually_keeps():
    """The trigger is what decides how much past survives, not the ceiling."""
    small, _ = budget_for(WINDOW_MIN_TOKENS)
    large, large_hot = budget_for(WINDOW_MAX_TOKENS)

    assert large.trigger_tokens > small.trigger_tokens
    assert large.target_tokens > small.target_tokens
    assert large_hot > 30_000


def test_the_derived_shape_stays_in_order_at_every_slider_position():
    for ceiling in range(WINDOW_MIN_TOKENS, WINDOW_MAX_TOKENS + 1, 10_000):
        budget, hot = budget_for(ceiling)
        assert budget.target_tokens <= budget.trigger_tokens <= budget.max_tokens
        assert hot <= budget.max_tokens


def test_a_ceiling_outside_what_is_supported_is_clamped_not_refused():
    """A config from an older build, or typed by hand, must still start."""
    assert clamp_ceiling(10_000) == WINDOW_MIN_TOKENS
    assert clamp_ceiling(10**9) == WINDOW_MAX_TOKENS
    assert clamp_ceiling("nonsense") == WINDOW_MIN_TOKENS
    assert clamp_ceiling(None) == WINDOW_MIN_TOKENS


# --- but the three are still reachable ----------------------------------------


def test_a_pinned_number_wins_over_the_ceiling():
    budget, hot = budget_for(500_000, trigger=90_000, hot=7_000)

    assert budget.trigger_tokens == 90_000
    assert hot == 7_000
    assert budget.max_tokens == 500_000


def test_zero_means_follow_the_ceiling_rather_than_a_window_of_nothing():
    budget, hot = budget_for(300_000, trigger=0, target=0, hot=0)

    assert (budget.trigger_tokens, budget.target_tokens, hot) == (240_000, 100_000, 60_000)


def test_the_config_block_is_read_the_same_way_everywhere():
    budget, hot = budget_from_config(
        {"context_max_tokens": 200_000, "handoff_target_tokens": 25_000})

    assert budget.max_tokens == 200_000
    assert budget.trigger_tokens == 160_000   # followed
    assert budget.target_tokens == 25_000     # pinned
    assert hot == 40_000                      # followed


# --- config and migration ------------------------------------------------------


def test_a_fresh_config_lets_the_three_follow_the_ceiling():
    cc = BrainConfig().consciousness

    assert cc["context_max_tokens"] == WINDOW_MIN_TOKENS
    assert cc["handoff_trigger_tokens"] == 0
    assert cc["handoff_target_tokens"] == 0
    assert cc["hot_tokens"] == 0


def test_an_install_carrying_the_old_defaults_starts_following_the_ceiling(tmp_path):
    """Every install written before this has the three spelled out. Left
    pinned, the new slider would move the ceiling and nothing else."""
    import json

    (tmp_path / "config.json").write_text(json.dumps(
        {"consciousness": {"context_max_tokens": 150_000,
                           "handoff_trigger_tokens": 120_000,
                           "handoff_target_tokens": 50_000,
                           "hot_tokens": 30_000}}))

    cc = BrainConfig().consciousness

    assert (cc["handoff_trigger_tokens"], cc["handoff_target_tokens"],
            cc["hot_tokens"]) == (0, 0, 0)


def test_a_number_somebody_chose_themselves_stays_chosen(tmp_path):
    import json

    (tmp_path / "config.json").write_text(json.dumps(
        {"consciousness": {"handoff_trigger_tokens": 90_000,
                           "hot_tokens": 30_000}}))

    cc = BrainConfig().consciousness

    assert cc["handoff_trigger_tokens"] == 90_000   # theirs
    assert cc["hot_tokens"] == 0                    # the old default


# --- the schema ----------------------------------------------------------------


def test_the_ceiling_is_a_slider_over_the_supported_range():
    setting = section("consciousness").get("context_max_tokens")

    assert setting.ui == "slider"
    assert (setting.minimum, setting.maximum) == (WINDOW_MIN_TOKENS, WINDOW_MAX_TOKENS)
    assert setting.step


def test_the_slider_carries_the_numbers_it_implies():
    """The dashboard draws the derived shape from these rather than from
    ratios of its own, so there is one definition of what a ceiling means."""
    derives = section("consciousness").get("context_max_tokens").describe()["derives"]

    assert [d["key"] for d in derives] == [
        "handoff_trigger_tokens", "handoff_target_tokens", "hot_tokens"]
    for derive in derives:
        assert 0 < derive["ratio"] <= 1


def test_the_three_are_folded_away_as_advanced():
    consciousness = section("consciousness")

    for key in ("handoff_trigger_tokens", "handoff_target_tokens", "hot_tokens"):
        assert consciousness.get(key).advanced, key
    assert not consciousness.get("context_max_tokens").advanced


def test_a_ceiling_under_the_floor_is_refused_rather_than_stored():
    with pytest.raises(ValidationError):
        apply_section(BrainConfig(), "consciousness", {"context_max_tokens": 1_000})


def test_the_section_accepts_a_ceiling_inside_the_range():
    config = BrainConfig()

    apply_section(config, "consciousness", {"context_max_tokens": 300_000})

    assert config.consciousness["context_max_tokens"] == 300_000


# --- resizing a window that is already live ------------------------------------


def window(**kw) -> SingleContext:
    return SingleContext(TokenBudget(max_tokens=2_000, trigger_tokens=1_500,
                                     target_tokens=1_000), hot_tokens=1_000, **kw)


def test_a_wider_ceiling_reaches_the_live_window():
    ctx = window()

    assert ctx.retarget(*budget_for(300_000))

    assert ctx.budget.max_tokens == 300_000
    assert ctx.budget.trigger_tokens == 240_000
    assert ctx.hot_tokens == 60_000


def test_resizing_to_the_same_shape_changes_nothing():
    ctx = window()
    budget, hot = budget_for(300_000)
    ctx.retarget(budget, hot)

    assert ctx.retarget(*budget_for(300_000)) is False


def test_a_narrower_ceiling_trims_the_window_it_no_longer_fits():
    ctx = window()
    for i in range(20):
        ctx.append("user", f"line {i} " + "x" * 400)
    before = ctx.total_tokens

    ctx.retarget(TokenBudget(max_tokens=1_000, trigger_tokens=900, target_tokens=500), 500)

    assert ctx.total_tokens <= 1_000 < before
    assert ctx.evicted_tokens > 0   # unsummarized amnesia stays auditable


def test_trimming_on_a_resize_spares_the_continuity_bridge():
    ctx = window()
    ctx.clear(bridge="[EARLIER] you talked about food")
    for i in range(20):
        ctx.append("user", f"line {i} " + "x" * 400)

    ctx.retarget(TokenBudget(max_tokens=1_000, trigger_tokens=900, target_tokens=500), 500)

    assert any(m["role"] == "system" for m in ctx.messages())


def test_the_hot_present_never_outgrows_the_ceiling_it_lives_in():
    ctx = window()

    ctx.retarget(TokenBudget(max_tokens=5_000, trigger_tokens=4_000,
                             target_tokens=2_000), 500_000)

    assert ctx.hot_tokens <= 5_000


def test_the_live_window_reports_the_size_it_was_given():
    ctx = window()
    ctx.retarget(*budget_for(300_000))

    status = ctx.status()

    assert status["max_tokens"] == 300_000
    assert status["trigger_tokens"] == 240_000
    assert status["hot_tokens"] == 60_000


# --- and the mind picks it up without a restart --------------------------------


def mind(config) -> Consciousness:
    return Consciousness(
        config=config, llm=MagicMock(), bus=MagicMock(), expression=MagicMock(),
        surfaces=MagicMock(), history_manager=MagicMock(), event_manager=MagicMock(),
        soul_getter=lambda: "soul", operating_getter=lambda: "operating",
        memory=MemoryStore(":memory:"), profiler=None,
    )


def test_the_mind_builds_its_window_from_the_ceiling():
    config = BrainConfig()
    config.consciousness["context_max_tokens"] = 400_000

    assert mind(config).sliding_window.budget.trigger_tokens == 320_000


def test_a_ceiling_changed_in_the_dashboard_reaches_the_window_without_a_restart():
    """It used to be read once, in the constructor: the dashboard said 'she is
    already using it' and she was not, until somebody restarted the engine."""
    config = BrainConfig()
    consciousness = mind(config)
    assert consciousness.sliding_window.budget.max_tokens == WINDOW_MIN_TOKENS

    config.consciousness["context_max_tokens"] = 300_000
    consciousness.apply_budget()

    assert consciousness.sliding_window.budget.max_tokens == 300_000
    assert consciousness.sliding_window.budget.trigger_tokens == 240_000
    assert consciousness.sliding_window.hot_tokens == 60_000


def test_the_handoff_switch_is_re_read_too():
    config = BrainConfig()
    consciousness = mind(config)

    config.consciousness["context_handoff"] = False
    consciousness.apply_budget()

    assert consciousness._handoff_enabled is False


@pytest.mark.asyncio
async def test_a_resize_asked_for_off_the_loop_lands_on_it():
    """The window is single-threaded by contract and `POST /config` is a
    synchronous route, so it arrives from a thread pool. An eviction running
    beside an append would lose the running total — so the resize is posted
    to the loop instead of running on the caller thread."""
    config = BrainConfig()
    consciousness = mind(config)
    consciousness._loop = asyncio.get_running_loop()

    config.consciousness["context_max_tokens"] = 300_000
    await asyncio.to_thread(consciousness.apply_budget)
    await asyncio.sleep(0)   # the posted resize runs before the loop goes idle

    assert consciousness.sliding_window.budget.max_tokens == 300_000
    assert consciousness.sliding_window.budget.trigger_tokens == 240_000


@pytest.mark.asyncio
async def test_a_resize_on_the_loop_itself_is_applied_at_once():
    config = BrainConfig()
    consciousness = mind(config)
    consciousness._loop = asyncio.get_running_loop()

    config.consciousness["context_max_tokens"] = 300_000
    consciousness.apply_budget()

    assert consciousness.sliding_window.budget.max_tokens == 300_000
