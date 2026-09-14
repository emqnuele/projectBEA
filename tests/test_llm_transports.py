"""The three wire protocols every provider speaks, tested without a network.

The app reasons in OpenAI-shaped messages and tools; each transport maps that
onto its own protocol and back. These tests pin the mapping: the request that
must leave, the reply that must come back, and the guarantee that a provider
error always raises (the pool's failover depends on it) instead of returning
silence.
"""

import json

import pytest

from src.core.agent.types import AssistantMessage

# --- faking the wire --------------------------------------------------------


class FakeContent:
    """`response.content` as an async iterator of byte chunks.

    Each yielded chunk ends with a newline, the way SSE frames arrive on a
    real wire: without a terminator there is no block boundary to parse.
    """

    def __init__(self, lines):
        self._lines = [(l if isinstance(l, bytes) else l.encode()) + b"\n" for l in lines]

    def __aiter__(self):
        async def gen():
            for line in self._lines:
                yield line
        return gen()


class FakeResponse:
    def __init__(self, status=200, payload=None, lines=None):
        self.status = status
        self._payload = payload
        self.content = FakeContent(lines or [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def text(self):
        if self._payload is not None:
            return json.dumps(self._payload)
        return ""


class FakeSession:
    """Records every request, replays the queued responses in order."""

    posts = []

    def __init__(self, shared):
        self._shared = shared

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, headers=None, json=None):
        FakeSession.posts.append({"url": url, "headers": headers or {}, "json": json})
        return self._shared.pop(0)


def wire(monkeypatch, *responses):
    import aiohttp

    FakeSession.posts = []
    shared = list(responses)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: FakeSession(shared))


def sent():
    return FakeSession.posts[-1]


TOOLS = [{"type": "function", "function": {
    "name": "speak", "description": "Say something.",
    "parameters": {"type": "object", "properties": {"message": {"type": "string"}},
                   "required": ["message"]}}}]


# --- the responses transport -------------------------------------------------


def responses_client(**overrides):
    from src.modules.llm.responses import ResponsesClient

    args = {"base_url": "https://api.openai.com/v1", "model_name": "gpt-5"}
    args.update(overrides)
    return ResponsesClient(**args)


def responses_reply(text="ciao", calls=(), usage=None):
    output = []
    if text is not None:
        output.append({"type": "message", "id": "msg_1", "role": "assistant",
                       "content": [{"type": "output_text", "text": text}]})
    for call_id, name, arguments in calls:
        output.append({"type": "function_call", "id": f"fc_{call_id}", "call_id": call_id,
                       "name": name, "arguments": json.dumps(arguments)})
    return {"id": "resp_1", "model": "gpt-5", "status": "completed", "output": output,
            "usage": usage or {"input_tokens": 10, "output_tokens": 5}}


async def test_responses_sends_instructions_items_and_flat_tools(monkeypatch):
    wire(monkeypatch, FakeResponse(payload=responses_reply()))
    client = responses_client()

    await client.complete([{"role": "system", "content": "be nice"},
                           {"role": "user", "content": "hi"}], tools=TOOLS)

    body = sent()["json"]
    assert sent()["url"] == "https://api.openai.com/v1/responses"
    assert body["instructions"] == "be nice"
    assert body["input"] == [{"role": "user", "content": "hi"}]
    assert body["tools"] == [{"type": "function", "name": "speak",
                              "description": "Say something.",
                              "parameters": TOOLS[0]["function"]["parameters"]}]
    assert body["tool_choice"] == "auto"


async def test_responses_never_asks_for_server_side_storage(monkeypatch):
    """stateless by design: history travels in, and openrouter rejects store:true."""
    wire(monkeypatch, FakeResponse(payload=responses_reply()))
    client = responses_client()

    await client.complete([{"role": "user", "content": "hi"}])

    body = sent()["json"]
    assert body.get("store") is False
    assert "previous_response_id" not in body


async def test_responses_replays_tool_history_as_items(monkeypatch):
    wire(monkeypatch, FakeResponse(payload=responses_reply()))
    client = responses_client()

    await client.complete([
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "speak", "arguments": '{"message": "hi"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "said"},
    ])

    body = sent()["json"]
    assert {"type": "function_call", "call_id": "c1", "name": "speak",
            "arguments": '{"message": "hi"}'} in body["input"]
    assert {"type": "function_call_output", "call_id": "c1",
            "output": "said"} in body["input"]


async def test_responses_parses_text_tool_calls_and_usage(monkeypatch):
    usage = {"input_tokens": 7, "output_tokens": 3,
             "input_tokens_details": {"cached_tokens": 2}}
    wire(monkeypatch, FakeResponse(payload=responses_reply(
        text="thinking", calls=[("c9", "speak", {"message": "hi"})], usage=usage)))
    client = responses_client()

    reply = await client.complete([{"role": "user", "content": "hi"}], tools=TOOLS)

    assert isinstance(reply, AssistantMessage)
    assert reply.content == "thinking"
    assert [(c.id, c.name, c.arguments) for c in reply.tool_calls] == [
        ("c9", "speak", {"message": "hi"})]
    assert (reply.usage.prompt_tokens, reply.usage.completion_tokens,
            reply.usage.cached_tokens) == (7, 3, 2)
    assert reply.model == "gpt-5"


async def test_responses_streams_text_and_tool_arguments_as_they_arrive(monkeypatch):
    lines = [
        'data: {"type": "response.output_item.added", "output_index": 0, '
        '"item": {"type": "function_call", "id": "fc_1", "call_id": "c1", "name": "speak"}}',
        'data: {"type": "response.function_call_arguments.delta", "output_index": 0, '
        '"delta": "{\\"message\\": "}',
        'data: {"type": "response.function_call_arguments.delta", "output_index": 0, '
        '"delta": "\\"hi\\"}"}',
        'data: {"type": "response.output_text.delta", "delta": "hmm"}',
        'data: {"type": "response.completed", "response": {"usage": '
        '{"input_tokens": 4, "output_tokens": 2}}}',
    ]
    wire(monkeypatch, FakeResponse(lines=lines))
    client = responses_client()
    deltas = []

    reply = await client.stream_complete(
        [{"role": "user", "content": "hi"}], tools=TOOLS,
        on_tool_delta=lambda i, name, fragment: deltas.append((i, name, fragment)))

    assert "".join(d for _, _, d in deltas) == '{"message": "hi"}'
    assert deltas[0][1] == "speak"
    assert reply.content == "hmm"
    assert reply.tool_calls[0].arguments == {"message": "hi"}
    assert reply.tool_calls[0].id == "c1"
    assert reply.usage.prompt_tokens == 4


async def test_a_responses_error_carries_status_and_body(monkeypatch):
    wire(monkeypatch, FakeResponse(status=401, payload={"error": {"message": "bad key"}}))
    client = responses_client()

    with pytest.raises(Exception, match="401"):
        await client.complete([{"role": "user", "content": "hi"}])


async def test_a_responses_failure_before_the_first_chunk_falls_back(monkeypatch):
    """losing a second of latency, not the turn: mirrors the sdk clients."""
    wire(monkeypatch,
         FakeResponse(status=400, payload={"error": {"message": "no stream"}}),
         FakeResponse(payload=responses_reply(text="whole")))
    client = responses_client()

    reply = await client.stream_complete([{"role": "user", "content": "hi"}],
                                         on_tool_delta=lambda *a: None)

    assert reply.content == "whole"


async def test_responses_json_mode_uses_text_format_then_falls_back(monkeypatch):
    wire(monkeypatch,
         FakeResponse(status=400, payload={"error": {"message": "text.format unsupported"}}),
         FakeResponse(payload=responses_reply(text='{"mood": "happy", "message": "hi"}')))
    client = responses_client()

    assert await client.complete_json("hi") == {"mood": "happy", "message": "hi"}
    assert sent()["json"].get("text", {}).get("format", {}).get("type") != "json_object"


# --- the chat completions transport ------------------------------------------


def chat_client(**overrides):
    from src.modules.llm.chat import ChatCompletionsClient

    args = {"base_url": "https://x/v1", "model_name": "m"}
    args.update(overrides)
    return ChatCompletionsClient(**args)


def chat_reply(text="ciao", calls=(), usage=None):
    message = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = [
            {"id": i, "type": "function",
             "function": {"name": n, "arguments": json.dumps(a)}} for i, n, a in calls]
    return {"choices": [{"message": message}],
            "usage": usage or {"prompt_tokens": 6, "completion_tokens": 2}}


async def test_chat_sends_messages_tools_and_choice(monkeypatch):
    wire(monkeypatch, FakeResponse(payload=chat_reply()))
    client = chat_client()

    await client.complete([{"role": "user", "content": "hi"}], tools=TOOLS)

    body = sent()["json"]
    assert sent()["url"] == "https://x/v1/chat/completions"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["tools"] == TOOLS
    assert body["tool_choice"] == "auto"


async def test_chat_omits_tool_choice_where_the_endpoint_rejects_it(monkeypatch):
    """ollama documents tools but not tool_choice: the quirk travels per provider."""
    wire(monkeypatch, FakeResponse(payload=chat_reply()))
    client = chat_client(send_tool_choice=False)

    await client.complete([{"role": "user", "content": "hi"}], tools=TOOLS)

    assert "tool_choice" not in sent()["json"]
    assert sent()["json"]["tools"] == TOOLS


async def test_chat_parses_reply_and_usage(monkeypatch):
    wire(monkeypatch, FakeResponse(payload=chat_reply(
        text="t <think>x</think>", calls=[("c1", "speak", {"message": "hi"})],
        usage={"prompt_tokens": 9, "completion_tokens": 4})))
    client = chat_client()

    reply = await client.complete([{"role": "user", "content": "hi"}], tools=TOOLS)

    assert reply.content == "t"
    assert [(c.id, c.name) for c in reply.tool_calls] == [("c1", "speak")]
    assert (reply.usage.prompt_tokens, reply.usage.completion_tokens) == (9, 4)


async def test_chat_streams_deltas_and_reports_tool_arguments(monkeypatch):
    lines = [
        'data: {"choices": [{"delta": {"content": "he"}}]}',
        'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c2", '
        '"function": {"name": "speak", "arguments": "{\\"msg\\": "}}]}}]}',
        'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, '
        '"function": {"arguments": "\\"sg\\"}"}}]}}]}',
        'data: {"usage": {"prompt_tokens": 3, "completion_tokens": 1}}',
    ]
    wire(monkeypatch, FakeResponse(lines=lines))
    client = chat_client()
    deltas = []

    reply = await client.stream_complete(
        [{"role": "user", "content": "hi"}], tools=TOOLS,
        on_tool_delta=lambda i, name, fragment: deltas.append((i, name, fragment)))

    assert reply.content == "he"
    assert reply.tool_calls[0].arguments == {"msg": "sg"}
    assert reply.tool_calls[0].id == "c2"
    assert reply.usage.prompt_tokens == 3


async def test_a_chat_error_raises_with_the_providers_own_words(monkeypatch):
    wire(monkeypatch, FakeResponse(status=429, payload={"error": {"message": "slow down"}}))
    client = chat_client()

    with pytest.raises(Exception, match="429.*slow down"):
        await client.complete([{"role": "user", "content": "hi"}])


async def test_chat_retries_without_reasoning_when_the_model_refuses_it(monkeypatch):
    from src.modules.llm.reasoning import style_for

    wire(monkeypatch,
         FakeResponse(status=400, payload={"error": {"message": "reasoning_effort refused"}}),
         FakeResponse(payload=chat_reply(text="ok")))
    client = chat_client(reasoning=style_for("openai", "off"))

    assert (await client.complete([{"role": "user", "content": "hi"}])).content == "ok"
    assert len(FakeSession.posts) == 2
    assert "reasoning_effort" not in sent()["json"]


async def test_chat_json_mode_falls_back_when_refused(monkeypatch):
    wire(monkeypatch,
         FakeResponse(status=400, payload={"error": {"message": "response_format unsupported"}}),
         FakeResponse(payload=chat_reply(text='{"a": 1}')))
    client = chat_client()

    assert await client.complete_json("hi") == {"a": 1}


# --- the anthropic transport ---------------------------------------------------


def anthropic_client(**overrides):
    from src.modules.llm.anthropic import AnthropicClient

    args = {"base_url": "https://api.anthropic.com/v1", "model_name": "claude-sonnet-5",
            "api_key": "k"}
    args.update(overrides)
    return AnthropicClient(**args)


def anthropic_reply(text="ciao", calls=(), usage=None):
    content = []
    if text is not None:
        content.append({"type": "text", "text": text})
    for call_id, name, arguments in calls:
        content.append({"type": "tool_use", "id": call_id, "name": name, "input": arguments})
    return {"id": "msg_1", "model": "claude-sonnet-5", "stop_reason": "tool_use",
            "content": content,
            "usage": usage or {"input_tokens": 8, "output_tokens": 6}}


async def test_anthropic_extracts_system_and_translates_tools(monkeypatch):
    wire(monkeypatch, FakeResponse(payload=anthropic_reply()))
    client = anthropic_client()

    await client.complete([{"role": "system", "content": "be nice"},
                           {"role": "user", "content": "hi"}], tools=TOOLS)

    body = sent()["json"]
    assert sent()["url"] == "https://api.anthropic.com/v1/messages"
    assert body["system"] == "be nice"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["tools"] == [{"name": "speak", "description": "Say something.",
                              "input_schema": TOOLS[0]["function"]["parameters"]}]
    assert sent()["headers"]["x-api-key"] == "k"
    assert sent()["headers"]["anthropic-version"] == "2023-06-01"


async def test_anthropic_replays_tool_history_as_blocks(monkeypatch):
    wire(monkeypatch, FakeResponse(payload=anthropic_reply()))
    client = anthropic_client()

    await client.complete([
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "speak", "arguments": '{"message": "hi"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "said"},
    ])

    messages = sent()["json"]["messages"]
    assert messages[0] == {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": "c1", "name": "speak",
                     "input": {"message": "hi"}}]}
    assert messages[1] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "said"}]}


async def test_anthropic_parses_text_tool_use_and_usage(monkeypatch):
    wire(monkeypatch, FakeResponse(payload=anthropic_reply(
        text="hmm", calls=[("tu_1", "speak", {"message": "hi"})],
        usage={"input_tokens": 5, "output_tokens": 5,
               "cache_read_input_tokens": 1})))
    client = anthropic_client()

    reply = await client.complete([{"role": "user", "content": "hi"}], tools=TOOLS)

    assert reply.content == "hmm"
    assert [(c.id, c.name, c.arguments) for c in reply.tool_calls] == [
        ("tu_1", "speak", {"message": "hi"})]
    assert (reply.usage.prompt_tokens, reply.usage.completion_tokens,
            reply.usage.cached_tokens) == (5, 5, 1)


async def test_anthropic_streams_text_and_partial_json(monkeypatch):
    lines = [
        'event: content_block_start',
        'data: {"type": "content_block_start", "index": 1, '
        '"content_block": {"type": "tool_use", "id": "tu_2", "name": "speak"}}',
        'event: content_block_delta',
        'data: {"type": "content_block_delta", "index": 1, '
        '"delta": {"type": "input_json_delta", "partial_json": "{\\"msg\\": "}}',
        'event: content_block_delta',
        'data: {"type": "content_block_delta", "index": 1, '
        '"delta": {"type": "input_json_delta", "partial_json": "\\"sg\\"}"}}',
        'event: content_block_delta',
        'data: {"type": "content_block_delta", "index": 0, '
        '"delta": {"type": "text_delta", "text": "yo"}}',
        'event: message_delta',
        'data: {"type": "message_delta", "usage": {"output_tokens": 7}}',
    ]
    wire(monkeypatch, FakeResponse(lines=lines))
    client = anthropic_client()
    deltas = []

    reply = await client.stream_complete(
        [{"role": "user", "content": "hi"}], tools=TOOLS,
        on_tool_delta=lambda i, name, fragment: deltas.append((i, name, fragment)))

    assert "".join(d for _, _, d in deltas) == '{"msg": "sg"}'
    assert reply.tool_calls[0].arguments == {"msg": "sg"}
    assert reply.tool_calls[0].id == "tu_2"
    assert reply.content == "yo"
    assert reply.usage.completion_tokens == 7


async def test_an_anthropic_error_raises_with_type_and_message(monkeypatch):
    wire(monkeypatch, FakeResponse(
        status=400, payload={"type": "error",
                             "error": {"type": "invalid_request_error",
                                       "message": "tools need input_schema"}}))
    client = anthropic_client()

    with pytest.raises(Exception, match="invalid_request_error.*input_schema"):
        await client.complete([{"role": "user", "content": "hi"}], tools=TOOLS)


async def test_anthropic_json_mode_is_prompt_plus_parse(monkeypatch):
    wire(monkeypatch, FakeResponse(payload=anthropic_reply(
        text='Sure:\n```json\n{"mood": "ok", "message": "hi"}\n```', calls=())))
    client = anthropic_client()

    assert await client.complete_json("hi") == {"mood": "ok", "message": "hi"}
