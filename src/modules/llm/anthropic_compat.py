"""Shared implementation for any provider exposing the Anthropic Messages API.

Mirrors `OpenAICompatibleClient` for the Anthropic wire format:
 - converts OpenAI-style function definitions into Anthropic `input_schema` tools
 - converts chat messages to Anthropic's alternating user/assistant format
 - separates `system` messages into the top-level `system` parameter
 - maps `assistant` tool calls to `tool_use` content blocks
 - maps `tool` role messages to user `tool_result` content blocks
 - coalesces consecutive same-role turns to preserve the required alternating
   user/assistant structure
 - handles both non-streaming `complete()` and SSE streaming `stream_complete()`

Zero new dependencies: uses only `json`, `asyncio`, and the existing `requests`
library already present in the environment.
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

from src.core.agent.llm_client import LLMClient
from src.core.agent.types import AssistantMessage, ToolCall, Usage
from src.interfaces.base_interfaces import LLMInterface, STTInterface
from src.modules.llm.reasoning import NO_STYLE, ReasoningStyle
from src.utils.llm_utils import parse_llm_json
from src.utils.logger import get_logger
from src.utils.sanitize import clean_model_output

logger = get_logger("bea.llm.anthropic_compat")

ANTHROPIC_API_VERSION = "2023-06-01"
NO_STREAM_COOLDOWN = 120.0


# --- conversions -------------------------------------------------------------


def _clean_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Remove schema keys that Anthropic Messages API rejects (e.g. title, default, $schema, examples)."""
    if not isinstance(schema, dict):
        return schema
    cleaned: Dict[str, Any] = {}
    for k, v in schema.items():
        if k in ("title", "default", "$schema", "examples"):
            continue
        if isinstance(v, dict):
            cleaned[k] = _clean_schema(v)
        elif isinstance(v, list):
            cleaned[k] = [_clean_schema(item) if isinstance(item, dict) else item for item in v]
        else:
            cleaned[k] = v
    return cleaned


def _openai_tools_to_anthropic(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert OpenAI function definitions to Anthropic tool format."""
    out: List[Dict[str, Any]] = []
    for tool in tools:
        fn = tool.get("function", {})
        raw_params = fn.get("parameters", {"type": "object", "properties": {}})
        out.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": _clean_schema(raw_params),
        })
    return out


_convert_tools = _openai_tools_to_anthropic


def _openai_messages_to_anthropic(
    messages: List[Dict[str, Any]],
) -> Tuple[str, List[Dict[str, Any]]]:
    """Separate system messages and convert to Anthropic's alternating format.

    Returns (system_text, converted_messages).
    """
    system_parts: List[str] = []
    converted: List[Dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content") or ""

        if role == "system":
            system_parts.append(content)
            continue

        if role == "assistant":
            blocks: List[Dict[str, Any]] = []
            if content:
                blocks.append({"type": "text", "text": content})
            for tc in msg.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                try:
                    tc_input = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tc_input = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": tc_input,
                })
            converted.append({"role": "assistant", "content": blocks or content})
            continue

        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": msg.get("tool_call_id", ""),
                "content": content,
            }
            converted.append({"role": "user", "content": [block]})
            continue

        # user or anything else
        converted.append({"role": "user", "content": content})

    # coalesce consecutive same-role turns
    coalesced: List[Dict[str, Any]] = []
    for entry in converted:
        if coalesced and coalesced[-1]["role"] == entry["role"]:
            prev = coalesced[-1]["content"]
            curr = entry["content"]
            if isinstance(prev, str) and isinstance(curr, str):
                coalesced[-1]["content"] = prev + "\n" + curr
            else:
                prev_list = prev if isinstance(prev, list) else [{"type": "text", "text": prev}]
                curr_list = curr if isinstance(curr, list) else [{"type": "text", "text": curr}]
                coalesced[-1]["content"] = prev_list + curr_list
        else:
            coalesced.append(entry)

    return "\n\n".join(system_parts), coalesced


_convert_messages = _openai_messages_to_anthropic


def _anthropic_response_to_assistant(response: Dict[str, Any], model: str) -> AssistantMessage:
    """Convert an Anthropic API response dict into an AssistantMessage."""
    text_parts: List[str] = []
    tool_calls: List[ToolCall] = []

    for block in response.get("content", []):
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            tool_calls.append(ToolCall(
                id=block.get("id", ""),
                name=block.get("name", ""),
                arguments=block.get("input", {}),
            ))

    raw_usage = response.get("usage", {})
    usage = Usage(
        prompt_tokens=raw_usage.get("input_tokens", 0),
        completion_tokens=raw_usage.get("output_tokens", 0),
        cached_tokens=raw_usage.get("cache_read_input_tokens", 0),
    )

    return AssistantMessage(
        content=clean_model_output("\n".join(text_parts)) or None,
        tool_calls=tool_calls,
        usage=usage,
        model=model,
    )


# --- the client itself -------------------------------------------------------


class AnthropicCompatibleClient(LLMClient, LLMInterface):
    """Shared implementation for any provider exposing the Anthropic Messages API.

    Mirrors `OpenAICompatibleClient` for the Anthropic wire format. Subclasses
    only set `api_key`, `base_url`, and `model_name`, and implement
    `reload_config`.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
        model_name: str = "claude-3-7-sonnet-latest",
        stt_interface: Optional[STTInterface] = None,
        reasoning: Optional[ReasoningStyle] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.stt = stt_interface
        self.reasoning = reasoning or NO_STYLE
        self._no_stream: Dict[str, float] = {}

    def _stream_blocked(self) -> bool:
        ref = self._no_stream.get(self.model_name, 0.0)
        return bool(ref) and time.monotonic() - ref < NO_STREAM_COOLDOWN

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }

    def _call_api(self, body: Dict[str, Any], stream: bool = False):
        """One blocking HTTP call to the messages endpoint."""
        url = f"{self.base_url}/messages"
        if stream:
            body["stream"] = True
        resp = requests.post(url, headers=self._headers(), json=body, timeout=300,
                             stream=stream)
        resp.raise_for_status()
        if stream:
            return resp
        return resp.json()

    def _build_body(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 8192,
    ) -> Dict[str, Any]:
        system_text, converted = _openai_messages_to_anthropic(messages)
        body: Dict[str, Any] = {
            "model": self.model_name,
            "messages": converted,
            "max_tokens": max_tokens,
        }
        if system_text:
            body["system"] = system_text
        if tools:
            body["tools"] = _openai_tools_to_anthropic(tools)
            body["tool_choice"] = {"type": "auto"}
        return body

    # --- tool-aware primitive (agent harness) ---

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> AssistantMessage:
        body = self._build_body(messages, tools)
        response = await asyncio.to_thread(self._call_api, body)
        return _anthropic_response_to_assistant(response, self.model_name)

    # --- streaming ---

    async def stream_complete(self, messages, tools=None, *, on_tool_delta=None):
        if on_tool_delta is None or self._stream_blocked():
            return await self.complete(messages, tools=tools)

        body = self._build_body(messages, tools)

        loop = asyncio.get_running_loop()
        chunks: "asyncio.Queue" = asyncio.Queue()

        def pump():
            try:
                resp = self._call_api(body, stream=True)
                for line in resp.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    loop.call_soon_threadsafe(chunks.put_nowait, event)
            except Exception as e:
                loop.call_soon_threadsafe(chunks.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(chunks.put_nowait, None)

        worker = loop.run_in_executor(None, pump)

        text_parts: List[str] = []
        tool_calls: Dict[int, Dict[str, Any]] = {}
        usage = Usage()
        got_any = False

        try:
            while True:
                item = await chunks.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    if not got_any:
                        self._no_stream[self.model_name] = time.monotonic()
                        logger.info(f"{self.model_name} did not stream ({item}); "
                                    f"trying again without streaming for a while.")
                        return await self.complete(messages, tools=tools)
                    raise item

                got_any = True
                event_type = item.get("type", "")

                if event_type == "content_block_start":
                    block = item.get("content_block", {})
                    index = item.get("index", 0)
                    if block.get("type") == "tool_use":
                        tool_calls[index] = {
                            "id": block.get("id", ""),
                            "name": block.get("name", ""),
                            "arguments": "",
                            "sent": 0,
                        }
                elif event_type == "content_block_delta":
                    delta = item.get("delta", {})
                    index = item.get("index", 0)
                    if delta.get("type") == "text_delta":
                        text_parts.append(delta.get("text", ""))
                    elif delta.get("type") == "input_json_delta":
                        partial = delta.get("partial_json", "")
                        if index in tool_calls:
                            call = tool_calls[index]
                            call["arguments"] += partial
                            if call["name"]:
                                pending = call["arguments"][call["sent"]:]
                                if pending:
                                    call["sent"] = len(call["arguments"])
                                    try:
                                        on_tool_delta(index, call["name"], pending)
                                    except Exception as e:
                                        logger.error(f"Could not hand over the line: {e}")
                                        on_tool_delta = None
                elif event_type == "message_delta":
                    raw = item.get("usage", {})
                    usage = Usage(
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=raw.get("output_tokens", usage.completion_tokens),
                        cached_tokens=usage.cached_tokens,
                    )
                elif event_type == "message_start":
                    msg = item.get("message", {})
                    raw = msg.get("usage", {})
                    usage = Usage(
                        prompt_tokens=raw.get("input_tokens", 0),
                        completion_tokens=raw.get("output_tokens", 0),
                        cached_tokens=raw.get("cache_read_input_tokens", 0),
                    )
        finally:
            await worker

        tc_list: List[ToolCall] = []
        for _, call in sorted(tool_calls.items()):
            try:
                args = json.loads(call["arguments"] or "{}")
            except json.JSONDecodeError:
                logger.error(f"Bad tool arguments for {call['name']}: {call['arguments']}")
                args = {}
            tc_list.append(ToolCall(id=call["id"], name=call["name"], arguments=args))

        return AssistantMessage(
            content=clean_model_output("".join(text_parts)) or None,
            tool_calls=tc_list,
            usage=usage,
            model=self.model_name,
        )

    # --- legacy helpers ---

    def _create(self, messages: List[Dict[str, Any]], json_mode: bool = False):
        body = self._build_body(messages, max_tokens=8192)
        return self._call_api(body)

    @staticmethod
    def _build_messages(
        user_input: str, system_prompt: Optional[str], history: Optional[list],
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_input})
        return messages

    def chat(
        self, user_input: str, system_prompt: Optional[str] = None,
        history: Optional[list] = None,
    ) -> Tuple[str, str, dict]:
        messages = self._build_messages(user_input, system_prompt, history)
        try:
            response = self._create(messages, json_mode=True)
            text = ""
            for block in response.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
            return parse_llm_json(text)
        except Exception as e:
            logger.error(f"API Error: {e}")
            return "sad", "There's some problem with my AI", {}

    def chat_audio(
        self, audio_path: str, system_prompt: Optional[str] = None,
        history: Optional[list] = None,
    ) -> Tuple[str, str, dict]:
        if not self.stt:
            return "neutral", "I cannot hear you (STT module not configured).", {}
        transcription = self.stt.transcribe(audio_path)
        if not transcription:
            return "neutral", "I heard nothing.", {}
        return self.chat(transcription, system_prompt, history)

    def generate_json(
        self, user_input: str, system_prompt: Optional[str] = None,
        history: Optional[list] = None,
    ) -> Union[Dict, list]:
        messages = self._build_messages(user_input, system_prompt, history)
        try:
            response = self._create(messages, json_mode=True)
            text = ""
            for block in response.get("content", []):
                if block.get("type") == "text":
                    text += block.get("text", "")
            _, _, data = parse_llm_json(text)
            return data
        except Exception as e:
            logger.error(f"JSON generation error: {e}")
            return {}

    async def complete_json(
        self, user_input: str, system_prompt: Optional[str] = None,
        history: Optional[list] = None,
    ) -> Union[Dict, list]:
        return await asyncio.to_thread(self.generate_json, user_input, system_prompt, history)

    def reload_config(self, config) -> None:  # pragma: no cover - overridden
        raise NotImplementedError
