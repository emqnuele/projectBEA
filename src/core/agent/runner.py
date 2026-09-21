import inspect
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.core.agent.llm_client import LLMClient
from src.core.agent.tools import ToolRegistry
from src.core.agent.types import AssistantMessage, ToolCall
from src.utils.logger import get_logger

logger = get_logger("bea.agent.runner")

Hook = Optional[Callable[..., Any]]


async def _maybe_await(fn: Hook, *args) -> None:
    if fn is None:
        return
    result = fn(*args)
    if inspect.isawaitable(result):
        await result


@dataclass
class AgentHooks:
    """Observability/side-effect callbacks fired during the agent loop.

    Each may be sync or async. They never alter control flow — they let the
    host (Brain, a skill) speak thoughts, log events, stream progress, etc.
    """

    on_thought: Hook = None          # (content: str)
    on_tool_call: Hook = None        # (name: str, arguments: dict)
    on_tool_result: Hook = None      # (name: str, result: str)
    on_final: Hook = None            # (message: AssistantMessage)


class AgentRunner:
    """The think -> act -> observe loop shared by every agent in the app.

    Given an LLM, a tool registry and a running message list, it repeatedly
    asks the model what to do, executes any requested tools, feeds the
    observations back, and stops when the model answers without tool calls
    (or `max_steps` is reached).
    """

    def __init__(
        self,
        llm: LLMClient,
        tools: Optional[ToolRegistry] = None,
        max_steps: int = 10,
        hooks: Optional[AgentHooks] = None,
    ) -> None:
        self.llm = llm
        self.tools = tools or ToolRegistry()
        self.max_steps = max_steps
        self.hooks = hooks or AgentHooks()

    async def run(self, messages: List[Dict[str, Any]]) -> AssistantMessage:
        """Drives the loop in place on `messages` and returns the final turn."""
        tool_schemas = self.tools.schemas() or None
        last = AssistantMessage(content="")

        for step in range(self.max_steps):
            last = await self.llm.complete(messages, tools=tool_schemas)
            messages.append(self._assistant_to_message(last))

            if last.content:
                await _maybe_await(self.hooks.on_thought, last.content)

            if last.is_final:
                await _maybe_await(self.hooks.on_final, last)
                return last

            for call in last.tool_calls:
                await _maybe_await(self.hooks.on_tool_call, call.name, call.arguments)
                observation = await self.tools.dispatch(call)
                await _maybe_await(self.hooks.on_tool_result, call.name, observation)
                messages.append(self._tool_result_message(call, observation))

        logger.warning(f"Agent hit max_steps ({self.max_steps}) without a final answer.")
        await _maybe_await(self.hooks.on_final, last)
        return last

    @staticmethod
    def _assistant_to_message(msg: AssistantMessage) -> Dict[str, Any]:
        out: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            out["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                }
                for c in msg.tool_calls
            ]
        return out

    @staticmethod
    def _tool_result_message(call: ToolCall, observation: str) -> Dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": call.id,
            "name": call.name,
            "content": observation,
        }
