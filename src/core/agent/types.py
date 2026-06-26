from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCall:
    """A single tool invocation requested by the model."""

    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class AssistantMessage:
    """Normalized assistant turn, provider-agnostic.

    `content` is the natural-language reasoning/answer (may be None when the
    model only emits tool calls). `tool_calls` is empty on a final answer.
    """

    content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)

    @property
    def is_final(self) -> bool:
        return not self.tool_calls
