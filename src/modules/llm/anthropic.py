"""The Anthropic Messages transport (`POST {base}/messages`).

Claude direct and any anthropic-compatible endpoint. The app reasons in
OpenAI-shaped messages and tools, so this transport translates both ways:
system messages become the `system` parameter, tool turns become
`tool_use`/`tool_result` blocks, and tool schemas are flattened onto
`input_schema`. Auth is `x-api-key`, not bearer.
"""

import json
from typing import Any, Dict, List, Optional

from src.core.agent.types import AssistantMessage, ToolCall, Usage
from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.base import AsyncLLMClient
from src.modules.llm.reasoning import ReasoningStyle
from src.utils.llm_utils import parse_llm_json
from src.utils.logger import get_logger
from src.utils.sanitize import clean_model_output

logger = get_logger("bea.llm.anthropic")

ANTHROPIC_VERSION = "2023-06-01"

# the api refuses a turn without one; background jobs are small, mind turns
# are not, and the pool fails over if a ceiling is ever actually hit
MAX_TOKENS = 4096


class AnthropicClient(AsyncLLMClient):
    """POSTs messages and reads the SSE event stream over aiohttp."""

    query_path = "/messages"

    def auth_headers(self) -> Dict[str, str]:
        headers = {"x-api-key": self.api_key or "", "anthropic-version": ANTHROPIC_VERSION}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def build_body(self, messages: List[Dict[str, Any]],
                   tools: Optional[List[Dict[str, Any]]] = None,
                   stream: bool = False, json_mode: bool = False) -> Dict[str, Any]:
        del json_mode  # no json mode here: json_turn goes prompt plus parse
        system, converted = _to_messages(messages)
        body: Dict[str, Any] = {"model": self.model_name, "max_tokens": MAX_TOKENS,
                                "messages": converted}
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [_to_tool(t) for t in tools]
        if stream:
            body["stream"] = True
        extra = self.reasoning.extra_body
        if extra:
            body.update({k: v for k, v in extra.items() if k not in body})
        return body

    def parse_message(self, data: Dict[str, Any]) -> AssistantMessage:
        texts: List[str] = []
        tool_calls: List[ToolCall] = []
        for block in data.get("content") or []:
            kind = block.get("type")
            if kind == "text":
                texts.append(block.get("text", ""))
            elif kind == "tool_use":
                arguments = block.get("input") or {}
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        logger.error(f"Bad tool arguments for {block.get('name')}: "
                                     f"{arguments}")
                        arguments = {}
                tool_calls.append(ToolCall(id=block.get("id", ""),
                                           name=block.get("name", ""),
                                           arguments=arguments))

        return AssistantMessage(content=clean_model_output("".join(texts)),
                                tool_calls=tool_calls,
                                usage=_usage(data.get("usage")),
                                model=data.get("model", self.model_name))

    def iter_events(self, event: str, data: Dict[str, Any]):
        event = event or str(data.get("type", ""))
        if event == "message_start":
            usage = (data.get("message") or {}).get("usage")
            if usage:
                yield ("usage", 0, "", _usage(usage))
        elif event == "content_block_start":
            block = data.get("content_block") or {}
            if block.get("type") == "tool_use":
                index = data.get("index", 0) or 0
                yield ("tool_id", index, "", block.get("id", ""))
                yield ("tool_delta", index, block.get("name", ""), "")
        elif event == "content_block_delta":
            delta = data.get("delta") or {}
            index = data.get("index", 0) or 0
            if delta.get("type") == "text_delta" and delta.get("text"):
                yield ("text", 0, "", delta["text"])
            elif delta.get("type") == "input_json_delta" and delta.get("partial_json"):
                yield ("tool_delta", index, "", delta["partial_json"])
        elif event == "message_delta":
            if data.get("usage"):
                yield ("usage", 0, "", _usage(data["usage"]))
        elif event == "error":
            yield ("error", 0, "", (data.get("error") or {}).get("message", "stream error"))
        # ping, message_stop and block_stop carry nothing to assemble

    async def json_turn(self, messages: List[Dict[str, Any]]):
        reply = self.parse_message(await self._send(self.build_body(messages)))
        _, _, data = parse_llm_json(reply.content or "")
        return data

    def __init__(self, base_url: str, model_name: str, api_key: Optional[str] = None,
                 stt: Optional[STTInterface] = None,
                 reasoning: Optional[ReasoningStyle] = None,
                 key_field: str = "", model_field: str = "", url_field: str = ""):
        super().__init__(base_url, model_name, api_key, stt, reasoning,
                         key_field, model_field, url_field)


def _to_messages(messages: List[Dict[str, Any]]):
    """The app's OpenAI-shaped history onto anthropic messages plus system."""
    systems: List[str] = []
    converted: List[Dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            systems.append(str(msg.get("content") or ""))
        elif role == "assistant" and msg.get("tool_calls"):
            blocks: List[Dict[str, Any]] = []
            if msg.get("content"):
                blocks.append({"type": "text", "text": str(msg["content"])})
            for tc in msg["tool_calls"]:
                function = tc.get("function") or {}
                arguments = function.get("arguments") or "{}"
                try:
                    arguments = json.loads(arguments) if isinstance(arguments, str) \
                        else arguments
                except json.JSONDecodeError:
                    arguments = {}
                blocks.append({"type": "tool_use", "id": tc.get("id", ""),
                               "name": function.get("name", ""), "input": arguments})
            converted.append({"role": "assistant", "content": blocks or
                              [{"type": "text", "text": ""}]})
        elif role == "tool":
            converted.append({"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": msg.get("tool_call_id", ""),
                "content": str(msg.get("content") or "")}]})
        else:
            content = msg.get("content")
            converted.append({"role": role,
                              "content": content if isinstance(content, str)
                              else str(content or "")})
    return "\n\n".join(systems), converted


def _to_tool(tool: Dict[str, Any]) -> Dict[str, Any]:
    function = tool.get("function") or {}
    parameters = function.get("parameters", tool.get("parameters",
                                                     tool.get("input_schema", {})))
    return {"name": function.get("name", tool.get("name", "")),
            "description": function.get("description", tool.get("description", "")),
            "input_schema": parameters}


def _usage(data: Optional[Dict[str, Any]]) -> Usage:
    data = data or {}
    return Usage(
        prompt_tokens=int(data.get("input_tokens", 0) or 0),
        completion_tokens=int(data.get("output_tokens", 0) or 0),
        cached_tokens=int(data.get("cache_read_input_tokens", 0) or 0),
    )
