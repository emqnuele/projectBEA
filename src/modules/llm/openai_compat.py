import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from src.core.agent.llm_client import LLMClient
from src.core.agent.types import AssistantMessage, ToolCall, Usage
from src.interfaces.base_interfaces import LLMInterface, STTInterface
from src.modules.llm.reasoning import NO_STYLE, ReasoningStyle
from src.utils.llm_utils import parse_llm_json
from src.utils.logger import get_logger
from src.utils.sanitize import clean_model_output

logger = get_logger("bea.llm.openai_compat")

# how long a failed-to-stream provider stays on the non-streaming path. A
# permanent blacklist over one bad request would lose speaking-early for the
# whole session; this forgets a transient 429 in a couple of minutes.
NO_STREAM_COOLDOWN = 120.0


def _usage(raw) -> Usage:
    """Token counts off a completed response, including what the cache covered.

    Providers spell the cached figure differently and most do not send it at
    all, so every field is read defensively: a missing usage block must never
    cost a turn.
    """
    if raw is None:
        return Usage()
    details = getattr(raw, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", None) if details else None
    if cached is None:
        # openrouter reports it flat, next to the totals
        cached = getattr(raw, "cached_tokens", None)
    return Usage(
        prompt_tokens=int(getattr(raw, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(raw, "completion_tokens", 0) or 0),
        cached_tokens=int(cached or 0),
    )


class _Assembly:
    """Puts a streamed response back together, one chunk at a time.

    Its other job is the one that matters: handing each tool call's arguments
    on as they arrive, so a line can start being spoken while it is still being
    written. Characters that turn up before the tool has a name are held rather
    than dropped — there is nobody to attribute them to yet.

    Speaking early is an optimisation, so nothing it does may cost the turn: a
    listener that raises is dropped and the response is assembled without it.
    """

    def __init__(self, on_tool_delta):
        self._on_delta = on_tool_delta
        self._content: List[str] = []
        self._calls: Dict[int, Dict[str, Any]] = {}
        self._usage = Usage()
        self.empty = True

    def take(self, chunk) -> None:
        self.empty = False
        raw = getattr(chunk, "usage", None)
        if raw is not None:
            self._usage = _usage(raw)

        choices = getattr(chunk, "choices", None) or []
        delta = getattr(choices[0], "delta", None) if choices else None
        if delta is None:
            return
        if getattr(delta, "content", None):
            self._content.append(delta.content)
        for part in getattr(delta, "tool_calls", None) or []:
            self._take_call(part)

    def _take_call(self, part) -> None:
        index = getattr(part, "index", 0) or 0
        call = self._calls.setdefault(index, {"id": "", "name": "", "arguments": "", "sent": 0})
        if getattr(part, "id", None):
            call["id"] = part.id

        function = getattr(part, "function", None)
        if function is None:
            return
        if getattr(function, "name", None):
            call["name"] = function.name
        arguments = getattr(function, "arguments", None)
        if arguments:
            call["arguments"] += arguments
        if not call["name"]:
            return

        pending = call["arguments"][call["sent"]:]
        if pending:
            call["sent"] = len(call["arguments"])
            self._tell(index, call["name"], pending)

    def _tell(self, index: int, name: str, pending: str) -> None:
        if self._on_delta is None:
            return
        try:
            self._on_delta(index, name, pending)
        except Exception as e:
            logger.error(f"Could not hand over the line as it was written: {e}")
            self._on_delta = None

    def message(self, model: str) -> AssistantMessage:
        tool_calls: List[ToolCall] = []
        for _, call in sorted(self._calls.items()):
            try:
                args = json.loads(call["arguments"] or "{}")
            except json.JSONDecodeError:
                logger.error(f"Bad tool arguments for {call['name']}: {call['arguments']}")
                args = {}
            tool_calls.append(ToolCall(id=call["id"], name=call["name"], arguments=args))
        return AssistantMessage(content=clean_model_output("".join(self._content)),
                                tool_calls=tool_calls, usage=self._usage, model=model)


class OpenAICompatibleClient(LLMClient, LLMInterface):
    """Shared implementation for any provider exposing the OpenAI Chat API.

    Implements the tool-aware `complete()` used by the agent harness and keeps
    the legacy `chat`/`chat_audio`/`generate_json` helpers so existing callers
    (memory, monologue, the pre-agentic chat path) keep working unchanged.

    Subclasses only build `self.client`/`self.model_name` and implement
    `reload_config`.
    """

    def __init__(self, client, model_name: str, stt: Optional[STTInterface] = None,
                 reasoning: Optional[ReasoningStyle] = None):
        self.client = client
        self.model_name = model_name
        self.stt = stt
        self.reasoning = reasoning or NO_STYLE
        # when each model last refused to stream, as monotonic clock readings.
        # Held per model so one stubborn provider never takes streaming away
        # from the pool's next-of-kin, and a config reload onto a different
        # model tries again.
        self._no_stream: Dict[str, float] = {}

    def _stream_blocked(self) -> bool:
        ref = self._no_stream.get(self.model_name, 0.0)
        # a refusal while it is still remembered makes the whole attempt
        # pointless; once the cooldown runs out, try streaming again
        return bool(ref) and time.monotonic() - ref < NO_STREAM_COOLDOWN

    # --- the sdk call, with the reasoning fields negotiated ------------------

    def _call_sdk(self, **kwargs):
        """One sdk call, retried without the reasoning fields if refused.

        Some models force reasoning and answer 400 to anything that switches it
        off. Losing the turn over a latency hint is the wrong trade.
        """
        extra = self.reasoning.extra_body
        if extra:
            kwargs["extra_body"] = {**extra, **(kwargs.get("extra_body") or {})}
        try:
            return self.client.chat.completions.create(**kwargs)
        except Exception:
            if not self.reasoning.negotiable:
                raise
            logger.info(
                f"{self.model_name} refused the reasoning parameters; retrying without them."
            )
            kwargs["extra_body"] = self.reasoning.without_optional() or None
            return self.client.chat.completions.create(**kwargs)

    # --- tool-aware primitive (agent harness) ---

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> AssistantMessage:
        kwargs: Dict[str, Any] = {"model": self.model_name, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if response_format:
            kwargs["response_format"] = response_format

        # the sdk call is blocking; keep the event loop free
        response = await asyncio.to_thread(self._call_sdk, **kwargs)
        message = response.choices[0].message

        tool_calls: List[ToolCall] = []
        for tc in getattr(message, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                logger.error(f"Bad tool arguments for {tc.function.name}: {tc.function.arguments}")
                args = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        usage = _usage(getattr(response, "usage", None))

        # cheap models leak <think> blocks and special tokens; unfiltered they
        # end up spoken out loud
        return AssistantMessage(content=clean_model_output(message.content),
                                tool_calls=tool_calls, usage=usage, model=self.model_name)

    # --- the same call, reported as it is written ---------------------------

    async def stream_complete(self, messages, tools=None, *, on_tool_delta=None):
        """`complete`, handing over each tool call's arguments as they arrive.

        The sdk iterator is blocking, so it is drained on a worker thread and the
        chunks are handed back to the loop one at a time. `on_tool_delta` is then
        called here, on the loop, which is what makes it safe for it to start
        speaking.

        Anything that goes wrong before the first chunk — a provider with no
        streaming, a model that refuses the options — falls back to the ordinary
        call. Losing a second of latency is not worth losing a turn over, and
        the model is remembered so the next turn does not pay for the attempt
        twice.
        """
        if on_tool_delta is None or self._stream_blocked():
            return await self.complete(messages, tools=tools)

        kwargs: Dict[str, Any] = {"model": self.model_name, "messages": messages,
                                  "stream": True,
                                  "stream_options": {"include_usage": True}}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        loop = asyncio.get_running_loop()
        chunks: "asyncio.Queue" = asyncio.Queue()

        def pump():
            try:
                for chunk in self._call_sdk(**kwargs):
                    loop.call_soon_threadsafe(chunks.put_nowait, chunk)
            except Exception as e:
                loop.call_soon_threadsafe(chunks.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(chunks.put_nowait, None)

        worker = loop.run_in_executor(None, pump)
        assembly = _Assembly(on_tool_delta)
        try:
            while True:
                item = await chunks.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    if assembly.empty:
                        self._no_stream[self.model_name] = time.monotonic()
                        logger.info(f"{self.model_name} did not stream ({item}); "
                                    f"trying again without streaming for a while.")
                        return await self.complete(messages, tools=tools)
                    raise item
                assembly.take(item)
        finally:
            await worker

        return assembly.message(self.model_name)

    # --- legacy helpers, implemented on top of the sync sdk ---

    def _create(self, messages: List[Dict[str, Any]], json_mode: bool = False):
        kwargs: Dict[str, Any] = {"model": self.model_name, "messages": messages}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return self._call_sdk(**kwargs)

    def chat(self, user_input: str, system_prompt: Optional[str] = None, history: Optional[list] = None) -> Tuple[str, str, dict]:
        messages = self._build_messages(user_input, system_prompt, history)
        try:
            response = self._create(messages, json_mode=True)
            return parse_llm_json(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"API Error: {e}")
            return "sad", "There's some problem with my AI", {}

    def chat_audio(self, audio_path: str, system_prompt: Optional[str] = None, history: Optional[list] = None) -> Tuple[str, str, dict]:
        if not self.stt:
            return "neutral", "I cannot hear you (STT module not configured).", {}
        transcription = self.stt.transcribe(audio_path)
        if not transcription:
            return "neutral", "I heard nothing.", {}
        return self.chat(transcription, system_prompt, history)

    def generate_json(self, user_input: str, system_prompt: Optional[str] = None, history: Optional[list] = None) -> Union[Dict, list]:
        messages = self._build_messages(user_input, system_prompt, history)
        try:
            response = self._create(messages, json_mode=True)
            _, _, data = parse_llm_json(response.choices[0].message.content)
            return data
        except Exception as e:
            logger.error(f"JSON generation error: {e}")
            return {}

    async def complete_json(self, user_input: str, system_prompt: Optional[str] = None,
                            history: Optional[list] = None) -> Union[Dict, list]:
        return await asyncio.to_thread(self.generate_json, user_input, system_prompt, history)

    @staticmethod
    def _build_messages(user_input: str, system_prompt: Optional[str], history: Optional[list]) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_input})
        return messages

    def reload_config(self, config) -> None:  # pragma: no cover - overridden
        raise NotImplementedError
