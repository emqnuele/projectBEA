# SHURA Dream Engine — Phase 2 Foundation

Status: Foundation (not fully autonomous dreaming system)
Implemented: 2026-09-17 · Commit: `e6136e3`

## Architectural boundary

The Dream Engine is a backend transaction/subsystem layer. It does not own event transport (EventManager does), persistence format (JSONL journal does), or UI rendering (Command Center will observe, not drive).

The event contract (`docs/EVENT_CONTRACT.md`) is stable infrastructure. Dream events are emitted through the existing `EventManager.publish()` mechanism; no separate event bus exists.

## Domain boundary

Files in this phase:

- `src/core/dream/domain.py` — `DreamRun`, `DreamSnapshot` (durable, UI-independent)
- `src/core/dream/events.py` — Dream event taxonomy + emission helpers
- `src/core/skills/dream/dreamer.py` — instrumented with event emission hooks
- `src/core/skills/dream/surface.py` — passes `event_manager` to Dreamer

No new database. No daemon/service layer. No visualization.

## Lifecycle (explicit, replayable)

```
created → started → snapshot_created* → reconciliation_started →
reconciliation_completed → completed / failed
```

The lifecycle is deterministic and replayable via the existing event journal (`data/events/events.jsonl`). Replay filters (`run_id`, `subsystem=dream`) reconstruct the sequence without creating new event IDs.

States (`src/core/dream/domain.py`):

- `created`
- `started`
- `snapshot_created`
- `reconciliation_started`
- `reconciliation_completed`
- `completed`
- `failed`

A Dream run creates a stable `run_id`. All events within the run share the same `run_id`. Parent/child hierarchies use `parent_event_id`.

## Event taxonomy (current Phase 2)

| Event type constant | Value | When emitted |
|---|---|---|
| `EVENT_DREAM_STARTED` | `dream.started` | Dream execution begins |
| `EVENT_DREAM_SNAPSHOT_CREATED` | `dream.snapshot_created` | Session/conversation snapshot produced |
| `EVENT_DREAM_RECONCILIATION_STARTED` | `dream.reconciliation_started` | Memory application/reconciliation stage begins |
| `EVENT_DREAM_RECONCILIATION_COMPLETED` | `dream.reconciliation_completed` | Reconciliation stage finishes |
| `EVENT_DREAM_COMPLETED` | `dream.completed` | Entire Dream run succeeds |
| `EVENT_DREAM_FAILED` | `dream.failed` | Handled failure (e.g., no LLM available) |

Every Dream event includes:
- `event_type` (explicit)
- `subsystem=dream`
- `run_id` (correlation group)
- `parent_event_id` (when in hierarchy)
- `severity` (`info` / `success` / `error`)
- `visibility` (`ui` by default)
- `payload` (structured data, not arbitrary text)
- `message` (human-readable summary)

## Domain models

### DreamRun

Minimal durable execution model (`src/core/dream/domain.py`):

- `run_id`: stable identifier
- `state`: lifecycle state string
- `created_at` / `updated_at`: timestamps
- `parent_run_id`: optional parent correlation
- `correlation_id`: optional broader correlation
- `metadata`: minimal execution metadata (e.g., `commit_mode`)

No scheduling, no daemon behavior, no autonomous tick.

### DreamSnapshot

Durable observation of Dream subsystem state at a point in time:

- `run_id`: associated DreamRun
- `snapshot_id`: unique snapshot identifier
- `created_at`: timestamp
- `source_memory_ids`: list of memory node IDs (empty by default for future consolidation)
- `active_concepts`: list of concept strings
- `unresolved_threads`: list of unresolved thread strings
- `contradictions`: list of contradiction strings
- `metrics`: structured metrics dict (empty by default)

Snapshots are independent of UI rendering. They contain no PNG/OBS/avatar references.

## Integration with existing Dream code

`DreamSkill` (`src/core/skills/dream/surface.py`) passes `event_manager` to `Dreamer` when available. The `Dreamer` (`src/core/skills/dream/dreamer.py`) emits lifecycle events through the existing `EventManager` without replacing it.

Current behavior preserved:
- Session consolidation through LLM (`_dream_session`)
- Durable memory writes (`self.md`, people cards, `recent.json`)
- Idempotency (`_processed()` tracking)
- Morning pass (`DreamSkill.morning_pass()`)

Event emission is non-destructive: failures in event emission are caught (`try/except`) and logged; the Dream execution continues regardless. This ensures the event contract never corrupts the core Dream behavior.

## Persistence and replay

Dream events use the same `EventJournal` (`data/events/events.jsonl`) established in Phase 1. No separate Dream journal exists.

A Dream run can be reconstructed by filtering:

```python
replay = event_manager.replay(run_id="dream-run-...")
```

Replay rules verified by tests (`tests/test_dream_engine.py`):
- Original `event_id` preserved
- `sequence` preserved
- `run_id` preserved
- `parent_event_id` preserved
- `payload` preserved
- No new event IDs generated during replay

## Current limitations (explicit)

The Dream Engine is a foundation, not a fully autonomous dreaming system. The following features are intentionally deferred to later phases:

- `DreamSnapshot` fields (`source_memory_ids`, `active_concepts`, etc.) are empty or minimal; full consolidation/population requires Phase 3 (Memory Consolidation + Rehearsal).
- `DreamRun` lifecycle is basic; complex transaction states (`awaiting_commit`, `dry_run`, etc.) will be added in Phase 2 (Dream Transaction Core) when reconciliation/completion logic is expanded.
- No visual scene generation (`DreamSubstrate`, `scene.py`). Deferred to Phase 4.
- No streaming event output separate from journal persistence. Deferred to Phase 4.
- No simulated rehearsal stage. Deferred to Phase 3.
- No cross-agent dream sharing. Deferred to future architecture phases.

The event taxonomy is minimal and will expand as the Dream Engine grows. New event types should be added as constants in `src/core/dream/events.py` rather than as arbitrary strings.

## Tests

`tests/test_dream_engine.py` covers:

- `DreamRun` creation and lifecycle transition
- `DreamSnapshot` creation and serialization (`to_dict`)
- Dream event taxonomy constants
- Lifecycle emission (`started`, `snapshot_created`, `reconciliation_started`, `reconciliation_completed`, `completed`, `failed`)
- Correlation (`run_id` grouping, replay)
- Parent/child hierarchy (`parent_event_id`)
- Journal persistence and replay (original IDs preserved)
- Existing Dream behavior compatibility (`Dreamer` structural compatibility)

All 15 Dream tests pass (`python -m unittest` verified together with event tests: 37 total, OK).

## File inventory (Phase 2 only)

New:
- `src/core/dream/domain.py` (DreamRun, DreamSnapshot, lifecycle constants)
- `src/core/dream/events.py` (Dream event emission helpers)
- `tests/test_dream_engine.py`
- `docs/DREAM_ENGINE.md` (this document)

Modified (minimal, non-destructive):
- `src/core/skills/dream/dreamer.py` (optional `event_manager` parameter, lifecycle emission hooks with safe exception handling)
- `src/core/skills/dream/surface.py` (passes `event_manager` to Dreamer when available)

No modifications to:
- `brain.py` (composition root unchanged)
- `consciousness.py` (no Dream-specific changes)
- `events.py` (event transport unchanged; Dream uses existing APIs)
- `expression.py` (no Dream coupling)
- `memory.py` (memory consolidation deferred)
- `agent/tools.py` (agent events unchanged)
- `config.py` (no new config sections required for Phase 2)
- Embodiment/image/OBS architecture (preserved)
- Legacy mood IDs (`normal`, `shock`, `love`, `cry`, `angry`, `ew`, `bored`) preserved

The event contract (`docs/EVENT_CONTRACT.md`) remains the authoritative reference for event structure, persistence, replay, subscription, and taxonomy conventions.
