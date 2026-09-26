"""The shared base for every provider reached over plain https.

The old clients went through their vendors' sync sdks, drained on a worker
thread. Everything now speaks https directly through aiohttp, so the event loop
is never parked behind a thread hop: this base owns sessions, errors and stream
assembly, and each transport only maps its own wire format onto normalized
events.
"""

import asyncio
import contextlib
import contextvars
import ipaddress
import json
import socket
import time
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Set, Tuple, Union
from urllib.parse import urlsplit

import aiohttp

from src.core.agent.llm_client import LLMClient
from src.core.agent.types import AssistantMessage, ToolCall, Usage
from src.modules.llm.reasoning import NO_STYLE, ReasoningStyle
from src.utils.logger import get_logger
from src.utils.sanitize import clean_model_output

logger = get_logger("bea.llm.base")

# a hung provider must never wedge the loop forever; the doctor applies a
# tighter budget of its own around the mind check
REQUEST_TIMEOUT = 120.0

# how long a failed-to-stream model stays on the non-streaming path. A
# permanent blacklist over one bad request would lose speaking-early for the
# whole session; this forgets a transient refusal in a couple of minutes.
NO_STREAM_COOLDOWN = 120.0

# how long a streamed call may go without its response headers. A provider that
# streams answers them at once — queueing included, it sends keep-alives — so a
# silence this long is a stalled request, not a slow model. Without it the only
# limit was REQUEST_TIMEOUT: two minutes of her standing there, then no turn.
STREAM_HEADERS_TIMEOUT = 30.0

# headers are not an answer. OpenRouter sends them early and then holds the
# stream open with keep-alive comments while the model queues or stalls, so a
# call can look alive for the whole REQUEST_TIMEOUT without a byte of answer.
# What counts is data: the first block has to come within a budget that grows
# with the prompt, since a cold prefill takes longer the longer the prompt,
# and once it streams, no gap between two blocks may be longer than the idle
# limit.
STREAM_FIRST_BLOCK_BASE = 15.0
STREAM_IDLE_TIMEOUT = 30.0

# measured cold on openrouter deepseek-v4-flash: 109k tokens -> 27.3s budget,
# first token at 7.3s; 383k tokens -> 58.0s budget, first token at 19.1-26.8s
PREFILL_CHARS_PER_SECOND = 40_000

# how long an idle connection to a provider waits for the next call. A new one
# is dns, tcp and tls before the first token — 110 to 190ms a call, measured —
# and people pause for longer than aiohttp's own fifteen seconds all the time.
KEEPALIVE_SECONDS = 90.0

# a provider's address does not move between two turns
DNS_CACHE_SECONDS = 300

# the kernel probes idle sockets, so a connection the network dropped silently is discarded, not reused
TCP_KEEPALIVE_IDLE = 10
TCP_KEEPALIVE_INTERVAL = 5
TCP_KEEPALIVE_PROBES = 3

# one pool of connections per event loop, shared by every client on it. A
# session belongs to the loop that made it, and the doctor runs on its own.
_sessions: Dict[asyncio.AbstractEventLoop, aiohttp.ClientSession] = {}

# pools set aside after a stall, each with the timer that closes it once its calls are done
_retired: Dict[asyncio.AbstractEventLoop, List[Tuple[aiohttp.ClientSession, asyncio.TimerHandle]]] = {}

# the loop only keeps weak references to tasks, so a closing pool is held here until it is shut
_closing: Set["asyncio.Task[None]"] = set()


# what the request in flight is riding on: "reused", "new", or "unknown" before aiohttp says
_connection: contextvars.ContextVar[Optional[Dict[str, str]]] = contextvars.ContextVar(
    "llm_connection", default=None)


def _keepalive_socket(addr_info) -> socket.socket:
    """a tcp socket that probes its peer while idle."""
    family, type_, proto, _, _ = addr_info
    sock = socket.socket(family=family, type=type_, proto=proto)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    # macos calls the idle option TCP_KEEPALIVE; linux and windows call it TCP_KEEPIDLE
    idle = getattr(socket, "TCP_KEEPIDLE", None) or getattr(socket, "TCP_KEEPALIVE", None)
    for option, value in ((idle, TCP_KEEPALIVE_IDLE),
                          (getattr(socket, "TCP_KEEPINTVL", None), TCP_KEEPALIVE_INTERVAL),
                          (getattr(socket, "TCP_KEEPCNT", None), TCP_KEEPALIVE_PROBES)):
        if option is None:
            continue
        try:
            sock.setsockopt(socket.IPPROTO_TCP, option, value)
        except OSError:
            # an os that refuses the tuning still probes, on its own schedule
            pass
    return sock


def _note_connection(kind: str):
    async def note(session, ctx, params) -> None:
        seen = _connection.get()
        if seen is not None:
            seen["kind"] = kind
    return note


def _open_session() -> aiohttp.ClientSession:
    """a pool on keepalive sockets that notes whether each request reused a connection."""
    tracing = aiohttp.TraceConfig()
    tracing.on_connection_reuseconn.append(_note_connection("reused"))
    tracing.on_connection_create_end.append(_note_connection("new"))
    return aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        connector=aiohttp.TCPConnector(keepalive_timeout=KEEPALIVE_SECONDS,
                                       ttl_dns_cache=DNS_CACHE_SECONDS,
                                       socket_factory=_keepalive_socket),
        trace_configs=[tracing],
    )


def _session() -> aiohttp.ClientSession:
    """This loop's connection pool, made the first time it is asked for."""
    loop = asyncio.get_running_loop()
    session = _sessions.get(loop)
    if session is not None and not getattr(session, "closed", False):
        return session
    for gone in [other for other in _sessions if other.is_closed()]:
        del _sessions[gone]
    for gone in [other for other in _retired if other.is_closed()]:
        del _retired[gone]
    session = _open_session()
    _sessions[loop] = session
    return session


def _retire_session() -> None:
    """sets this loop's pool aside after a stall; closed once its running calls have timed out."""
    loop = asyncio.get_running_loop()
    session = _sessions.pop(loop, None)
    close = getattr(session, "close", None)
    if session is None or close is None:
        return
    retired = _retired.setdefault(loop, [])

    def close_now() -> None:
        retired[:] = [(s, h) for s, h in retired if s is not session]
        task = loop.create_task(close())
        _closing.add(task)
        task.add_done_callback(_closing.discard)

    retired.append((session, loop.call_later(REQUEST_TIMEOUT, close_now)))


async def close_sessions() -> None:
    """Closes this loop's connections. Shutdown calls it once the mind is quiet."""
    loop = asyncio.get_running_loop()
    sessions = [_sessions.pop(loop, None)]
    for session, timer in _retired.pop(loop, []):
        timer.cancel()
        sessions.append(session)
    for session in sessions:
        close = getattr(session, "close", None)
        if close is not None:
            await close()


def _stale(error: BaseException) -> bool:
    """A pooled connection the provider closed while it sat idle.

    It fails before a byte of the answer exists, so sending the request again
    on a fresh connection is the same request, not a second one. A host that
    cannot be reached at all is not this, and is left to the pool's failover.
    """
    if isinstance(error, aiohttp.ClientConnectorError):
        return False
    return isinstance(error, (aiohttp.ServerDisconnectedError, aiohttp.ClientOSError))


def _is_local(base_url: str) -> bool:
    """A model served on this machine or network: loading one can take a minute."""
    host = (urlsplit(base_url).hostname or "").lower()
    if host == "localhost" or host.endswith(".local"):
        return True
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        return False


class ProviderStalled(RuntimeError):
    """The provider took the request and never started answering.

    Not a `ProviderError`: that one means "refused", and a refused stream is
    retried without reasoning and then without streaming — each of which would
    wait on the same stalled provider all over again.
    """


_ON_CONNECTION = {"reused": " on a connection reused from the pool", "new": " on a new connection"}


@contextlib.asynccontextmanager
async def _answered_within(request, seconds: Optional[float], label: str,
                           seen: Optional[Dict[str, str]] = None):
    """`async with request` whose response has to start within `seconds`.

    `seen["kind"]` is filled in with the connection the request went out on.
    """
    seen = {"kind": "unknown"} if seen is None else seen
    token = _connection.set(seen)
    try:
        if seconds is None:
            response = await request.__aenter__()
        else:
            response = await asyncio.wait_for(request.__aenter__(), seconds)
    except asyncio.TimeoutError as e:
        raise ProviderStalled(f"{label}: no answer within {seconds:.0f}s"
                              f"{_ON_CONNECTION.get(seen['kind'], '')}") from e
    finally:
        _connection.reset(token)
    failure = (None, None, None)
    try:
        yield response
    except BaseException as e:
        failure = (type(e), e, e.__traceback__)
        raise
    finally:
        await request.__aexit__(*failure)


def first_block_budget(payload: Dict[str, Any]) -> float:
    """How long a streamed call may take to send its first block of answer."""
    try:
        size = len(json.dumps(payload))
    except (TypeError, ValueError):
        size = 0
    return STREAM_FIRST_BLOCK_BASE + size / PREFILL_CHARS_PER_SECOND


async def _next_line(lines, deadline: Optional[float], why: str) -> bytes:
    """The next raw line of a stream, or `ProviderStalled` once `deadline` passes.

    `deadline` is a monotonic reading; None waits as long as the request may.
    """
    if deadline is None:
        return await lines.__anext__()
    try:
        return await asyncio.wait_for(lines.__anext__(), max(0.0, deadline - time.monotonic()))
    except asyncio.TimeoutError as e:
        raise ProviderStalled(why) from e


class _StreamRefused(RuntimeError):
    """The stream ended before it began: nothing was assembled, so retrying is
    free and whatever is tried next is still the same turn."""


class ProviderError(RuntimeError):
    """A failed request, with the status and the provider's own words.

    The body travels in the exception on purpose: the pool decides between
    "try the next model" and "this spec is misconfigured" from it, so a status
    without the provider's explanation would fail over blind.
    """


# a normalized stream event: (kind, index, name, payload). kind is one of
# "text" (payload: str), "tool_delta" (payload: argument fragment),
# "tool_id" (payload: the call id), "usage" (payload: Usage),
# "error" (payload: message).
StreamEvent = Tuple[str, int, str, Any]


class AsyncLLMClient(LLMClient):
    """One https client, parameterised by endpoint instead of subclassed.

    `query_path` is appended to `base_url`. Subclasses translate payloads;
    this class owns the transport, the assembly and the config reload.
    """

    query_path = ""

    def __init__(self, base_url: str, model_name: str, api_key: Optional[str] = None,
                 reasoning: Optional[ReasoningStyle] = None,
                 key_field: str = "", model_field: str = "", url_field: str = ""):
        self.base_url = (base_url or "").rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.reasoning = reasoning or NO_STYLE
        # the config fields this instance was built from, so a reload reads the
        # same places the factory did instead of each transport repeating it
        self._key_field = key_field
        self._model_field = model_field
        self._url_field = url_field
        # when each model last refused to stream, as monotonic clock readings.
        # Held per model so one stubborn endpoint never takes streaming away
        # from the pool's next-of-kin, and a config reload onto a different
        # model tries again.
        self._no_stream: Dict[str, float] = {}

    def _stream_blocked(self) -> bool:
        ref = self._no_stream.get(self.model_name, 0.0)
        # a refusal while it is still remembered makes the whole attempt
        # pointless; once the cooldown runs out, try streaming again
        return bool(ref) and time.monotonic() - ref < NO_STREAM_COOLDOWN

    async def _fallback(self, messages, tools) -> AssistantMessage:
        """The ordinary call, remembering not to pay for the attempt twice."""
        self._no_stream[self.model_name] = time.monotonic()
        return await self.complete(messages, tools=tools)

    # --- the transport ----------------------------------------------------

    def auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{self.query_path}"
        headers = {"Content-Type": "application/json", **self.auth_headers()}
        retried = False
        while True:
            answered = False
            try:
                async with _session().post(url, headers=headers, json=payload) as response:
                    answered = True
                    body = await response.text()
                    if response.status >= 400:
                        raise ProviderError(
                            f"{self.model_name}: HTTP {response.status}: {body[:500]}")
                    try:
                        return json.loads(body)
                    except json.JSONDecodeError as e:
                        raise ProviderError(
                            f"{self.model_name}: not JSON: {body[:500]}") from e
            except Exception as e:
                if answered or retried or not _stale(e):
                    raise
                retried = True
                logger.debug(f"{self.model_name}: an idle connection had gone ({e}); sending again")

    async def _send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """One request, retried without the reasoning fields if refused.

        Some models force reasoning and answer 400 to anything that switches it
        off. Losing the turn over a latency hint is the wrong trade; anything
        else raises untouched so the pool can fail over.
        """
        try:
            return await self._post(payload)
        except ProviderError:
            if not self.reasoning.negotiable:
                raise
            logger.info(
                f"{self.model_name} refused the reasoning parameters; retrying without them.")
            payload = {k: v for k, v in payload.items()
                       if k not in self.reasoning.optional_keys}
            return await self._post(payload)

    async def _post_stream(self, payload: Dict[str, Any]) -> AsyncIterator[Tuple[str, Dict]]:
        """Yields `(event, data)` per server-sent block, in order.

        `event` is the `event:` line when the protocol sends one (anthropic
        does, openai-shaped streams do not) and `""` otherwise. A `[DONE]`
        sentinel ends the stream; a chunk that is not JSON is skipped, never
        fatal — one malformed line must not cost the turn.
        """
        url = f"{self.base_url}{self.query_path}"
        headers = {"Content-Type": "application/json", **self.auth_headers()}
        local = _is_local(self.base_url)
        limit = None if local else STREAM_HEADERS_TIMEOUT
        first_budget = None if local else first_block_budget(payload)
        retried = False
        # once a block has left, sending the request again would hand the
        # caller the start of the answer twice
        delivered = False
        while True:
            answered = False
            try:
                started = time.monotonic()
                seen = {"kind": "unknown"}
                async with _answered_within(_session().post(url, headers=headers, json=payload),
                                            limit, self.model_name, seen) as response:
                    answered = True
                    logger.debug(f"{self.model_name}: headers in {time.monotonic() - started:.2f}s"
                                 f"{_ON_CONNECTION.get(seen['kind'], '')}")
                    if response.status >= 400:
                        body = await response.text()
                        raise ProviderError(
                            f"{self.model_name}: HTTP {response.status}: {body[:500]}")
                    event = ""
                    buffer = ""
                    lines = response.content.__aiter__()
                    deadline = None if first_budget is None else started + first_budget
                    why = f"{self.model_name}: no answer within {first_budget or 0:.0f}s of asking"
                    while True:
                        try:
                            raw = await _next_line(lines, deadline, why)
                        except StopAsyncIteration:
                            break
                        buffer += raw.decode("utf-8", errors="replace")
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            for item in _parse_line(line, event):
                                # keep-alive comments never get here: only a
                                # block of the answer moves the deadline
                                if deadline is not None:
                                    deadline = time.monotonic() + STREAM_IDLE_TIMEOUT
                                    why = (f"{self.model_name}: went silent for "
                                           f"{STREAM_IDLE_TIMEOUT:.0f}s mid-answer")
                                if item[0] == "event":
                                    event = item[1]
                                else:
                                    delivered = True
                                    yield event, item[1]
                                    event = ""
                    # a truncated final chunk still carries a block worth yielding
                    if buffer.strip():
                        for item in _parse_line(buffer, event):
                            if item[0] != "event":
                                delivered = True
                                yield event, item[1]
                    return
            except ProviderStalled as e:
                # nothing of the answer exists yet: the same request on a new
                # pool, once, and then it is the pool's to fail over
                if retried or delivered:
                    raise
                retried = True
                _retire_session()
                logger.warning(f"{e}; sending it again on a new connection.")
            except Exception as e:
                if answered or retried or not _stale(e):
                    raise
                retried = True
                logger.debug(f"{self.model_name}: an idle connection had gone ({e}); sending again")

    # --- payloads: each transport maps its own wire format ----------------

    def build_body(self, messages: List[Dict[str, Any]],
                   tools: Optional[List[Dict[str, Any]]] = None,
                   stream: bool = False, json_mode: bool = False) -> Dict[str, Any]:
        raise NotImplementedError

    def parse_message(self, data: Dict[str, Any]) -> AssistantMessage:
        raise NotImplementedError

    def iter_events(self, event: str, data: Dict[str, Any]) -> Iterator[StreamEvent]:
        """Zero or more normalized `StreamEvent`s from one stream block."""
        raise NotImplementedError

    async def json_turn(self, messages: List[Dict[str, Any]]) -> Union[Dict, list]:
        raise NotImplementedError

    # --- the tool-aware primitive (agent harness) --------------------------

    async def complete(self, messages: List[Dict[str, Any]],
                       tools: Optional[List[Dict[str, Any]]] = None,
                       response_format: Optional[Dict[str, Any]] = None) -> AssistantMessage:
        del response_format  # json mode travels via complete_json, not via a flag here
        return self.parse_message(await self._send(
            self.build_body(messages, tools=tools)))

    async def stream_complete(self, messages, tools=None, *, on_tool_delta=None):
        """`complete`, handing over each tool call's arguments as they arrive.

        `on_tool_delta` runs on the loop, inline: the chunks already arrive
        here, so there is no thread handover to protect.

        Failing before anything has been assembled costs a second of latency
        and not the turn: the reasoning hint is dropped and the stream tried
        again, exactly as `_send` does for the ordinary call, and only then
        does it fall back to not streaming at all. Without that retry a model
        that refuses the hint lost speaking-early for two minutes at a time,
        forever, having already paid for the refused request. Past the first
        event failures raise, so the pool fails over instead of blending two
        voices onto one line.
        """
        if on_tool_delta is None or self._stream_blocked():
            return await self.complete(messages, tools=tools)

        body = self.build_body(messages, tools=tools, stream=True)
        try:
            return await self._stream_once(body, on_tool_delta)
        except _StreamRefused:
            pass

        if self.reasoning.negotiable:
            logger.info(f"{self.model_name} refused the reasoning parameters while "
                        f"streaming; trying again without them.")
            plain = {k: v for k, v in body.items() if k not in self.reasoning.optional_keys}
            try:
                return await self._stream_once(plain, on_tool_delta)
            except _StreamRefused:
                pass

        return await self._fallback(messages, tools)

    async def _stream_once(self, body: Dict[str, Any], on_tool_delta) -> AssistantMessage:
        """One streamed turn. Raises `_StreamRefused` if nothing ever arrived."""
        texts: List[str] = []
        calls: Dict[int, Dict[str, Any]] = {}
        usage = Usage()
        seen_any = False
        tell = on_tool_delta
        try:
            async for event, data in self._post_stream(body):
                for kind, index, name, payload in self.iter_events(event, data):
                    if kind == "error":
                        if not seen_any:
                            raise _StreamRefused(str(payload))
                        raise ProviderError(f"{self.model_name}: {payload}")
                    seen_any = True
                    if kind == "usage":
                        usage = _merge_usage(usage, payload)
                    elif kind == "text":
                        texts.append(payload)
                    elif kind == "tool_id":
                        call = calls.setdefault(index, {"id": "", "name": "",
                                                        "arguments": "", "sent": 0})
                        if payload:
                            call["id"] = payload
                    else:
                        if not self._take_call(calls, index, name, payload, tell):
                            tell = None
        except ProviderError as e:
            if not seen_any:
                raise _StreamRefused(str(e)) from e
            raise

        tool_calls = []
        for _, call in sorted(calls.items()):
            try:
                args = json.loads(call["arguments"] or "{}")
            except json.JSONDecodeError:
                logger.error(f"Bad tool arguments for {call['name']}: {call['arguments']}")
                args = {}
            tool_calls.append(ToolCall(id=call["id"], name=call["name"], arguments=args))
        return AssistantMessage(content=clean_model_output("".join(texts)),
                                tool_calls=tool_calls, usage=usage, model=self.model_name)

    @staticmethod
    def _take_call(calls: Dict[int, Dict[str, Any]], index: int, name: str,
                   fragment: str, tell) -> bool:
        """Folds one argument fragment into the call being assembled.

        Characters that turn up before the tool has a name are held rather
        than dropped — there is nobody to attribute them to yet — and handed
        over together with the fragment that finally names them. Returns
        whether the listener is still alive: speaking early is an
        optimisation, so a listener that raises is dropped and the response is
        assembled without it.
        """
        call = calls.setdefault(index, {"id": "", "name": "", "arguments": "",
                                        "sent": 0})
        if name:
            call["name"] = name
        if fragment:
            call["arguments"] += fragment
        if not call["name"]:
            return tell is not None
        pending = call["arguments"][call["sent"]:]
        if not pending:
            return tell is not None
        call["sent"] = len(call["arguments"])
        if tell is None:
            return False
        try:
            tell(index, call["name"], pending)
        except Exception as e:
            logger.error(f"Could not hand over the line as it was written: {e}")
            return False
        return True

    # --- json mode ----------------------------------------------------------

    async def complete_json(self, user_input: str, system_prompt: Optional[str] = None,
                            history: Optional[list] = None) -> Union[Dict, list]:
        return await self.json_turn(self._build_messages(user_input, system_prompt, history))

    def reload_config(self, config) -> None:
        if self._key_field:
            key = getattr(config, self._key_field, None)
            if key != self.api_key:
                self.api_key = key
        if self._url_field:
            url = (getattr(config, self._url_field, None) or "").rstrip("/")
            if url and url != self.base_url:
                self.base_url = url
        if self._model_field:
            model = getattr(config, self._model_field, None)
            if model and model != self.model_name:
                self.model_name = model

    @staticmethod
    def _build_messages(user_input: str, system_prompt: Optional[str],
                        history: Optional[list]) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_input})
        return messages


def _parse_line(line: str, event: str):
    """One SSE line onto `("event", name)` or `("data", parsed)`."""
    line = line.strip()
    if not line or line.startswith(":"):
        return
    if line.startswith("event:"):
        yield ("event", line[6:].strip())
        return
    if not line.startswith("data:"):
        return
    data = line[5:].strip()
    if data == "[DONE]":
        return
    try:
        yield ("data", json.loads(data))
    except json.JSONDecodeError:
        logger.error(f"Skipping a chunk that is not JSON: {data[:200]}")


def _merge_usage(into: Usage, update: Usage) -> Usage:
    """One usage figure out of incremental ones: nonzero fields win.

    Non-streaming replies carry the totals at once; anthropic streams them in
    two halves (input on start, output on delta). Merging covers both without
    the transports caring which shape they got.
    """
    return Usage(
        prompt_tokens=update.prompt_tokens or into.prompt_tokens,
        completion_tokens=update.completion_tokens or into.completion_tokens,
        cached_tokens=update.cached_tokens or into.cached_tokens,
        reasoning_tokens=update.reasoning_tokens or into.reasoning_tokens,
    )
