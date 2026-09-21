"""Canonical Presence-domain event names.

Transport and envelope concerns remain owned by src.core.events.
"""

PRESENCE_CONNECTED = "presence.connected"
PRESENCE_DISCONNECTED = "presence.disconnected"
PRESENCE_STATE_CHANGED = "presence.state.changed"
PRESENCE_EMOTION_CHANGED = "presence.emotion.changed"
PRESENCE_MOTION_REQUESTED = "presence.motion.requested"

# Expression adapter speech lifecycle.
SPEECH_STARTED = "speech.started"
SPEECH_CHUNK = "speech.chunk"
SPEECH_FINISHED = "speech.finished"
SPEECH_INTERRUPTED = "speech.interrupted"

# Agent turn lifecycle.
AGENT_TURN_STARTED = "agent.turn.started"
AGENT_TURN_COMPLETED = "agent.turn.completed"
AGENT_TURN_FAILED = "agent.turn.failed"

# Tool lifecycle.
TOOL_STARTED = "tool.started"
TOOL_PROGRESS = "tool.progress"
TOOL_COMPLETED = "tool.completed"
TOOL_FAILED = "tool.failed"

# STT lifecycle.
INPUT_LISTENING_STARTED = "input.listening.started"
INPUT_TRANSCRIPT_PARTIAL = "input.transcript.partial"
INPUT_TRANSCRIPT_FINAL = "input.transcript.final"
INPUT_LISTENING_FINISHED = "input.listening.finished"
