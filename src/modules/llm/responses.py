"""The Responses API transport (`POST {base}/responses`).

OpenAI's item-based protocol: the system prompt travels as `instructions`,
history as input items, tools flat (no nested `function` key), tool results as
`function_call_output` linked by `call_id`. Stateless on purpose — history goes
in on every call and `store` stays false, which is both a privacy choice and a
requirement on endpoints that reject server-side state.
"""

import json
from typing import Any, Dict, List, Optional

from src.core.agent.types import AssistantMessage, ToolCall, Usage
from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.base import AsyncLLMClient, ProviderError
from src.modules.llm.reasoning import ReasoningStyle
from src.utils.llm_utils import parse_llm_json
from src.utils.logger import get_logger
from src.utils.sanitize import clean_model_output

logger = get_logger("bea.llm.responses")


class ResponsesClient(AsyncLLMClient):
    """POSTs to `/responses` and translates the app's message schema onto items."""

    query_path = "/responses"

    def build_body(self, messages: List[Dict[str, Any]],
                   tools: Optional[List[Dict[str, Any]]] = None,
                   stream: bool = False, json_mode: bool = False) -> Dict[str, Any]:
        instructions, inputs = _to_items(messages)
        body: Dict[str, Any] = {"model": self.model_name, "input": inputs,
                                "store": False}
        if instructions:
            body["instructions"] = instructions
        if tools:
            body["tools"] = [_flat_tool(t) for t in tools]
            body["tool_choice"] = "auto"
        if json_mode:
            body["text"] = {"format": {"type": "json_object"}}
        if stream:
            body["stream"] = True
        extra = self.reasoning.extra_body
        if extra:
            body.update({k: v for k, v in extra.items() if k not in body})
        return body

    def parse_message(self, data: Dict[str, Any]) -> AssistantMessage:
        texts: List[str] = []
        tool_calls: List[ToolCall] = []
        for item in data.get("output") or []:
            kind = item.get("type")
            if kind == "message":
                for part in item.get("content") or []:
                    if part.get("type") == "output_text":
                        texts.append(part.get("text", ""))
            elif kind == "function_call":
                try:
                    args = json.loads(item.get("arguments") or "{}")
                except json.JSONDecodeError:
                    logger.error(f"Bad tool arguments for {item.get('name')}: "
                                 f"{item.get('arguments')}")
                    args = {}
                tool_calls.append(ToolCall(id=item.get("call_id") or item.get("id", ""),
                                           name=item.get("name", ""), arguments=args))
            # reasoning items and anything else the endpoint invents are not
            # for the room and never reach it

        if not texts and not tool_calls and data.get("status", "completed") != "completed":
            raise ProviderError(f"{self.model_name}: response {data.get('status')}: "
                                f"{json.dumps(data)[:500]}")

        return AssistantMessage(content=clean_model_output("".join(texts)),
                                tool_calls=tool_calls,
                                usage=_usage(data.get("usage")),
                                model=data.get("model", self.model_name))

    def iter_events(self, event: str, data: Dict[str, Any]):
        # the event line and the type inside the payload say the same thing;
        # either may be missing behind a proxy, so each covers for the other
        event = event or str(data.get("type", ""))
        if event == "response.output_text.delta":
            if data.get("delta"):
                yield ("text", 0, "", data["delta"])
        elif event == "response.output_item.added":
            item = data.get("item") or {}
            if item.get("type") == "function_call":
                index = data.get("output_index", 0) or 0
                yield ("tool_id", index, "", item.get("call_id") or item.get("id", ""))
                yield ("tool_delta", index, item.get("name", ""), "")
        elif event == "response.function_call_arguments.delta":
            if data.get("delta"):
                yield ("tool_delta", data.get("output_index", 0) or 0, "",
                       data["delta"])
        elif event == "response.completed":
            usage = (data.get("response") or {}).get("usage")
            if usage:
                yield ("usage", 0, "", _usage(usage))
        elif event == "error":
            yield ("error", 0, "", data.get("message", "stream error"))
        # created, in_progress, content_part events carry nothing the room needs

    async def json_turn(self, messages: List[Dict[str, Any]]):
        try:
            reply = self.parse_message(await self._send(
                self.build_body(messages, json_mode=True)))
        except ProviderError as e:
            if "text.format" not in str(e).lower() and "json" not in str(e).lower():
                raise
            logger.info(f"{self.model_name} refused json mode; retrying with a plain prompt.")
            reply = self.parse_message(await self._send(self.build_body(messages)))
        _, _, data = parse_llm_json(reply.content or "")
        return data

    def __init__(self, base_url: str, model_name: str, api_key: Optional[str] = None,
                 stt: Optional[STTInterface] = None,
                 reasoning: Optional[ReasoningStyle] = None,
                 key_field: str = "", model_field: str = "", url_field: str = ""):
        super().__init__(base_url, model_name, api_key, stt, reasoning,
                         key_field, model_field, url_field)


def _to_items(messages: List[Dict[str, Any]]):
    """The app's OpenAI-shaped history onto responses input items."""
    instructions: List[str] = []
    inputs: List[Dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            instructions.append(str(msg.get("content") or ""))
        elif role == "assistant" and msg.get("tool_calls"):
            if msg.get("content"):
                inputs.append({"role": "assistant", "content": str(msg["content"])})
            for tc in msg["tool_calls"]:
                function = tc.get("function") or {}
                inputs.append({"type": "function_call",
                               "call_id": tc.get("id", ""),
                               "name": function.get("name", ""),
                               "arguments": function.get("arguments") or "{}"})
        elif role == "tool":
            inputs.append({"type": "function_call_output",
                           "call_id": msg.get("tool_call_id", ""),
                           "output": str(msg.get("content") or "")})
        else:
            inputs.append({"role": role, "content": msg.get("content")})
    return "\n\n".join(instructions), inputs


def _flat_tool(tool: Dict[str, Any]) -> Dict[str, Any]:
    function = tool.get("function") or {}
    return {"type": "function", "name": function.get("name", tool.get("name", "")),
            "description": function.get("description", tool.get("description", "")),
            "parameters": function.get("parameters", tool.get("parameters", {}))}


def _usage(data: Optional[Dict[str, Any]]) -> Usage:
    data = data or {}
    details = data.get("input_tokens_details") or {}
    return Usage(
        prompt_tokens=int(data.get("input_tokens", 0) or 0),
        completion_tokens=int(data.get("output_tokens", 0) or 0),
        cached_tokens=int(details.get("cached_tokens", 0) or 0),
    )
