from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Union

from src.core.agent.types import AssistantMessage

# (tool name, the new characters of its arguments). Called as a tool call is
# being written, so the arguments are a JSON fragment and not yet an object.
# (index, tool name, raw argument delta). The index is which of the turn's tool
# calls this belongs to: a provider may write two of them at once, and without
# it one call's arguments end up inside another's.
ToolDelta = Callable[[int, str, str], None]


class LLMClient(ABC):
    """Provider-agnostic, tool-aware chat client.

    This is the single primitive the agent harness depends on. Concrete
    providers (OpenAI, Groq, OpenRouter) map their native APIs onto it.
    `messages` follow the OpenAI chat schema (role/content, plus tool roles),
    which every supported provider can represent.
    """

    @abstractmethod
    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> AssistantMessage:
        """One model turn. Returns the assistant message, possibly with tool calls."""
        ...

    @abstractmethod
    async def complete_json(
        self,
        user_input: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[Dict[str, Any], list]:
        """One JSON-mode turn, awaitable.

        Background work (diary, dreamer, summaries) runs inside the same event
        loop as the consciousness. The blocking `generate_json` froze it for the
        whole call — with a dozen sessions to dream, Bea went deaf for minutes.
        """
        ...

    async def stream_complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        *,
        on_tool_delta: Optional[ToolDelta] = None,
    ) -> AssistantMessage:
        """`complete`, with the tool call reported as it is written.

        Deliberately not abstract, and the default is `complete` itself: a
        provider that cannot stream, or a model that turns out not to, then
        behaves exactly as it did before — the turn is simply heard when the
        whole line exists rather than as it is written.
        """
        return await self.complete(messages, tools=tools)

    @abstractmethod
    def reload_config(self, config) -> None:
        """Re-reads keys/model from config without recreating the client owner."""
        ...
