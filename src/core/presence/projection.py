"""Presence projection — deterministic semantic translation layer.

Subscribes to canonical EventManager events and translates runtime facts
into Presence state via PresenceRuntime. It never touches renderer APIs,
PNG paths, OBS commands, Live2D indices, or provider instructions.
"""

from src.core.events import EventCategory, EventManager
from src.core.presence.events import (
    PRESENCE_CONNECTED,
    PRESENCE_DISCONNECTED,
    PRESENCE_STATE_CHANGED,
    PRESENCE_EMOTION_CHANGED,
    PRESENCE_MOTION_REQUESTED,
    SPEECH_STARTED,
    SPEECH_FINISHED,
    SPEECH_INTERRUPTED,
    AGENT_TURN_STARTED,
    AGENT_TURN_COMPLETED,
    AGENT_TURN_FAILED,
    TOOL_STARTED,
    TOOL_COMPLETED,
    TOOL_FAILED,
    INPUT_LISTENING_STARTED,
    INPUT_LISTENING_FINISHED,
)
from src.core.presence.runtime import PresenceRuntime, PresenceState


class PresenceProjection:
    """Deterministic projection from canonical events to Presence state."""

    def __init__(
        self,
        event_manager: EventManager,
        presence_runtime: PresenceRuntime,
    ):
        self.event_manager = event_manager
        self.runtime = presence_runtime
        self._listening_active = False
        self._agent_active = False
        self._speech_active = False
        self._interrupted_active = False
        self._subscribe()

    def _subscribe(self):
        # Presence events (direct control)
        self.event_manager.subscribe(
            self._handle,
            event_type=PRESENCE_CONNECTED,
            subsystem="presence",
        )
        self.event_manager.subscribe(
            self._handle,
            event_type=PRESENCE_DISCONNECTED,
            subsystem="presence",
        )
        self.event_manager.subscribe(
            self._handle,
            event_type=PRESENCE_STATE_CHANGED,
            subsystem="presence",
        )
        # Speech lifecycle
        self.event_manager.subscribe(
            self._handle,
            event_type=SPEECH_STARTED,
            subsystem="expression",
        )
        self.event_manager.subscribe(
            self._handle,
            event_type=SPEECH_FINISHED,
            subsystem="expression",
        )
        self.event_manager.subscribe(
            self._handle,
            event_type=SPEECH_INTERRUPTED,
            subsystem="expression",
        )
        # STT lifecycle
        self.event_manager.subscribe(
            self._handle,
            event_type=INPUT_LISTENING_STARTED,
            subsystem="stt",
        )
        self.event_manager.subscribe(
            self._handle,
            event_type=INPUT_LISTENING_FINISHED,
            subsystem="stt",
        )
        # Agent/tool lifecycle
        self.event_manager.subscribe(
            self._handle,
            event_type=AGENT_TURN_STARTED,
            subsystem="agent",
        )
        self.event_manager.subscribe(
            self._handle,
            event_type=AGENT_TURN_COMPLETED,
            subsystem="agent",
        )
        self.event_manager.subscribe(
            self._handle,
            event_type=AGENT_TURN_FAILED,
            subsystem="agent",
        )
        self.event_manager.subscribe(
            self._handle,
            event_type=TOOL_STARTED,
            subsystem="agent",
        )
        self.event_manager.subscribe(
            self._handle,
            event_type=TOOL_COMPLETED,
            subsystem="agent",
        )
        self.event_manager.subscribe(
            self._handle,
            event_type=TOOL_FAILED,
            subsystem="agent",
        )

    def _handle(self, event_dict, event_obj):
        event_type = event_dict.get("event_type")
        subsystem = event_dict.get("subsystem")

        # Update active flags based on lifecycle events
        if event_type == INPUT_LISTENING_STARTED:
            self._listening_active = True
        elif event_type == INPUT_LISTENING_FINISHED:
            self._listening_active = False
        elif event_type == AGENT_TURN_STARTED or event_type == TOOL_STARTED:
            self._agent_active = True
        elif event_type == AGENT_TURN_COMPLETED or event_type == AGENT_TURN_FAILED:
            self._agent_active = False
            self._interrupted_active = False
        elif event_type == SPEECH_STARTED:
            self._speech_active = True
            self._interrupted_active = False
        elif event_type == SPEECH_FINISHED:
            self._speech_active = False
        elif event_type == SPEECH_INTERRUPTED:
            self._interrupted_active = True
            self._speech_active = False
        elif event_type == PRESENCE_CONNECTED:
            pass
        elif event_type == PRESENCE_DISCONNECTED:
            pass

        # Presence events control state directly
        if subsystem == "presence":
            if event_type == PRESENCE_CONNECTED:
                self.runtime.set_state(PresenceState.IDLE, trigger="presence.event")
                return
            elif event_type == PRESENCE_DISCONNECTED:
                self.runtime.set_state(PresenceState.OFFLINE, trigger="presence.event")
                self._listening_active = False
                self._agent_active = False
                self._speech_active = False
                self._interrupted_active = False
                return
            elif event_type == PRESENCE_STATE_CHANGED:
                return

        # Derive presence state from active lifecycle flags
        if self._interrupted_active:
            target = PresenceState.INTERRUPTED
        elif self._speech_active:
            target = PresenceState.SPEAKING
        elif self._agent_active:
            target = PresenceState.THINKING
        elif self._listening_active:
            target = PresenceState.LISTENING
        else:
            target = PresenceState.IDLE

        if target != self.runtime.state:
            self.runtime.set_state(target, trigger=str(event_type))
