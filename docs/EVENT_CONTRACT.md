# SHURA Event Contract

Status: Phase 1 (Event Foundation) · Internal runtime contract · Not a UI model

## Purpose

The event system is the durable, observable substrate that supports Dream Engine transactions, memory consolidation, agent execution, skill activation, embodiment events, and future Command Center surfaces.

The contract is internal: business logic does not live in the frontend; the UI consumes events via subscription and replay.

## Canonical Event Envelope

Every event produces exactly one structured record. The authoritative representation is the Python `BrainEvent` dataclass (see `src/core/events.py`).

Required fields (always present):

| Field | Type | Meaning |
|---|---|---|
| `event_id` | `str` (UUID) | Unique event identifier; survives replay |
| `timestamp` | `float` (Unix time) | Wall-clock time at emission |
| `sequence` | `int` | Monotonic local sequence within this runtime; increases with each publish |
| `event_type` | `str` | Explicit event classification (see taxonomy below) |
| `category` | `str` (Enum) | Legacy category (`system`, `input`, `output`, `thought`, `skill`, `tool`, `error`, `memory`, `agent`, `dream`, `embodiment`) |
| `source` | `str` | Producer identifier (e.g. `"consciousness"`, `"memory"`, `"agent"`) |
| `message` | `str` | Human-readable summary |
| `subsystem` | `str` | Subsystem grouping (`core`, `memory`, `agent`, `embodiment`, `dream`, etc.) |
| `run_id` | `str` or `None` | Correlation ID grouping events into one logical execution |
| `parent_event_id` | `str` or `None` | Hierarchy reference; `None` for root events |
| `severity` | `str` | `info`, `success`, `warning`, `error`, `learning`, `approval`, `dream` |
| `visibility` | `str` | `ui` (user-facing), `debug` (developer diagnostics), `audit` (security/replay) |
| `payload` | `dict` | Structured data specific to the event; never arbitrary unstructured text |
| `metadata` | `dict` | Legacy/backward-compatible metadata bag |

No field is optional for serialization; `None` values serialize explicitly.

## Event Taxonomy (Event Types)

Use explicit `event_type` strings rather than inferring from `message` text.

| Constant | Value | When to use |
|---|---|---|
| `EVENT_TYPE_INFO` | `"info"` | General informational event |
| `EVENT_TYPE_STATE` | `"state"` | State change (e.g. sleep/wake, mode switch) |
| `EVENT_TYPE_LIFECYCLE` | `"lifecycle"` | Operation started/completed/failed/aborted |
| `EVENT_TYPE_ERROR` | `"error"` | Failure event |
| `EVENT_TYPE_WARNING` | `"warning"` | Non-fatal anomaly |
| `EVENT_TYPE_PROGRESS` | `"progress"` | Intermediate step (e.g. tool call, snapshot created) |
| `EVENT_TYPE_MUTATION` | `"mutation"` | Proposed or committed memory mutation |
| `EVENT_TYPE_OBSERVATION` | `"observation"` | External observation (tool result, perception) |
| `EVENT_TYPE_REHEARSAL` | `"rehearsal"` | Rehearsal stage events |
| `EVENT_TYPE_CONFLICT` | `"conflict"` | Contradiction detected |

## Presence Event Taxonomy (P0 — Design Phase)

Presence/embodiment events use `EventCategory.EMBODIMENT`. The `subsystem` identifies the logical producer domain and MUST be one of `presence`, `expression`, `agent`, `dream`, `shell`, or `stt`. They are emitted by the Presence Runtime and its adapters, and observed by the Desktop Shell and Embodiment Adapters.

| event_type | Source | Meaning |
|---|---|---|
| `presence.connected` | `presence.runtime` | Hermes/core started; presence active |
| `presence.disconnected` | `presence.runtime` | Hermes/core stopped; presence offline |
| `presence.state.changed` | `presence.runtime` | State transition `{from → to}`; payload: `{state, from, to, trigger}` |
| `presence.emotion.changed` | `presence.runtime` | Emotion update; payload: `{emotion, motion}` (maps to 7 legacy mood IDs) |
| `presence.motion.requested` | `presence.runtime` | Motion/animation request; payload: `{motion, duration}` |
| `speech.started` | `expression.adapter` | TTS audio began playback; payload: `{mood}` |
| `speech.chunk` | `expression.adapter` | TTS audio chunk ready (streaming); payload: `{chunk_index}` |
| `speech.finished` | `expression.adapter` | TTS audio completed |
| `speech.interrupted` | `expression.adapter` | TTS interrupted (barge-in); payload: `{resume_buffer_sec}` |
| `input.listening.started` | `stt.adapter` | ASR began capturing audio |
| `input.transcript.partial` | `stt.adapter` | Partial transcript update; payload: `{text}` |
| `input.transcript.final` | `stt.adapter` | Final transcript ready; payload: `{text, confidence}` |
| `input.listening.finished` | `stt.adapter` | ASR stopped capturing |
| `tool.started` | `agent.core` | Tool execution began; payload: `{tool_name}` |
| `tool.progress` | `agent.core` | Tool progress update; payload: `{tool_name, progress}` |
| `tool.completed` | `agent.core` | Tool finished successfully; payload: `{tool_name, result}` |
| `tool.failed` | `agent.core` | Tool failed; payload: `{tool_name, error}` |
| `attention.requested` | `shell.ui` | User attention requested (shell → core) |
| `attention.released` | `shell.ui` | User attention released |
| `avatar.interaction.clicked` | `shell.ui` | Avatar clicked; payload: `{x, y, region}` |
| `avatar.interaction.dragged` | `shell.ui` | Avatar dragged; payload: `{from_x, from_y, to_x, to_y}` |
| `dream.started` | `dream.skill` | Dream consolidation begun; payload: `{run_id}` |
| `dream.progress` | `dream.skill` | Dream progress update; payload: `{run_id, progress}` |
| `dream.finished` | `dream.skill` | Dream consolidation complete; payload: `{run_id, status}` |

### Presence Event Envelope (Mandatory Fields)

Every presence event MUST include:
- `subsystem`: `"presence"`, `"expression"`, `"agent"`, `"dream"`, `"shell"`, or `"stt"`
- `run_id`: when part of a multi-step operation (e.g. one speech turn)
- `parent_event_id`: when hierarchical (e.g. `speech.chunk` parent is `speech.started`)

Every presence event MUST NOT include:
- PNG filenames / file paths (renderer layer owns this)
- OBS-specific commands (expression adapter owns this)
- Live2D expression indices (embodiment adapter owns this)
- Provider-specific avatar instructions (adapter layer translates)

## Correlation Semantics

### `run_id`

Groups events belonging to a single logical execution. Examples:

- One agent turn
- One Dream run (`DreamTransaction.transaction_id`)
- One memory consolidation pass
- One tool workflow

Each event within the same logical execution shares the same `run_id`. The event manager does not enforce uniqueness globally; it is the producer's responsibility to set a consistent `run_id`.

### `parent_event_id`

Allows nested hierarchies. Example for a Dream run:

```
run_id: "dream-abc"
  event_id: "e1"  event_type: lifecycle  message: "Dream started"
  event_id: "e2"  event_type: progress  parent_event_id: "e1"  message: "Snapshot created"
  event_id: "e3"  event_type: progress  parent_event_id: "e1"  message: "Cluster started"
  event_id: "e4"  event_type: progress  parent_event_id: "e3"  message: "Memory recalled"
```

Root events (`parent_event_id` = `None`) represent top-level operations. Child events represent sub-operations.

### Ordering

`sequence` is a monotonic integer that increases with each `publish()` call within the current runtime. It is not globally unique across restarts; replay uses `sequence` within a `run_id` for deterministic ordering.

When replaying, events are ordered by `sequence`, then `timestamp`, then `event_id` for stability.

Ordering guarantees (within one runtime):
- `sequence` is strictly monotonically increasing.
- Replay of a `run_id` preserves original sequence.
- Replay does not generate new event IDs.

No global ordering is promised across independent future processes.

## Persistence: JSONL Journal

Location: `data/events/events.jsonl` (relative to workspace root; configurable via `EventManager` constructor).

Format: one JSON object per line (`JSON Lines`).

Retention policy (default):
- Maximum file size: 5 MB (`max_size_bytes`)
- Maximum lines: 20,000 (`max_lines`)
- Rotation: when overflow occurs, truncate to the most recent half (`max_lines // 2`).

The retention behavior is fail-safe: malformed lines are skipped during replay; rotation never deletes events below the retention threshold silently (the file is rewritten with truncated content, but replay reports the updated count).

Configuration: set `journal_path`, `max_size_bytes`, `max_lines` when constructing `EventManager`. Default values are conservative.

## Subscription Model

Internal only. No UI framework dependency.

Usage:

```python
em.subscribe(
    handler=lambda event_dict, event_obj: print(event_dict["message"]),
    event_type="lifecycle",
    subsystem="memory",
    run_id="dream-abc",
)
```

Filter dimensions (composable with `AND` logic):
- `event_type`
- `subsystem`
- `run_id`
- `severity`
- `visibility`
- `source`

Multiple subscribers are supported. Subscriber failures are caught and logged; they do not block event emission.

Unsubscribe:

```python
em.unsubscribe(handler)
```

## Replay Semantics

`EventManager.replay()` reads from the persistent JSONL journal and applies filters.

Key rules:
- Replay reproduces original event IDs (`event_id` unchanged).
- Replay does not create new `event_id` values.
- Replay does not modify `sequence`, `timestamp`, `run_id`, `parent_event_id`.
- Replay returns events in original order (`sequence`, then `timestamp`).
- Replay filters are `AND` composable.

Distinction between replay and emission:

`REPLAY REPRODUCES HISTORY.` It does not pretend the replay is a new occurrence. `publish()` creates a new event.

## Emission Hooks (Current Integration Points)

Minimal hooks added in Phase 1 (no destructive changes):

- `src/core/consciousness.py`: lifecycle/progress events for batch processing and tool dispatch (`event_type: lifecycle/progress`, `subsystem: consciousness/agent`).
- `src/core/expression.py`: state event for output (`event_type: state`, `subsystem: embodiment`).
- `src/core/agent/tools.py`: observation/progress events for tool execution (future phase; framework prepared).
- `src/core/skills/memory/memory.py`: framework preserved; event emission kept safe by avoiding tight coupling (memory skill does not own `EventManager` directly).

Existing `publish()` calls in `brain.py`, `consciousness.py`, `expression.py` continue to work unchanged; the new fields default to safe values.

## Producer Guidance

When emitting an event:

1. Choose an explicit `event_type` from the taxonomy, or define a new constant if the taxonomy is insufficient.
2. Set `subsystem` to the logical domain (`memory`, `agent`, `dream`, `embodiment`, `core`).
3. Set `run_id` when the event belongs to a multi-step operation.
4. Set `parent_event_id` when the event is a child of a previous event.
5. Set `payload` to structured data (`dict`), not arbitrary strings.
6. Do not include secrets (API keys, tokens, passwords) in `message`, `payload`, or `metadata`. Reference secrets by environment variable name or omit entirely.
7. Prefer `visibility: "ui"` for routine events; use `"audit"` for security-sensitive actions; use `"debug"` for diagnostic details.

## Consumer Guidance

When consuming events:

1. Subscribe using `subscribe()`; do not poll `events` list directly for real-time consumption (polling is supported via `get_events()` for inspection only).
2. Replay using `replay()` for audit, debugging, or historical analysis.
3. Do not assume `message` contains all information; read `payload` and `metadata` for structured data.
4. Treat `event_id` as the authoritative identifier; never replace it with derived keys.

## Compatibility

- `EventManager()` constructor preserves previous behavior (`max_history=200`, no journal). Default now creates `data/events/events.jsonl`.
- `publish(category, source, message, metadata=...)` continues to work; new fields default safely.
- `get_events()` continues to return recent events with the new envelope fields.
- `BrainEvent` dataclass preserves existing fields (`category`, `source`, `message`, `metadata`, `timestamp`, `id`) and appends new fields.
- The 7 legacy mood IDs (`normal`, `shock`, `love`, `cry`, `angry`, `ew`, `bored`) are preserved independently; event emission does not couple to avatar rendering.

## Limitations (Phase 1)

- Event stream does not yet include Dream-specific transaction stages (`snapshot_created`, `reconciliation_started`, etc.). Those will be added in Phase 2 (Dream Transaction Core) when `DreamTransaction` is implemented.
- Command Center UI does not yet subscribe to events; subscription mechanism is backend-ready.
- Event journal rotation is bounded but not compressed; future phases may add compression or archiving.
- Event emission from `memory` operations is minimal; full consolidation pipeline events will be added in Phase 3.

## Example Event Hierarchy

`run_id`: `dream-demo-001`

```
{
  "event_id": "e-001",
  "timestamp": 1695000000.0,
  "sequence": 1,
  "event_type": "lifecycle",
  "category": "dream",
  "source": "dream_engine",
  "message": "Dream transaction started",
  "subsystem": "dream",
  "run_id": "dream-demo-001",
  "parent_event_id": null,
  "severity": "info",
  "visibility": "ui",
  "payload": {"transaction_id": "dream-demo-001", "commit_mode": "review"},
  "metadata": {}
}

{
  "event_id": "e-002",
  "timestamp": 1695000001.2,
  "sequence": 2,
  "event_type": "progress",
  "category": "memory",
  "source": "dream_engine",
  "message": "Snapshot created: 42 source memories",
  "subsystem": "dream",
  "run_id": "dream-demo-001",
  "parent_event_id": "e-001",
  "severity": "info",
  "visibility": "ui",
  "payload": {"snapshot_size": 42, "max_limit": 250},
  "metadata": {}
}

{
  "event_id": "e-003",
  "timestamp": 1695000010.5,
  "sequence": 3,
  "event_type": "rehearsal",
  "category": "dream",
  "source": "dream_engine",
  "message": "Rehearsal passed: stem-workflow",
  "subsystem": "dream",
  "run_id": "dream-demo-001",
  "parent_event_id": "e-001",
  "severity": "success",
  "visibility": "ui",
  "payload": {"skill_name": "stem-workflow", "result": "passed", "confidence_delta": 0.05},
  "metadata": {}
}

{
  "event_id": "e-004",
  "timestamp": 1695000030.0,
  "sequence": 4,
  "event_type": "lifecycle",
  "category": "dream",
  "source": "dream_engine",
  "message": "Dream transaction completed",
  "subsystem": "dream",
  "run_id": "dream-demo-001",
  "parent_event_id": "e-001",
  "severity": "success",
  "visibility": "ui",
  "payload": {"status": "committed", "mutation_count": 3},
  "metadata": {}
}
```

Note: the Dream Engine does not yet exist; the example above is the intended target contract for Phase 2.
