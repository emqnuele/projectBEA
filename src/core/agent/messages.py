"""Turning our types into the OpenAI wire format.

One copy. The consciousness, the agent runner and the conversation turns all
build the same two message shapes, and three drifting copies of a serialization
detail is how a subtle protocol bug gets introduced in exactly one of them.
"""

import json
from typing import Any, Dict

from src.core.agent.types import AssistantMessage, ToolCall


def assistant_to_message(msg: AssistantMessage) -> Dict[str, Any]:
    """An assistant turn as the API expects it back in the next request."""
    out: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        out["tool_calls"] = [
            {"id": c.id, "type": "function",
             "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
            for c in msg.tool_calls
        ]
    return out


def tool_result_message(call: ToolCall, observation: str) -> Dict[str, Any]:
    """What a tool answered, addressed back to the call that asked."""
    return {"role": "tool", "tool_call_id": call.id, "name": call.name,
            "content": observation}
