"""Test doubles for the pieces the consciousness talks to.

`FakeLLMClient` replays a scripted sequence of `AssistantMessage`s, so the whole
loop runs with no network and "how many model calls did that batch cost?"
becomes an assertion.
"""

import asyncio
import json
import time
import types
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
        # recorded before it fails: a call that raised is still a call that was
        # made, and a test waiting for one would otherwise wait forever
        # deep enough to survive the caller mutating its context afterwards
        self.calls.append([dict(m) for m in messages])
        if self.fail_with:
            raise self.fail_with
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
        """Everything she was told as system on the last call, in order.

        More than one message, since the stable half of the prompt and the
        briefing for this particular moment are deliberately kept apart.
        """
        if not self.calls:
            return ""
        return "\n\n".join(m.get("content", "") for m in self.calls[-1]
                            if m.get("role") == "system")


class StreamingLLMClient(FakeLLMClient):
    """Replays a scripted turn the way a provider writes one: a few characters
    at a time, with the loop given a chance to breathe between them."""

    def __init__(self, script: Optional[List[AssistantMessage]] = None, chunk: int = 6):
        super().__init__(script)
        self.chunk = chunk
        # called after every delta, so a test can look at what has happened so
        # far while the line is still being written
        self.after_delta = None

    async def stream_complete(self, messages, tools=None, *, on_tool_delta=None):
        message = await self.complete(messages, tools=tools)
        if on_tool_delta is None:
            return message
        for index, call in enumerate(message.tool_calls):
            raw = json.dumps(call.arguments)
            for start in range(0, len(raw), self.chunk):
                on_tool_delta(index, call.name, raw[start:start + self.chunk])
                for _ in range(4):
                    await asyncio.sleep(0)
                if self.after_delta:
                    self.after_delta()
        return message


def speaks(message: str, mood: str = "neutral", call_id: str = "c1") -> AssistantMessage:
    return AssistantMessage(tool_calls=[
        ToolCall(id=call_id, name="speak", arguments={"mood": mood, "message": message})
    ])


def stays_silent(call_id: str = "c1") -> AssistantMessage:
    return AssistantMessage(tool_calls=[
        ToolCall(id=call_id, name="stay_silent", arguments={"reason": "nothing to say"})
    ])


def thinks(content: str) -> AssistantMessage:
    return AssistantMessage(content=content)


class FakeLine:
    """A line she is saying while it is written, recorded rather than heard."""

    def __init__(self, mood: str, route: str, feeling=None):
        self.mood = mood
        self.route = route
        self.feeling = feeling
        self.said: List[str] = []
        self.input_closed = False
        self.closed = False
        self.cancelled = False
        self.spoiled = False
        self.tainted = False
        # what of the line actually reached the room, as the real `LiveLine`
        # reports it: non-empty means an answer must not be said over it
        self.spoken = ""

    def say(self, text: str) -> None:
        self.said.append(text)

    def close_input(self) -> None:
        self.input_closed = True

    async def close(self):
        self.input_closed = True
        self.closed = True
        return None

    async def cancel(self) -> None:
        self.cancelled = True

    @property
    def written(self) -> str:
        return "".join(self.said)


class FakeExpression:
    """Records what was spoken; never touches audio, OBS or the network."""

    def __init__(self):
        self.spoken: List[tuple] = []
        # how she felt when each line was decided, for the prosody tests
        self.felt: List[Any] = []
        self.is_speaking = False
        self.interrupts = 0
        self.state: Optional[tuple] = None
        self.call = None
        # every line she started, finished or not
        self.lines: List[FakeLine] = []
        # None means the route cannot be served, the way the real one answers
        self.opens_lines = True
        # a line that meets the model's own scaffolding before a word is heard
        self.spoils_lines = False
        # turns that opened the sound card ahead of her first word
        self.warm_ups = 0
        self.thinking: List[bool] = []

    def warm_up(self):
        self.warm_ups += 1

    def set_call(self, call):
        self.call = call

    def set_affect(self, affect):
        self.affect = affect

    def show_thinking(self, active):
        self.thinking.append(active)

    def open_line(self, mood, *, route="local", feeling=None, caption=None):
        if not self.opens_lines:
            return None
        line = FakeLine(mood, route, feeling)
        line.spoiled = self.spoils_lines
        self.lines.append(line)
        return line

    @property
    def call_is_live(self) -> bool:
        return bool(self.call is not None and self.call.live)

    async def wait_for_floor(self) -> bool:
        wait = getattr(self.call, "until_quiet", None)
        if not self.call_is_live or wait is None:
            return True
        return await wait(30.0)

    async def speak(self, mood, message, *, route="local", feeling=None):
        self.spoken.append((mood, message, route))
        self.felt.append(feeling)
        return None

    async def interrupt(self, ramp_ms: int = 200):
        self.interrupts += 1
        return True

    def set_state(self, state, mood=None):
        self.state = (state, mood)


class FakeAvatar:
    """Records what she was made to look like; touches nothing."""

    def __init__(self):
        self.shown: List[tuple] = []
        self.performed: List[str] = []
        self.envelopes: List[tuple] = []
        self.closed = False

    def show(self, mood, state):
        self.shown.append((mood, state))

    def perform(self, clip):
        self.performed.append(clip)

    def mouth(self, envelope, fps):
        self.envelopes.append((list(envelope), fps))

    def reload_config(self, config):
        pass

    def close(self):
        self.closed = True

    @property
    def states(self) -> List[str]:
        return [state for _mood, state in self.shown]


class FakeCaption:
    """Records the lines put on screen, without animating them.

    `delay` stands in for a backend that types over time, like the OBS one: it is
    what makes "an interruption reaches the caption" something a test can see.
    """

    def __init__(self, delay: float = 0.0):
        self.said: List[str] = []
        self.clears = 0
        self.delay = delay
        self.cancelled = 0
        self.finished = 0

    async def say(self, text):
        self.said.append(text)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        self.finished += 1

    def clear(self):
        self.clears += 1

    def reload_config(self, config):
        pass


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


# --- the sound card ------------------------------------------------------------


class FakeOutputStream:
    """A device that plays in real time and hears nothing: a ring of `capacity` frames drained by the clock."""

    def __init__(self, samplerate=24000, device=None, channels=1, dtype="float32",
                 capacity_ms=60, fail_open=False, latency=None, **_):
        if fail_open:
            raise OSError("the device refused to open")
        self.latency_asked = latency
        self.samplerate = int(samplerate)
        self.device = device
        self.channels = channels
        self.capacity = self.samplerate * capacity_ms // 1000
        self.frames = 0
        self.started_at = None
        self.written = []
        self.peak = 0.0
        self.underflows = 0
        self.closed = False

    def _played(self):
        if self.started_at is None:
            return 0
        return int((time.monotonic() - self.started_at) * self.samplerate)

    def _queued(self):
        return max(0, self.frames - self._played())

    def start(self):
        self.started_at = time.monotonic()

    @property
    def write_available(self):
        return self.capacity - self._queued()

    def write(self, data):
        # an empty ring plays the next write from now, the first too: a stream opened early banks no time
        underflow = self._queued() == 0 and self.frames > 0
        if underflow:
            self.underflows += 1
        if self._queued() == 0:
            self.frames = self._played()
        while self.capacity - self._queued() < len(data):
            time.sleep(0.001)
        self.frames += len(data)
        self.written.append(len(data))
        if len(data):
            self.peak = max(self.peak, float(abs(data).max()))
        return underflow

    def abort(self):
        pass

    def close(self):
        self.closed = True


class SilentDevice:
    """Stands in for PortAudio so the suite never reaches the sound card.

    The player imports sounddevice where it is used and hands it whatever the
    TTS produced. A test that returns real samples rather than zeros would
    play them — out loud, on the machine running the tests — and a headless
    box has no PortAudio to import in the first place.
    """

    def __init__(self):
        self.streams = []
        self.restarts = 0
        self.default = types.SimpleNamespace(device=(0, 0))
        self.devices = [{"name": "silent", "max_output_channels": 2, "max_input_channels": 2,
                         "default_low_output_latency": 0.0}]
        # device names that refuse to open, like a bluetooth headset stuck in headset mode
        self.refuse = set()
        # seconds opening a stream takes, like a real device does
        self.open_delay = 0.0
        # the size of each stream's ring; a test about holes gives a shared ci runner room to hiccup
        self.capacity_ms = 60

    def output(self, name, latency=0.0, channels=2):
        """Adds an output device and returns its position."""
        self.devices.append({"name": name, "max_output_channels": channels, "max_input_channels": 0,
                             "default_low_output_latency": latency})
        return len(self.devices) - 1

    def OutputStream(self, **kwargs):
        if self.open_delay:
            time.sleep(self.open_delay)
        name = self.devices[kwargs.get("device", 0)]["name"]
        stream = FakeOutputStream(fail_open=name in self.refuse, capacity_ms=self.capacity_ms, **kwargs)
        self.streams.append(stream)
        return stream

    def query_devices(self, index=None):
        return self.devices[index] if index is not None else list(self.devices)

    def _terminate(self):
        self.restarts += 1

    def _initialize(self):
        pass
