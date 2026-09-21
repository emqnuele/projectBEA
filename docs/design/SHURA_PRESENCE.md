# SHURA Presence Architecture — Design Specification

Status: P0 Design Complete | P1 Runtime Framework | P2+ Deferred
Author: Architectural design phase (autonomous loop guidance)

---

## 1. Executive Summary

This document defines the **Presence Architecture** for ProjectSHURA, establishing how SHURA's semantic state, emotion, motion, and activity are modeled, projected, and observed through the desktop companion shell and embodiment adapters.

**Core Principle:** `IDENTITY != COGNITION != PRESENCE != EMBODIMENT != PROVIDER != INTERFACE`

- **Identity**: Who SHURA is (`data/prompts/soul.md`)
- **Cognition**: Hermes, memory, reasoning, skills, tools, Dream Engine
- **Presence**: Semantic state (offline, listening, thinking, speaking, etc.)
- **Embodiment**: Live2D, 3D, PNG sprite, animation, visual presentation
- **Provider**: LLM/ASR/TTS/model infrastructure
- **Interface**: Desktop pet, control window, future web/mobile UI

---

## 2. Architecture Delta — Where Presence Connects

```
┌─────────────────────────────────────────────────────────────────┐
│                     ATLAS / Design Framework                      │
│  docs/design/, docs/vision/, docs/reference/, docs/operations/   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PROJECTSHURA CORE                            │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌───────┐│
│  │  Conscious- │  │   Dream     │  │   Event      │  │Memory ││
│  │  ness      │  │   Engine    │  │ Manager      │  │       ││
│  │ (brain.py) │  │(domain.py)  │  │(events.py)   │  │       ││
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘  └───┬───┘│
│         │                │                │              │    │
│         │                │                │              │    │
│         ▼                │                ▼              │    │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │           PROJECTSHURA OBSERVATION HOOKS                 │ │
│  │  (event_manager.subscribe() + /dream/projection endpoint)│ │
│  └──────────────────────────────────────────────────────────┘ │
│                                 │                              │
│                                 ▼                              │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │       PRESENCE RUNTIME / PROJECTOR (NEW)                 │ │
│  │  (subscribes to events; runs state machine; emits        │ │
│  │   presence.* events)                                     │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                 │                              │
│                                 ▼                              │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │            SHURA SHELL (Electron Desktop, P2 DESIGN)     │ │
│  │  (pet mode / control window; shared session state)      │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                 │                              │
│                                 ▼                              │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                EMBODIMENT ADAPTER (P3 DESIGN)           │ │
│  │  (Live2D / PNG / future 3D; maps presence → visuals)    │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Boundary Rules Verified:**
- Brain/consciousness loop unchanged (verified: `brain.py`, `consciousness.py`)
- Event bus NOT duplicated (uses `EventManager.subscribe()` only)
- Projection read-only (verified: `src/core/dream/projection.py`, `tests/test_dream_projection.py`)
- Presence domain does NOT import brain internals (design contract)
- Legacy 7 mood IDs preserved: `normal, shock, love, cry, angry, ew, bored`

---

## 3. Presence Contract (P0)

### 3.1 Semantic States (Presence Domain)

`src/core/presence/domain.py` — semantic state enumeration (NOT PNG paths):

```python
class PresenceState:
    OFFLINE   = "offline"    # Hermes not connected / brain not running
    BOOTING   = "booting"    # Initializing consciousness / skills
    IDLE      = "idle"       # No active input; available
    LISTENING = "listening"  # ASR active; receiving audio input
    THINKING  = "thinking"   # LLM processing; no speech yet
    SPEAKING  = "speaking"   # TTS active; voice output in progress
    INTERRUPTED = "interrupted" # User interrupted speech (barge-in)
    WORKING   = "working"    # Tool execution in progress
    DREAMING  = "dreaming"   # System dream/consolidation active
    PAUSED    = "paused"     # Consciousness paused (sleep mode)
    ERROR     = "error"      # System error; cannot process input
```

### 3.2 Event Vocabulary (Presence Events)

Uses existing `EventCategory.EMBODIMENT` — extends via `event_type` strings (NOT new category):

| Event | Event Type | Source | Description |
|-------|------------|--------|-------------|
| `presence.connected` | `state` | presence.runtime | Hermes/core started; presence active |
| `presence.disconnected` | `state` | presence.runtime | Hermes/core stopped; presence offline |
| `presence.state.changed` | `state` | presence.runtime | State transition: `{from → to}` |
| `presence.emotion.changed` | `state` | presence.runtime | Emotion update; maps to 7 mood IDs |
| `presence.motion.requested` | `state` | presence.runtime | Motion/animation request |
| `speech.started` | `state` | expression.adapter | TTS audio began playback |
| `speech.chunk` | `state` | expression.adapter | TTS audio chunk ready |
| `speech.finished` | `state` | expression.adapter | TTS audio completed |
| `speech.interrupted` | `state` | expression.adapter | TTS interrupted (barge-in) |
| `input.listening.started` | `state` | stt.adapter | ASR began capturing |
| `input.transcript.partial` | `info` | stt.adapter | Partial transcript update |
| `input.transcript.final` | `state` | stt.adapter | Final transcript ready |
| `input.listening.finished` | `state` | stt.adapter | ASR stopped |
| `tool.started` | `progress` | agent.core | Tool execution began |
| `tool.progress` | `progress` | agent.core | Tool progress update |
| `tool.completed` | `success` | agent.core | Tool finished successfully |
| `tool.failed` | `error` | agent.core | Tool failed |
| `attention.requested` | `state` | shell/ui | User attention requested |
| `attention.released` | `state` | shell/ui | User attention released |
| `avatar.interaction.clicked` | `info` | shell/ui | Avatar click event |
| `avatar.interaction.dragged` | `info` | shell/ui | Avatar drag event |
| `dream.started` | `state` | dream.skill | Dream consolidation begun |
| `dream.progress` | `progress` | dream.skill | Dream progress update |
| `dream.finished` | `state` | dream.skill | Dream consolidation complete |

### 3.3 Semantic Contracts

**Emotion** — semantic emotion maps to 7 legacy mood IDs (never replaces):
```
emotion.normal   → mood.normal   (baseline, conversational)
emotion.shock    → mood.shock    (surprise, startled)
emotion.love     → mood.love     (affection, caring)
emotion.cry      → mood.cry      (sadness, upset)
emotion.angry    → mood.angry    (anger, frustration)
emotion.ew       → mood.ew       (disgust, discomfort)
emotion.bored    → mood.bored    (disinterest, waiting)
```
*Adapter layer translates; presence domain does NOT own avatar files.*

**Motion** — semantic animation states:
```
motion.idle         (default breathing/idle animation)
motion.listening    (ear/bubble animation for ASR)
motion.thinking     (head tilt, hand to chin, etc.)
motion.speaking     (mouth movement, gesture sync)
motion.working      (focused pose, tool action visualization)
motion.interrupted  (startled stop animation)
motion.dreaming     (soft glow, drifting pose)
motion.error        (distress animation, indicator)
```

**Speech Lifecycle** — first-class interruption modeling:
```
speech.started   → expression.is_speaking = True
speech.chunk     → TTS chunk emitted (streaming)
speech.finished  → expression.is_speaking = False; idle reset
speech.interrupted → expression.interrupt() triggered (barge-in)
```

**Tool Activity Lifecycle** — observable through existing Tool events:
```
tool.started   → Tool call dispatched; presence.state = working
tool.progress  → Tool in progress; optional status update
tool.completed → Tool result observed; presence.state returns
tool.failed    → Tool error observed; presence.state = error
```

---

## 4. Presence Runtime (P1)

### 4.1 Components

```
src/core/presence/
├── domain.py      # Semantic states, emotions, motions (VERIFIED CONTRACT)
├── events.py      # Event vocabulary constants (extends event_type usage)
├── state.py       # State machine (offline → booting → idle → ...)
├── projector.py   # Projection adapter (observes events, builds presence state)
└── runtime.py     # Runtime engine (runs state machine, emits events)
```

### 4.2 projector.py — Read-Only Observation

```
# MUST NOT import:
#   - brain.py, consciousness.py, expression.py
#   - dream/domain.py (only uses public events)
#
# USES:
#   - event_manager.subscribe() with filters
#   - event replay for state reconstruction
#   - /dream/projection endpoint via HTTP (if needed)
```

**Key Implementation Rules:**
1. Observation only — never mutated domain state
2. Event subscription filters: `subsystem="presence"`, `event_type="state|progress|error"`
3. Parent event correlation for traceability
4. State transitions emit `presence.state.changed` with `{state, from, to, trigger}`

### 4.3 state.py — Semantic State Machine

```python
class PresenceStateMachine:
    def __init__(self):
        self.current_state = PresenceState.OFFLINE
        self.emotion = "normal"
        self.motion = "idle"
        self.speech_active = False
        self.tool_in_progress = False

    def on_event(self, event: Dict[str, Any]) -> List[Event]:
        """Process event; return list of derived presence events."""
        # Transition logic based on event.source, event.category
        # Emit presence.* events when state changes
        pass
```

### 4.4 runtime.py — Event Emission

```python
class PresenceRuntime:
    def __init__(self, event_manager: EventManager, stt: Optional[STTInterface] = None):
        self.events = event_manager
        self.state_machine = PresenceStateMachine()
        self.subscriptions = []

    async def start(self):
        """Subscribe to relevant events; run initial state."""
        self.subscriptions = [
            self.events.subscribe(self._handle, source="expression"),
            self.events.subscribe(self._handle, category=EventCategory.TOOL),
            self.events.subscribe(self._handle, category=EventCategory.DREAM),
            # ... more subscriptions
        ]
        await self.events.publish(EventCategory.SYSTEM, "presence", "Presence online")

    def _handle(self, event_dict, event_obj):
        """Observer callback; updates state machine; emits derived events."""
        pass
```

### 4.5 Test Framework (tests/test_presence_*.py)

- `test_presence_contract.py`: verifies event vocabulary; verifies no brain mutation; verifies projection read-only
- `test_presence_runtime.py`: verifies state machine transitions; verifies event emission; verifies legacy mood preservation

---

## 5. Desktop Shell Design (P2 Framework Only)

**NOT IMPLEMENTED** — design contract only for future shell layer.

### 5.1 Required Capabilities

| Capability | Contract |
|------------|----------|
| Transparent background | Shell owns visual layer; brain/presence independent |
| Borderless window | Design: Electron BrowserWindow with `transparent: true` |
| Global always-on-top | Design: `alwaysOnTop: true` via Electron |
| Drag | Design: window moved on titlebar drag; position persisted |
| Resize | Design: handle or shortcut; scale persisted |
| Click-through | Design: `transparent` + `hasShadow: false`; non-interactive regions pass through |
| System tray | Design: context menu: show/hide/pet-mode/control-mode |
| Persist position/scale | Design: JSON config in user app data; not identity file |
| Pet mode / Control-window mode | Design: same session state; mode switch broadcasts `presence.state.changed` |
| Mode switch without reset | Design: shared process; single brain session; websocket for multi-process |

### 5.2 Shell Resilience (Design Contract)

| Component Dies | System Response |
|----------------|-----------------|
| Electron shell dies | Cognition survives (brain runs independently); shell reconnects to event bus |
| Hermes/core dies | Shell displays `presence.state = offline` (observes disconnect event) |
| Live2D fails | Text interaction survives (expression.adapter continues; presence.shows `error` state) |
| TTS fails | Text output survives (typing animation continues; speech events show failure) |
| ASR fails | Manual text input survives (voice surface disabled; presence.state = `idle`) |

### 5.3 Session Sharing (Design Contract)

Shell modes share:
- Same `brain` session ID
- Same connection to LLM/TTS/OBS
- Same `HistoryManager` context
- Same avatar state (`expression.current_pose`, `is_speaking`)
- Same memory/session context

**Mechanism**: Single brain process; shell connects via WebSocket or file-based event bus (design decision deferred; transport framework allows both).

---

## 6. Embodiment Adapter Contract (P3 Design Reference)

**NOT IMPLEMENTED** — contract design only.

### 6.1 Adapter Interface

```
class EmbodimentAdapter:
    async def observe(self, presence_event: Dict) -> VisualStateRequest:
        """Translate presence event to visual state request."""
        pass

class VisualStateRequest:
    emotion: str      # one of 7 mood IDs
    motion: str       # one of motion.* states
    expression: float  # Live2D parameter (0-1 ranges, or None for sprite)
    audio: bool       # should speak? (TTS handled by Expression)
```

### 6.2 Supported Embodiments

| Embodiment | Design Status | Mapping |
|------------|---------------|---------|
| shura-01 (PNG/sprite) | V1 preserved | Mood → PNG index via avatar_map |
| shura-02 (Live2D) | P3 deferred | Mood → Cubism parameters + motion |
| Future 3D | P3 deferred | Mood/state → 3D animations |
| Non-Live2D renderers | P3 deferred | Abstract visual state interface |

### 6.3 Legacy Mood ID Preservation

Live2D adapter MUST map 7 mood IDs to model expressions:
```
mood.normal   → Live2D: "happy" + "neutral" parameters
mood.shock    → Live2D: "surprised" + "eyes wide"
mood.love     → Live2D: "smiling" + "blush"
mood.cry      → Live2D: "sad" + "tearducts"
mood.angry    → Live2D: "angry" + "furrowed brows"
mood.ew       → Live2D: "disgust" + "nose wrinkle"
mood.bored    → Live2D: "neutral" + "yawning"
```
*No silent replacement; adapter owns translation.*

---

## 7. Voice Presence Design (P4 Reference)

### 7.1 Speech Lifecycle Events

Extends existing TTS infrastructure (`Expression` adapter); does NOT replace.

| Phase | Event Emitted | Observer |
|-------|---------------|----------|
| Start | `speech.started` | PresenceRuntime observes `expression.is_speaking` |
| Chunk | `speech.chunk` | TTS streaming callback (if supported) |
| Finish | `speech.finished` | PresenceRuntime observes speech end |
| Interrupted | `speech.interrupted` | `expression.interrupt()` triggers event |

### 7.2 ASR Integration

ASR adapter (new `STTInterface` implementation) emits:
- `input.listening.started` when ASR begins
- `input.transcript.partial` on interim results
- `input.transcript.final` on final result
- `input.listening.finished` when ASR stops

**Fallback**: Manual text input always available; presence.state = `idle` when ASR unavailable.

### 7.3 Interruption First-Class

```
User interrupts speech:
1. Input: Ctrl+C or stop button
2. expression.interrupt() called
3. audio_lock releases current playback
4. resume_buffer may be set
5. PresenceRuntime observes interruption → emits speech.interrupted
6. presence.state may update to "interrupted" briefly
7. After resume or completion → presence.state returns
```

---

## 8. Control Center Design (P5 Framework Reference)

**Framework Design Only** — full implementation deferred to workspace expansion.

### 8.1 Integrated Views

| View | Data Source | Event Categories |
|------|-------------|------------------|
| Chat/history | `HistoryManager` | `EventCategory.OUTPUT`, `EventCategory.INPUT` |
| Tool activity | Event replay | `EventCategory.TOOL` |
| Presence display | `PresenceRuntime` | New `presence.*` events |
| Memory | `DreamSnapshot` (projection) | `EventCategory.MEMORY`, `EventCategory.DREAM` |
| Dream visibility | Projection endpoint | Dream events + snapshot fields |
| Settings | Config file | `EventCategory.SYSTEM` |
| Mood/emotion | Presence state | `presence.emotion.changed` |

### 8.2 Workspace Framework Integration

References:
- `docs/design/COMMAND_CENTER_V1.md` — navigation framework
- `docs/design/ARCHITECTURE_MAP.md` — system integration
- `docs/operations/LOOP_STATE.md` — observable state

### 8.3 Mutation Routes (Never Direct Brain Access)

| Action | Entry Point |
|--------|-------------|
| Start dream | `/dream/run` endpoint |
| Toggle skill | `/skills/{name}/toggle` endpoint |
| Update config | `/config` endpoint |
| Interrupt | `expression.interrupt()` via shell command |
| Click avatar | Shell emits `avatar.interaction.*` event |

---

## 9. Architecture Delta — What Connects to What

| Component | Connects To | Mechanism | Direction |
|-----------|-------------|-----------|-----------|
| Consciousness | EventManager | `publish()` | Out to events |
| Expression | EventManager | `publish()` | Out to events |
| DreamSkill | EventManager | `publish()` | Out to events |
| PresenceRuntime | EventManager | `subscribe()` | In from events |
| PresenceRuntime | EventManager | `publish()` | Out to events |
| Shell | EventManager | `subscribe()` | In from events |
| Adapter | PresenceRuntime | `subscribe()` | In from events |
| Adapter | EventManager | `subscribe()` | In from events |
| Projection | Domain | `read()` | In from domain (read-only) |

**No Cycles**: All connections are one-way observational flows; brain/consciousness has no presence dependencies.

---

## 10. Roadmap Integration

Integrated into `docs/tasks/V1_ROADMAP.md` Milestone 6 as subphases:

| Phase | Milestone | Scope | Status |
|-------|-----------|-------|--------|
| P0 | M6-P0 | Presence Contract design/spec | PROPOSED |
| P1 | M6-P1 | Presence Runtime + Test adapter | PROPOSED |
| P2 | M6-P2 | Desktop Shell design framework | PROPOSED |
| P3 | M6-P3 | Live2D Embodiment adapter contract | PROPOSED |
| P4 | M6-P4 | Voice Presence design | PROPOSED |
| P5 | M6-P5 | Control Center framework | PROPOSED |

**V2 Acceptance Criteria (from docs/reference/V1_ACCEPTANCE.md):**
- [ ] Presence framework observable in docs/design/SHURA_PRESENCE.md
- [ ] Event vocabulary documented in docs/reference/EVENT_CONTRACT.md
- [ ] Projection/read-only boundary preserved (verifies tests)
- [ ] Identity independence preserved (verifies soul.md unchanged)
- [ ] Dream/event/projection boundary preserved (verifies no shell coupling)
- [ ] Legacy mood IDs preserved (automated check in tests)

---

## 11. Verification Plan

### 11.1 Boundary Verification

Run before any implementation:
```bash
# Identity divergence check
md5sum data/prompts/soul.md
# Expected: unchanged from previous audit

# Dream boundary check
git diff --stat src/core/dream/
# Allowed: P1 runtime files (tests, projector), NOT domain mutation

# Event contract check
# Verify no new EventCategory (only new event_type strings)
grep "class EventCategory" src/core/events.py
# Should show: SYSTEM, INPUT, OUTPUT, THOUGHT, SKILL, TOOL, ERROR, MEMORY, AGENT, DREAM, EMBODIMENT

# Mood ID check
grep -oE "normal|shock|love|cry|angry|ew|bored" data/prompts/soul.md | sort -u
# Expected: all 7 present
```

### 11.2 Endpoint Inspection (Post-implementation)

- `/dream/projection` — unchanged (read-only)
- `/presence/state` — new endpoint (P1 runtime)
- `/events` — event replay works with presence.* events
- `/health` — presence runtime health endpoint

### 11.3 File Inspection

- `src/core/presence/` — only new domain files
- `tests/test_presence_*.py` — new tests, no brain mutation
- `docs/design/SHURA_PRESENCE.md` — this file (design only)

---

## 12. Design Framework Durability

This document must preserve expansion points for:

1. **Multiple SHURA embodiments** — adapter interface allows new renderers
2. **shura-01, shura-02, shura-03** — embodiment config drives which model loads
3. **Future 3D embodiment** — abstract visual state interface
4. **Non-Live2D renderers** — adapter pattern allows custom exporters
5. **Desktop shell evolution** — transport framework (WebSocket/file/IPC) allows multiple frontends

**References to durable frameworks:**
- `docs/vision/SHURA_V1_VISION.md` — V1 criteria
- `docs/design/THREE_SYSTEMS.md` — atlas/projectSHURA/forge separation
- `docs/design/ARCHITECTURE_MAP.md` — system integration
- `docs/design/COMMAND_CENTER_V1.md` — workspace surfaces
- `docs/operations/AUTONOMOUS_LOOP.md` — verification protocols
- `docs/operations/LOOP_STATE.md` — state format
- `docs/tasks/V1_TASK_GRAPH.md` — bounded task framework

---

## Appendix A: Event Taxonomy Extension Rules

Per `docs/EVENT_CONTRACT.md` (taxonomy rules):

1. **New event types** are additive string values for `event_type` field
2. **New categories** require ADR entry (none added here)
3. **Subsytem naming** follows: `"core"`, `"agent"`, `"dream"`, `"presence"`, `"embodiment"`
4. **Event schemas** must be documented here (not inline)
5. **Backward compatibility** must be preserved (existing callers unchanged)

---

## Appendix B: Mood ID Migration Path

If Live2D model lacks one of the 7 mood IDs, adapter MUST:
1. NOT skip/drop the mood
2. Map to closest approximation with documented deviation
3. Log warning if mapping is lossy
4. Allow user override in config

---

## Appendix C: Change Log

| Date | Change | Stage |
|------|--------|-------|
| 2024-09-17 | Initial creation (P0-P5 design framework) | DESIGN |

---

**END OF DESIGN DOCUMENT**