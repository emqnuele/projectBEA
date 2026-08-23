from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCall:
    """A single tool invocation requested by the model."""

    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class Usage:
    """What one model call cost. Zero when the provider did not report it."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.prompt_tokens + other.prompt_tokens,
                     self.completion_tokens + other.completion_tokens)


@dataclass
class AssistantMessage:
    """Normalized assistant turn, provider-agnostic.

    `content` is the natural-language reasoning/answer (may be None when the
    model only emits tool calls). `tool_calls` is empty on a final answer.
    """

    content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    # what it cost. Kept on the message so a turn can add it up without the
    # caller having to thread a counter through every layer.
    usage: "Usage" = field(default_factory=lambda: Usage())
    model: str = ""

    @property
    def is_final(self) -> bool:
        return not self.tool_calls
