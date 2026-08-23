from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from src.core.agent.types import AssistantMessage


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

    @abstractmethod
    def reload_config(self, config) -> None:
        """Re-reads keys/model from config without recreating the client owner."""
        ...
