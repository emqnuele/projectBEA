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
    """What one model call cost. Zero when the provider did not report it.

    `cached_tokens` is the part of the prompt the provider recognised from a
    previous call and did not charge full price for. It is reported because it
    is the only way to tell whether the prompt is still shaped the way caching
    wants it: a change that quietly puts something volatile near the top drives
    it to zero, and nothing else about the turn looks any different.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cache_hit(self) -> float:
        """How much of the prompt came out of the cache, 0 to 1."""
        return self.cached_tokens / self.prompt_tokens if self.prompt_tokens else 0.0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.prompt_tokens + other.prompt_tokens,
                     self.completion_tokens + other.completion_tokens,
                     self.cached_tokens + other.cached_tokens)


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
