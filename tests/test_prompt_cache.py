"""What a provider can cache, and what the three transports do to it.

The loop hands over two system messages on purpose: who she is, which never
moves, and the briefing for this moment, which moves every turn. The briefing
sits *below* the sliding window so the window is part of the cacheable prefix —
a window that reaches 120k tokens is the expensive half of every request.

Two transports used to collect every system message into one field at the top
of the prompt. That put a block that changes every turn in front of the whole
window, and the prefix cache ended where the soul ended.
"""

import pytest

from src.modules.llm.anthropic import AnthropicClient
from src.modules.llm.chat import ChatCompletionsClient
from src.modules.llm.responses import ResponsesClient

SOUL = "SOUL: who she is. Thousands of characters that never move."
BRIEFING = "CURRENT DATE: 2026-09-22\n[HOW YOU FEEL] fine\n[RECALLED] something"
FRAME = "[PERCEPTIONS] ciao bea"


def turn():
    """What `Consciousness.run` builds, in the order it builds it."""
    return [
        {"role": "system", "content": SOUL},
        {"role": "user", "content": "a turn from an hour ago"},
        {"role": "assistant", "content": "what she said back"},
        {"role": "system", "content": BRIEFING},
        {"role": "user", "content": FRAME},
    ]


def flatten(parts):
    """Every message as one ordered list of (where, text)."""
    return [(str(p.get("role") or p.get("type")), str(p.get("content") or "")) for p in parts]


# --- the stable half is the only thing at the top ----------------------------


def test_responses_keeps_the_briefing_below_the_window():
    body = ResponsesClient("https://x/v1", "m").build_body(turn())
    assert body["instructions"] == SOUL
    order = [text for _, text in flatten(body["input"])]
    assert order.index("a turn from an hour ago") < order.index(BRIEFING)
    assert order.index(BRIEFING) < order.index(FRAME)


def test_anthropic_keeps_the_briefing_below_the_window():
    body = AnthropicClient("https://x/v1", "m").build_body(turn())
    assert body["system"] == SOUL
    order = [text for _, text in flatten(body["messages"])]
    assert order.index("a turn from an hour ago") < order.index(BRIEFING)
    assert order.index(BRIEFING) < order.index(FRAME)


def test_chat_completions_passes_the_order_through_untouched():
    body = ChatCompletionsClient("https://x/v1", "m").build_body(turn())
    assert flatten(body["messages"]) == flatten(turn())


@pytest.mark.parametrize("client", [ResponsesClient, AnthropicClient, ChatCompletionsClient])
def test_every_transport_puts_the_same_thing_in_front(client):
    """The cacheable prefix is the same wherever she is pointed."""
    body = client("https://x/v1", "m").build_body(turn())
    front = body.get("instructions") or body.get("system") or \
        body["messages"][0]["content"]
    assert front == SOUL


# --- several leading system messages are still one prefix --------------------


def test_the_skill_sections_stay_in_the_cached_half():
    """`_system_message` composes them into one, but a caller may not."""
    messages = [{"role": "system", "content": SOUL},
                {"role": "system", "content": "## DISCORD\nyou are connected"},
                {"role": "user", "content": FRAME}]
    body = ResponsesClient("https://x/v1", "m").build_body(messages)
    assert body["instructions"] == f"{SOUL}\n\n## DISCORD\nyou are connected"
    assert len(body["input"]) == 1


def test_a_turn_with_no_briefing_is_unchanged():
    messages = [{"role": "system", "content": SOUL}, {"role": "user", "content": FRAME}]
    for client in (ResponsesClient, AnthropicClient):
        body = client("https://x/v1", "m").build_body(messages)
        assert (body.get("instructions") or body.get("system")) == SOUL
