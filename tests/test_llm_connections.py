"""One connection pool per loop, and what happens when a pooled connection died.

Every model call used to open its own session, so every call paid dns, tcp and
tls before the provider saw a byte — 110 to 190ms, measured, on every step of
every turn. These pin the two halves of not doing that: the pool is reused, and
a connection the provider closed while it sat idle costs a resend rather than
the turn.
"""

import aiohttp
import pytest

from src.modules.llm import base
from src.modules.llm.chat import ChatCompletionsClient


class Response:
    def __init__(self, payload):
        self.status = 200
        self._payload = payload

    async def text(self):
        import json

        return json.dumps(self._payload)


class Attempt:
    """What one `session.post` does: raise on the way in, or answer."""

    def __init__(self, outcome, fail_while_reading=None):
        self.outcome = outcome
        self.fail_while_reading = fail_while_reading

    async def __aenter__(self):
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        if self.fail_while_reading is not None:
            raise_later = self.fail_while_reading

            class Broken(Response):
                async def text(self):
                    raise raise_later

            return Broken(self.outcome)
        return Response(self.outcome)

    async def __aexit__(self, *args):
        return False


class Session:
    def __init__(self, attempts):
        self.attempts = attempts
        self.posts = 0
        self.closed = False

    def post(self, url, headers=None, json=None):
        self.posts += 1
        return self.attempts.pop(0)

    async def close(self):
        self.closed = True


REPLY = {"choices": [{"message": {"role": "assistant", "content": "ciao"}}], "usage": {}}


def wire(monkeypatch, *attempts):
    queue = list(attempts)
    made = []

    def build(*args, **kwargs):
        session = Session(queue)
        made.append(session)
        return session

    monkeypatch.setattr(aiohttp, "ClientSession", build)
    return made


def client():
    return ChatCompletionsClient(base_url="https://example.test/v1", model_name="m")


@pytest.fixture(autouse=True)
async def _fresh_pool():
    yield
    await base.close_sessions()


async def test_every_call_on_a_loop_shares_one_session(monkeypatch):
    made = wire(monkeypatch, Attempt(REPLY), Attempt(REPLY), Attempt(REPLY))
    llm = client()

    for _ in range(3):
        await llm.complete([{"role": "user", "content": "hi"}])

    assert len(made) == 1, "each call opened its own connection pool"
    assert made[0].posts == 3


async def test_a_connection_that_died_while_idle_is_sent_again(monkeypatch):
    made = wire(monkeypatch,
                Attempt(aiohttp.ServerDisconnectedError()),
                Attempt(REPLY))

    reply = await client().complete([{"role": "user", "content": "hi"}])

    assert reply.content == "ciao"
    assert made[0].posts == 2


async def test_a_host_that_cannot_be_reached_is_not_retried(monkeypatch):
    refused = aiohttp.ClientConnectorError(None, OSError(61, "refused"))
    made = wire(monkeypatch, Attempt(refused), Attempt(REPLY))

    with pytest.raises(aiohttp.ClientConnectorError):
        await client().complete([{"role": "user", "content": "hi"}])
    # the pool's failover to the next model is the answer to a dead host
    assert made[0].posts == 1


async def test_nothing_is_sent_twice_once_the_answer_started(monkeypatch):
    made = wire(monkeypatch,
                Attempt(REPLY, fail_while_reading=aiohttp.ServerDisconnectedError()),
                Attempt(REPLY))

    with pytest.raises(aiohttp.ServerDisconnectedError):
        await client().complete([{"role": "user", "content": "hi"}])
    assert made[0].posts == 1


async def test_only_one_resend_per_call(monkeypatch):
    made = wire(monkeypatch,
                Attempt(aiohttp.ServerDisconnectedError()),
                Attempt(aiohttp.ServerDisconnectedError()),
                Attempt(REPLY))

    with pytest.raises(aiohttp.ServerDisconnectedError):
        await client().complete([{"role": "user", "content": "hi"}])
    assert made[0].posts == 2


async def test_closing_the_pool_closes_the_session_and_the_next_call_opens_one(monkeypatch):
    made = wire(monkeypatch, Attempt(REPLY), Attempt(REPLY))
    llm = client()

    await llm.complete([{"role": "user", "content": "hi"}])
    await base.close_sessions()
    assert made[0].closed

    await llm.complete([{"role": "user", "content": "hi"}])
    assert len(made) == 2, "a closed session was reused"


class Lines:
    def __init__(self, lines):
        self._lines = lines

    def __aiter__(self):
        async def gen():
            for line in self._lines:
                yield (line + "\n").encode()
        return gen()


class Streamed(Attempt):
    async def __aenter__(self):
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        response = Response({})
        response.content = Lines(self.outcome)
        return response


async def test_a_stream_on_a_connection_that_died_while_idle_is_sent_again(monkeypatch):
    import json

    tool = {"id": "c1", "type": "function",
            "function": {"name": "speak", "arguments": json.dumps({"message": "ciao"})}}
    chunk = {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, **tool}]}}]}
    made = wire(monkeypatch,
                Streamed(aiohttp.ServerDisconnectedError()),
                Streamed([f"data: {json.dumps(chunk)}", "data: [DONE]"]))
    heard = []

    reply = await client().stream_complete(
        [{"role": "user", "content": "hi"}], tools=[{"type": "function", "function": {
            "name": "speak", "parameters": {"type": "object"}}}],
        on_tool_delta=lambda index, name, delta: heard.append(delta))

    assert made[0].posts == 2
    assert reply.tool_calls and reply.tool_calls[0].arguments == {"message": "ciao"}
    assert "".join(heard) == json.dumps({"message": "ciao"})


# --- against a real server ---------------------------------------------------


async def test_a_real_provider_sees_one_connection_across_calls(monkeypatch):
    """The pool, for real: three calls to a server over one tcp connection, held
    open for as long as the settings promise rather than aiohttp's own 15s."""
    from aiohttp import web

    peers = []
    asked = {}
    connector = aiohttp.TCPConnector

    def spy(*args, **kwargs):
        asked.update(kwargs)
        return connector(*args, **kwargs)

    monkeypatch.setattr(aiohttp, "TCPConnector", spy)

    async def completions(request):
        peers.append(request.transport.get_extra_info("peername"))
        return web.json_response(REPLY)

    app = web.Application()
    app.router.add_post("/v1/chat/completions", completions)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    try:
        port = runner.addresses[0][1]
        llm = ChatCompletionsClient(base_url=f"http://127.0.0.1:{port}/v1", model_name="m")
        for _ in range(3):
            reply = await llm.complete([{"role": "user", "content": "hi"}])
            assert reply.content == "ciao"

        assert len(peers) == 3
        assert len(set(peers)) == 1, f"{len(set(peers))} connections for three calls"
        assert asked["keepalive_timeout"] == base.KEEPALIVE_SECONDS == 90.0
        assert asked["ttl_dns_cache"] == base.DNS_CACHE_SECONDS == 300
    finally:
        await base.close_sessions()
        await runner.cleanup()
