from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

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
    def reload_config(self, config) -> None:
        """Re-reads keys/model from config without recreating the client owner."""
        ...
