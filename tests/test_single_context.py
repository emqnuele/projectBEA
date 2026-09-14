import time
from unittest.mock import MagicMock

import pytest

from src.core.mind.single_context import SingleContext
from src.core.mind.token_budget import BudgetEntry, TokenBudget, estimate_tokens


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
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == handoff_prose
    assert messages[1]["content"] == "hot stuff"
    assert ctx.version == 1
