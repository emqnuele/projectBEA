"""The Chat Completions transport (`POST {base}/chat/completions`).

The industry-standard protocol every compatible endpoint speaks: google ai
studio's openai endpoint, the models on localhost, and any self-hosted
compatible server. Messages and tools travel unchanged; only the reasoning
hint and the json-mode negotiation live here.
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

logger = get_logger("bea.llm.chat")


class ChatCompletionsClient(AsyncLLMClient):
    """POSTs chat completions (and reads the SSE stream) over aiohttp."""

    query_path = "/chat/completions"

    def __init__(self, base_url: str, model_name: str, api_key: Optional[str] = None,
                 stt: Optional[STTInterface] = None,
                 reasoning: Optional[ReasoningStyle] = None,
                 send_tool_choice: bool = True,
                 key_field: str = "", model_field: str = "", url_field: str = ""):
        # some endpoints document tools but reject tool_choice (ollama does):
        # the quirk travels per provider rather than per call
        self.send_tool_choice = send_tool_choice
        super().__init__(base_url, model_name, api_key, stt, reasoning,
                         key_field, model_field, url_field)

    def build_body(self, messages: List[Dict[str, Any]],
                   tools: Optional[List[Dict[str, Any]]] = None,
                   stream: bool = False, json_mode: bool = False) -> Dict[str, Any]:
        body: Dict[str, Any] = {"model": self.model_name, "messages": messages}
        if tools:
            body["tools"] = tools
            if self.send_tool_choice:
                body["tool_choice"] = "auto"
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if stream:
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}
        extra = self.reasoning.extra_body
        if extra:
            body.update({k: v for k, v in extra.items() if k not in body})
        return body

    def parse_message(self, data: Dict[str, Any]) -> AssistantMessage:
        choices = data.get("choices") or []
        message = (choices[0].get("message") if choices else {}) or {}

        tool_calls: List[ToolCall] = []
        for tc in message.get("tool_calls") or []:
            function = tc.get("function") or {}
            try:
                args = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                logger.error(f"Bad tool arguments for {function.get('name')}: "
                             f"{function.get('arguments')}")
                args = {}
            tool_calls.append(ToolCall(id=tc.get("id", ""), name=function.get("name", ""),
                                       arguments=args))

        # cheap models leak <think> blocks and special tokens; unfiltered they
        # end up spoken out loud
        return AssistantMessage(content=clean_model_output(message.get("content") or ""),
                                tool_calls=tool_calls,
                                usage=_usage(data.get("usage")),
                                model=self.model_name)

    def iter_events(self, event: str, data: Dict[str, Any]):
        if "usage" in data and data["usage"]:
            yield ("usage", 0, "", _usage(data["usage"]))
        choices = data.get("choices") or []
        delta = (choices[0].get("delta") if choices else {}) or {}
        if delta.get("content"):
            yield ("text", 0, "", delta["content"])
        for part in delta.get("tool_calls") or []:
            index = part.get("index", 0) or 0
            if part.get("id"):
                yield ("tool_id", index, "", part["id"])
            function = part.get("function") or {}
            yield ("tool_delta", index, function.get("name", ""),
                   function.get("arguments", ""))

    async def json_turn(self, messages: List[Dict[str, Any]]):
        try:
            reply = self.parse_message(await self._send(
                self.build_body(messages, json_mode=True)))
        except ProviderError as e:
            if "response_format" not in str(e).lower() and "json" not in str(e).lower():
                raise
            logger.info(f"{self.model_name} refused json mode; retrying with a plain prompt.")
            reply = self.parse_message(await self._send(self.build_body(messages)))
        _, _, data = parse_llm_json(reply.content or "")
        return data


def _usage(data: Optional[Dict[str, Any]]) -> Usage:
    data = data or {}
    details = data.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens", data.get("cached_tokens", 0))
    return Usage(
        prompt_tokens=int(data.get("prompt_tokens", 0) or 0),
        completion_tokens=int(data.get("completion_tokens", 0) or 0),
        cached_tokens=int(cached or 0),
    )
