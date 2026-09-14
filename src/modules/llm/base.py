"""The shared base for every provider reached over plain https.

The old clients went through their vendors' sync sdks, drained on a worker
thread. Everything now speaks https directly through aiohttp, so the event loop
is never parked behind a thread hop: this base owns sessions, errors, stream
assembly and the legacy helpers, and each transport only maps its own wire
format onto normalized events.
"""

import json
import time
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Tuple, Union

import aiohttp

from src.core.agent.llm_client import LLMClient
from src.core.agent.types import AssistantMessage, ToolCall, Usage
from src.interfaces.base_interfaces import LLMInterface, STTInterface
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


class AsyncLLMClient(LLMClient, LLMInterface):
    """One https client, parameterised by endpoint instead of subclassed.

    `query_path` is appended to `base_url`. Subclasses translate payloads;
    this class owns the transport, the assembly and the config reload.
    """

    query_path = ""

    def __init__(self, base_url: str, model_name: str, api_key: Optional[str] = None,
                 stt: Optional[STTInterface] = None,
                 reasoning: Optional[ReasoningStyle] = None,
                 key_field: str = "", model_field: str = "", url_field: str = ""):
        self.base_url = (base_url or "").rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.stt = stt
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
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                body = await response.text()
                if response.status >= 400:
                    raise ProviderError(
                        f"{self.model_name}: HTTP {response.status}: {body[:500]}")
                try:
                    return json.loads(body)
                except json.JSONDecodeError as e:
                    raise ProviderError(
                        f"{self.model_name}: not JSON: {body[:500]}") from e

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
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status >= 400:
                    body = await response.text()
                    raise ProviderError(
                        f"{self.model_name}: HTTP {response.status}: {body[:500]}")
                event = ""
                buffer = ""
                async for raw in response.content:
                    buffer += raw.decode("utf-8", errors="replace")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        for item in _parse_line(line, event):
                            if item[0] == "event":
                                event = item[1]
                            else:
                                yield event, item[1]
                                event = ""
                # a truncated final chunk still carries a block worth yielding
                if buffer.strip():
                    for item in _parse_line(buffer, event):
                        if item[0] != "event":
                            yield event, item[1]

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
        here, so there is no thread handover to protect. A failure before
        anything was assembled falls back to the ordinary call — losing a
        second of latency, not the turn. Past that point failures raise, so
        the pool fails over instead of blending two voices onto one line.
        """
        if on_tool_delta is None or self._stream_blocked():
            return await self.complete(messages, tools=tools)

        texts: List[str] = []
        calls: Dict[int, Dict[str, Any]] = {}
        usage = Usage()
        seen_any = False
        tell = on_tool_delta
        try:
            async for event, data in self._post_stream(
                    self.build_body(messages, tools=tools, stream=True)):
                for kind, index, name, payload in self.iter_events(event, data):
                    if kind == "error":
                        if not seen_any:
                            return await self._fallback(messages, tools)
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
        except ProviderError:
            if not seen_any:
                return await self._fallback(messages, tools)
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

    # --- legacy helpers -----------------------------------------------------

    async def chat(self, user_input: str, system_prompt: Optional[str] = None,
                   history: Optional[list] = None) -> Tuple[str, str, dict]:
        """One json turn, as (mood, message, metadata). Raises on failure.

        Raising rather than returning a fallback is deliberate: the pool can
        only fail over to the next model when it sees the error.
        """
        reply = await self.complete_json(user_input, system_prompt, history)
        if isinstance(reply, dict):
            return reply.get("mood", "neutral"), reply.get("message", ""), {}
        return "neutral", str(reply), {}

    async def chat_audio(self, audio_path: str, system_prompt: Optional[str] = None,
                         history: Optional[list] = None) -> Tuple[str, str, dict]:
        if not self.stt:
            return "neutral", "I cannot hear you (STT module not configured).", {}
        transcription = self.stt.transcribe(audio_path)
        if not transcription:
            return "neutral", "I heard nothing.", {}
        return await self.chat(transcription, system_prompt, history)

    async def generate_json(self, user_input: str, system_prompt: Optional[str] = None,
                            history: Optional[list] = None) -> Union[Dict, list]:
        return await self.complete_json(user_input, system_prompt, history)

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
    )
