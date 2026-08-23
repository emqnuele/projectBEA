"""Test doubles for the pieces the consciousness talks to.

The important one is `FakeLLMClient`: given a scripted sequence of
`AssistantMessage`s it lets the whole loop run end-to-end with no network, so
questions like "how many model calls did that batch cost?" become assertions
instead of guesses.
"""

import asyncio
from typing import Any, Dict, List, Optional, Union

from src.core.agent.llm_client import LLMClient
from src.core.agent.types import AssistantMessage, ToolCall


class FakeLLMClient(LLMClient):
    """Replays scripted turns and records everything it was asked."""

    def __init__(self, script: Optional[List[AssistantMessage]] = None,
                 json_script: Optional[List[Any]] = None):
        self.script = list(script or [])
        self.json_script = list(json_script or [])
        self.calls: List[List[Dict[str, Any]]] = []
        self.json_calls: List[str] = []
        self.tools_seen: List[List[str]] = []
        self.fail_with: Optional[Exception] = None

    @property
    def call_count(self) -> int:
        return len(self.calls)

    async def complete(self, messages, tools=None, response_format=None) -> AssistantMessage:
        if self.fail_with:
            raise self.fail_with
        # deep enough to survive the caller mutating its context afterwards
        self.calls.append([dict(m) for m in messages])
        self.tools_seen.append([t["function"]["name"] for t in (tools or [])])
        if self.script:
            return self.script.pop(0)
        return AssistantMessage(content="(nothing to add)")

    async def complete_json(self, user_input, system_prompt=None, history=None) -> Union[Dict, list]:
        self.json_calls.append(user_input)
        return self.json_script.pop(0) if self.json_script else {}

    def reload_config(self, config) -> None:
        pass

    @property
    def last_system_prompt(self) -> str:
        if not self.calls:
            return ""
        first = self.calls[-1][0]
        return first.get("content", "") if first.get("role") == "system" else ""


def speaks(message: str, mood: str = "normal", call_id: str = "c1") -> AssistantMessage:
    return AssistantMessage(tool_calls=[
        ToolCall(id=call_id, name="speak", arguments={"mood": mood, "message": message})
    ])


def stays_silent(call_id: str = "c1") -> AssistantMessage:
    return AssistantMessage(tool_calls=[
        ToolCall(id=call_id, name="stay_silent", arguments={"reason": "nothing to say"})
    ])


def thinks(content: str) -> AssistantMessage:
    return AssistantMessage(content=content)


class FakeExpression:
    """Records what was spoken; never touches audio, OBS or the network."""

    def __init__(self):
        self.spoken: List[tuple] = []
        self.is_speaking = False
        self.interrupts = 0
        self.mood_avatar: Optional[str] = None

    async def speak(self, mood, message, *, route="local"):
        self.spoken.append((mood, message, route))
        return b"" if route == "remote" else None

    async def interrupt(self):
        self.interrupts += 1
        return True

    def set_mood_avatar(self, mood):
        self.mood_avatar = mood


class FakeHistory:
    def __init__(self, session_id: str = "session_test"):
        self.session_id = session_id
        self.messages: List[Dict[str, Any]] = []

    def add_message(self, role, content, **kwargs):
        self.messages.append({"role": role, "content": content, **kwargs})


class RecordingEvents:
    def __init__(self):
        self.events: List[tuple] = []

    def publish(self, category, source, message, metadata=None):
        self.events.append((category, source, message, metadata or {}))

    def of_category(self, category) -> List[tuple]:
        return [e for e in self.events if e[0] == category]


async def settle(loops: int = 8) -> None:
    """Yields long enough for the consciousness loop to make progress."""
    for _ in range(loops):
        await asyncio.sleep(0)
