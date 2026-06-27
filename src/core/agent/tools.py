import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.core.agent.types import ToolCall
from src.utils.logger import get_logger

logger = get_logger("bea.agent.tools")

# a handler may be sync or async; it always returns an observation string
ToolHandler = Callable[..., Any]


@dataclass
class Tool:
    """A capability exposed to the model as a callable function.

    `parameters` is a JSON Schema object describing the arguments. `handler`
    receives those arguments as keyword args and returns an observation that is
    fed back into the agent loop.
    """

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: ToolHandler
    long_running: bool = False  # BODY actions that should run async (single-slot), not block reasoning

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Holds the tools available to an agent and dispatches calls to them."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' is being overwritten.")
        self._tools[tool.name] = tool

    def add(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: ToolHandler,
        long_running: bool = False,
    ) -> None:
        self.register(Tool(name, description, parameters, handler, long_running))

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def schemas(self) -> List[Dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    def tools(self) -> List[Tool]:
        return list(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    async def dispatch(self, call: ToolCall) -> str:
        """Executes a tool call and returns its observation as a string.

        Errors are caught and returned as observations so the agent can react
        to them instead of crashing the loop.
        """
        tool = self._tools.get(call.name)
        if tool is None:
            return f"ERROR: unknown tool '{call.name}'."

        try:
            result = tool.handler(**call.arguments)
            if inspect.isawaitable(result):
                result = await result
            return "" if result is None else str(result)
        except TypeError as e:
            # almost always wrong/missing arguments from the model
            return f"ERROR: invalid arguments for '{call.name}': {e}"
        except Exception as e:
            logger.error(f"Tool '{call.name}' raised: {e}")
            return f"ERROR: tool '{call.name}' failed: {e}"
