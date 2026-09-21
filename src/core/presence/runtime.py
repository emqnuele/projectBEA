"""Semantic Presence runtime.

This layer owns semantic Presence state and emits canonical events.
It deliberately knows nothing about PNGs, OBS, Live2D, VRM, audio devices,
or provider-specific renderer APIs.
"""

from enum import Enum
from typing import Optional

from src.core.events import EventCategory, EventManager

from .events import (
    PRESENCE_CONNECTED,
    PRESENCE_DISCONNECTED,
    PRESENCE_EMOTION_CHANGED,
    PRESENCE_MOTION_REQUESTED,
    PRESENCE_STATE_CHANGED,
)


class PresenceState(str, Enum):
    OFFLINE = "offline"
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"


class PresenceRuntime:
    """Own semantic Presence state and publish Presence events."""

    SUBSYSTEM = "presence"
    SOURCE = "presence.runtime"
    CATEGORY = EventCategory.EMBODIMENT

    def __init__(self, event_manager: EventManager):
        self.events = event_manager
        self.state = PresenceState.OFFLINE
        self.emotion: Optional[str] = None
        self.motion: Optional[str] = None
        self._state_event_id: Optional[str] = None

    @property
    def connected(self) -> bool:
        return self.state is not PresenceState.OFFLINE

    def connect(self):
        if self.connected:
            return None

        previous = self.state
        self.state = PresenceState.IDLE

        connected = self.events.publish(
            self.CATEGORY,
            self.SOURCE,
            "Presence connected",
            metadata={
                "event_type": PRESENCE_CONNECTED,
                "subsystem": self.SUBSYSTEM,
                "payload": {"state": self.state.value},
            },
        )

        self._state_event_id = connected.id

        self.events.publish(
            self.CATEGORY,
            self.SOURCE,
            "Presence state changed",
            metadata={
                "event_type": PRESENCE_STATE_CHANGED,
                "subsystem": self.SUBSYSTEM,
                "parent_event_id": connected.id,
                "payload": {
                    "state": self.state.value,
                    "from": previous.value,
                    "to": self.state.value,
                    "trigger": "connect",
                },
            },
        )

        return connected

    def disconnect(self):
        if not self.connected:
            return None

        previous = self.state
        self.state = PresenceState.OFFLINE

        disconnected = self.events.publish(
            self.CATEGORY,
            self.SOURCE,
            "Presence disconnected",
            metadata={
                "event_type": PRESENCE_DISCONNECTED,
                "subsystem": self.SUBSYSTEM,
                "payload": {"state": self.state.value},
            },
        )

        self._state_event_id = disconnected.id

        self.events.publish(
            self.CATEGORY,
            self.SOURCE,
            "Presence state changed",
            metadata={
                "event_type": PRESENCE_STATE_CHANGED,
                "subsystem": self.SUBSYSTEM,
                "parent_event_id": disconnected.id,
                "payload": {
                    "state": self.state.value,
                    "from": previous.value,
                    "to": self.state.value,
                    "trigger": "disconnect",
                },
            },
        )

        return disconnected

    def set_state(
        self,
        state: PresenceState | str,
        *,
        trigger: str = "runtime",
        run_id: Optional[str] = None,
    ):
        target = PresenceState(state)

        if target is self.state:
            return None

        previous = self.state
        self.state = target

        event = self.events.publish(
            self.CATEGORY,
            self.SOURCE,
            "Presence state changed",
            metadata={
                "event_type": PRESENCE_STATE_CHANGED,
                "subsystem": self.SUBSYSTEM,
                "run_id": run_id,
                "parent_event_id": self._state_event_id,
                "payload": {
                    "state": target.value,
                    "from": previous.value,
                    "to": target.value,
                    "trigger": trigger,
                },
            },
        )

        self._state_event_id = event.id
        return event

    def set_emotion(
        self,
        emotion: str,
        *,
        motion: Optional[str] = None,
        run_id: Optional[str] = None,
    ):
        self.emotion = emotion

        if motion is not None:
            self.motion = motion

        return self.events.publish(
            self.CATEGORY,
            self.SOURCE,
            "Presence emotion changed",
            metadata={
                "event_type": PRESENCE_EMOTION_CHANGED,
                "subsystem": self.SUBSYSTEM,
                "run_id": run_id,
                "parent_event_id": self._state_event_id,
                "payload": {
                    "emotion": emotion,
                    "motion": self.motion,
                },
            },
        )

    def request_motion(
        self,
        motion: str,
        *,
        duration: Optional[float] = None,
        run_id: Optional[str] = None,
    ):
        self.motion = motion

        return self.events.publish(
            self.CATEGORY,
            self.SOURCE,
            "Presence motion requested",
            metadata={
                "event_type": PRESENCE_MOTION_REQUESTED,
                "subsystem": self.SUBSYSTEM,
                "run_id": run_id,
                "parent_event_id": self._state_event_id,
                "payload": {
                    "motion": motion,
                    "duration": duration,
                },
            },
        )
