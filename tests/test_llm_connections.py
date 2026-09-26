"""One connection pool per loop, and what happens when a pooled connection died.

Every model call used to open its own session, so every call paid dns, tcp and
tls before the provider saw a byte — 110 to 190ms, measured, on every step of
every turn. These pin the two halves of not doing that: the pool is reused, and
a connection the provider closed while it sat idle costs a resend rather than
the turn.
"""

import asyncio

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


def test_a_pool_does_not_outlive_the_loop_that_made_it(monkeypatch):
    """A session belongs to the loop that made it, and the doctor runs on its
    own. A finished loop must not leave its pool remembered for good."""
    wire(monkeypatch, Attempt(REPLY), Attempt(REPLY))
    llm = client()
    first, second = asyncio.new_event_loop(), asyncio.new_event_loop()
    try:
        first.run_until_complete(llm.complete([{"role": "user", "content": "hi"}]))
        assert first in base._sessions

        first.run_until_complete(base.close_sessions())
        assert first not in base._sessions
        first.close()

        second.run_until_complete(llm.complete([{"role": "user", "content": "hi"}]))
        # the closed loop's entry was pruned rather than kept forever
        assert list(base._sessions) == [second]
    finally:
        second.run_until_complete(base.close_sessions())
        second.close()


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
        assert asked["socket_factory"] is base._keepalive_socket
    finally:
        await base.close_sessions()
        await runner.cleanup()


# 26 september: a streamed call got no headers for 30s, and its resend went back
# through the same pool — which hands out its oldest idle connection first —
# and waited 30s more. The turn was lost after a minute of silence.


async def test_a_stall_on_a_pooled_connection_is_resent_on_a_new_one(monkeypatch, caplog):
    import json
    import logging

    from aiohttp import web

    monkeypatch.setattr(base, "STREAM_HEADERS_TIMEOUT", 0.3)
    monkeypatch.setattr(base, "_is_local", lambda url: False)
    pooled = set()
    streamed = []
    release = asyncio.Event()
    both_in = asyncio.Event()
    chunk = {"choices": [{"index": 0, "delta": {"content": "eccomi"}}]}

    async def completions(request):
        peer = request.transport.get_extra_info("peername")
        body = await request.json()
        if not body.get("stream"):
            # two calls at once leave two idle connections in the pool
            pooled.add(peer)
            if len(pooled) == 2:
                both_in.set()
            await both_in.wait()
            return web.json_response(REPLY)
        streamed.append(peer)
        if peer in pooled:
            # every connection the pool kept answers nothing, like dead ones
            await release.wait()
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        await response.write(f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode())
        return response

    app = web.Application()
    app.router.add_post("/v1/chat/completions", completions)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    try:
        port = runner.addresses[0][1]
        llm = ChatCompletionsClient(base_url=f"http://127.0.0.1:{port}/v1", model_name="m")
        await asyncio.gather(*(llm.complete([{"role": "user", "content": "hi"}])
                               for _ in range(2)))
        assert len(pooled) == 2

        with caplog.at_level(logging.WARNING, logger="bea.llm.base"):
            reply = await asyncio.wait_for(llm.stream_complete(
                [{"role": "user", "content": "hi"}], on_tool_delta=lambda *a: None), timeout=5)

            # the other idle connection is as dead: the next call must not get it
            again = await asyncio.wait_for(llm.stream_complete(
                [{"role": "user", "content": "hi"}], on_tool_delta=lambda *a: None), timeout=5)

        assert reply.content == again.content == "eccomi"
        assert len(streamed) == 3
        assert streamed[0] in pooled, "the stalled call did not go out on a pooled connection"
        assert streamed[1] not in pooled, "the resend reused a pooled connection"
        assert streamed[2] == streamed[1], "the call after a stall did not keep the new connection"
        assert caplog.text.count("no answer within") == 1
        assert "reused from the pool" in caplog.text
        assert "on a new connection" in caplog.text
    finally:
        release.set()
        await base.close_sessions()
        await runner.cleanup()


def test_sockets_probe_their_peer_while_idle():
    import socket

    sock = base._keepalive_socket((socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0)))
    try:
        assert sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE)
        idle = getattr(socket, "TCP_KEEPIDLE", None) or getattr(socket, "TCP_KEEPALIVE", None)
        if idle is not None:
            assert sock.getsockopt(socket.IPPROTO_TCP, idle) == base.TCP_KEEPALIVE_IDLE
        if hasattr(socket, "TCP_KEEPINTVL"):
            assert sock.getsockopt(socket.IPPROTO_TCP,
                                   socket.TCP_KEEPINTVL) == base.TCP_KEEPALIVE_INTERVAL
        if hasattr(socket, "TCP_KEEPCNT"):
            assert sock.getsockopt(socket.IPPROTO_TCP,
                                   socket.TCP_KEEPCNT) == base.TCP_KEEPALIVE_PROBES
    finally:
        sock.close()


async def test_a_pool_set_aside_after_a_stall_lets_its_calls_finish(monkeypatch):
    made = wire(monkeypatch, Attempt(REPLY), Attempt(REPLY))
    monkeypatch.setattr(base, "REQUEST_TIMEOUT", 0.05)
    llm = client()

    await llm.complete([{"role": "user", "content": "hi"}])
    base._retire_session()
    # a call still running on the old pool would be cut by closing it now
    assert not made[0].closed

    await llm.complete([{"role": "user", "content": "hi"}])
    assert len(made) == 2, "the call after a stall went back to the old pool"
    await asyncio.sleep(0.1)
    assert made[0].closed, "the old pool was never closed"
    assert not made[1].closed


async def test_shutdown_closes_a_pool_that_was_set_aside(monkeypatch):
    made = wire(monkeypatch, Attempt(REPLY))

    await client().complete([{"role": "user", "content": "hi"}])
    base._retire_session()
    await base.close_sessions()

    assert made[0].closed
    assert not base._retired
