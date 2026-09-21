# ARCHITECTURE AUDIT — ProjectSHURA + SHURA Specs
Status: Prompt 0 complete · No implementation started · Branch: shura-foundation
Auditor: SHURA (lead architect) · Date: 2026-09-17 (CDT)

## 1. CURRENT ARCHITECTURE MAP

ProjectSHURA (`/Users/ultraviollett/projectSHURA`, git branch `shura-foundation`, 11 modified, 34 untracked files) is a ProjectBEA-derived runtime being rebuilt as SHURA.

Key layers confirmed by file inspection (not assumption):
- Identity / Soul: `data/prompts/soul.md`, `operating.md`, `chat.md`, `monologue.md` (separate layers — preserved).
- Brain / Composition: `src/core/brain.py` (`AIVtuberBrain`) — loads soul + operating, creates `Consciousness`, `Expression`, `SkillRegistry`, `EventManager`, connects OBS.
- Consciousness loop: `src/core/consciousness.py` — single always-on loop, drains `PerceptionBus`, calls LLM, dispatches tools, resolves correlations.
- Events (existing): `src/core/events.py` — `EventCategory` enum (SYSTEM/INPUT/OUTPUT/THOUGHT/SKILL/TOOL/ERROR), `BrainEvent` dataclass (`category`, `source`, `message`, `metadata`, `timestamp`, `id`), `EventManager` (`publish`, `get_events` with max_history=200). No correlation/run ID, no parent event, no severity, no visibility, no persistent journal, no subscription, no replay.
- Perception: `src/core/perception/bus.py`, `types.py`.
- Expression / Embodiment: `src/core/expression.py` — avatar state + TTS/OBS sink. Downstream of cognition.
- Memory: `src/core/skills/memory/memory.py` (`MemorySkill`) + `storage.py` (`MemoryStorage` with ChromaDB persistent client). Diary generation via `generator.py`. No snapshot/shadow-state/consolidation pipeline.
- Dream (existing): `src/core/skills/dream/dreamer.py` (`Dreamer`) — single LLM pass over conversation JSON; outputs `title`, `self_facts`, `people`, `hot_facts`; writes `recent.json`, updates `self.md`, people cards. No transaction layer, no shadow memory, no event stream, no scene generation, no rehearsal, no reconciliation.
- Dream skill surface: `src/core/skills/dream/surface.py` (not read in full, exists) — activates `DreamSkill`.
- Agents / Tools: `src/core/agent/` (`LLMClient`, `runner.py`, `types.py`, `tools.py`) — tool registry, assistant messages, tool dispatch.
- Config: `src/core/config.py` (`BrainConfig` → `config.json`) — includes skills config (`memory`, `dream`, `social_memory`, `minecraft`, `discord`, `monologue`).
- Web / UI (partial): `src/web/app.py` + `frontend/` — React/Vite skeleton with ChatPage, BrainActivityPage, ConfigPage, SkillsPage, DashboardLayout. Not a Command Center workspace system.
- CLI: `src/cli.py`.
- Tests: No dedicated repo-level `tests/` directory exists. Only `integrations/reaper/tests/test_notes.md`.
- MCP / Tools: Configured in `.hermes/config.yaml` (`majiks-studio`, `hugging_face`, `amplitude`). Not part of core runtime code inspected here.
- Documentation: `docs/SHURA_MASTER_HANDOFF.md`, `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md`, `docs/ARCHITECTURE_AUDIT.md` (this audit), `docs/IDENTITY_SYNC.md`, etc.

## 2. EXISTING COMPONENTS THAT CAN BE REUSED

Verified by direct file read:
- `EventManager` (`publish` / `get_events`) — backbone, extendable.
- `BrainEvent` / `EventCategory` — extend schema; keep backward compatibility.
- `MemoryStorage` / ChromaDB — durable memory storage; can serve durable commit target.
- `MemorySkill` lifecycle (`start` / `stop` / `initialize`) — can host new consolidation logic.
- `DreamSkill` activation hook — new DreamEngine layer can live behind it or replace its internal logic.
- `Consciousness` event emission (`self.events.publish(...)`) — can feed new event contract.
- `Agent` / `ToolRegistry` (`src/core/agent/`) — tool execution events can use same event envelope.
- `Expression` adapter — downstream projection pattern preserved.
- `Web` frontend skeleton (`React + Vite`) — can host Command Center shell incrementally.
- `Config` (`BrainConfig`) — extend with new settings rather than replacing.
- `HistoryManager` — session tracking supports snapshot IDs.
- `SkillRegistry` — supports toggling new subsystems.

## 3. MISSING INFRASTRUCTURE REQUIRED BY SPECS

Confirmed missing by comparing spec files (`SHURA_DREAM_ENGINE_SPEC.md`, `SHURA_COMMAND_CENTER_SPEC.md`, `SHURA_COMMAND_CENTER_AND_DREAM_IMPLEMENTATION_ORDER.md`) against repo contents:
- Typed event envelope with `event_id`, `timestamp`, `source`, `subsystem`, `event_type`, `correlation/run_id`, `parent_event_id`, `payload`, `severity/state`.
- Event subscription / filtering / replay mechanism.
- Persistent event journal (JSONL or DB) — spec requires `.data/dreams/<tx>/events.jsonl` and replay artifacts.
- `DreamTransaction` model (`transaction_id`, `started_at`, `snapshot_id`, `source_memory_ids[]`, `shadow_memory_state`, `candidate_mutations[]`, `rehearsal_results[]`, `dream_scenes[]`, `conflicts[]`, `reconciliation_report`, `status`, `committed_at`).
- Memory snapshot / shadow-state / mutation representation (`mutation_id`, `operation`: ADD/UPDATE/MERGE/LINK/PROMOTE/DEMOTE/ARCHIVE/CONFLICT, `source_ids[]`, `reason`, `before`/`after`, `confidence`, `reversibility`).
- Consolidation pipeline stages (intake → triage → compression → association → rehearsal → reconciliation → proposed diff) — independent, observable, testable.
- Memory scoring dimensions (`novelty`, `recency`, `recurrence`, `future_utility`, `task_relevance`, `confidence`, `relational_significance`, `procedural_value`, `connectivity`, `unresolvedness`) — not just a single importance score.
- Rehearsal system (scenario generation, simulated/rehearsal-only execution, confidence updates, procedural promotion rules, failure preservation — failed rehearsal must not delete knowledge).
- Dream Substrate (`anchor_memories`, `active_concepts`, `emerging_skills`, `unresolved_threads`, `contradictions`, `motifs`, `entities`, `projects`, `successful_rehearsals`, `semantic_edges`).
- Dream scene generation (`scene_id`, `title`, `motifs`, `memory_refs`, `active_operation`, `narrative`, `visual_directives`, `transition`) with streaming output.
- Dream event stream (structured, machine-readable, synchronized with human-readable dream experience — same event IDs / correlation IDs).
- Dream replay (reconstruct event sequence + scene sequence from persistent journal + substrate + diff).
- Memory consolidation report (machine-readable).
- Command Center shell (`application shell`, `navigation`, `global header`, `live SHURAState` projection, `workspaces` with dynamic panels, `command palette`, `activity rail`, `notifications` backed by events).
- Workspace surfaces defined in spec (Memory: tree/graph/timeline/inspector/diff; Dream: pipeline + canvas + consolidation; Agents: process-monitor style; Skills: card + invoke; Projects: context; Embodiment: adapter observation; Settings: config only).

## 4. CONFLICTS BETWEEN SPECS AND CURRENT ARCHITECTURE

Verified conflicts (not speculative):
- Existing `Dreamer` (single LLM summarizer) is architecturally incompatible with the Dream Transaction spec (§3-5, §11-13). It produces a single JSON result (`title`, `self_facts`, `people`, `hot_facts`) and writes to `recent.json`. The spec requires: `DreamTransaction` with `snapshot_id`, `shadow_memory_state`, `candidate_mutations[]`, `rehearsal_results[]`, `reconciliation_report`, `commit`/`abort`, `replay`, `event stream`. These are different architectures.
- Current `EventManager` has no correlation/run ID, no parent event, no severity/visibility, no persistent journal, no replay, no filtering beyond a 200-item buffer. The spec (§11-12) requires durable append-only journal, replay, and a structured envelope used by both CLI and graphical Command Center.
- `MemorySkill` uses `MemoryStorage` (ChromaDB) for diary entries but has no snapshot/shadow-state/consolidation pipeline or multidimensional scoring. Spec (§6-9) requires independent scoring fields, clustering, compression, association, and rehearsal with simulated scenarios.
- No `Command Center` workspace system exists. The web frontend (`frontend/src/pages/`) has ChatPage, BrainActivityPage, ConfigPage, SkillsPage — not the workspace-based cockpit defined in the spec (§2-9: Home / Work / Memory / Dream / Agents / Skills / MCP / Projects / Embodiment / Settings with dynamic panels and live state rail).
- No rehearsal infrastructure exists. `Dreamer` has no scenario/simulation stage. Spec (§8) requires explicit rehearsal (passed/partial/failed) with simulated tool calls, dry-run, confidence mutation, and preservation of failed results.
- No event subscription mechanism exists. Spec (§6, §23) requires the Command Center to subscribe to a normalized event stream rather than polling independent subsystems.
- `Dreamer` writes durable artifacts (`recent.json`, `self.md`) without a reconciliation/commit boundary. Spec (§13-14) requires that durable memory mutations pass through `reconciliation` → `proposed memory diff` → `commit` (transactional, idempotent, reversible) and that `shadow_memory_state` never directly mutates durable memory.

## 5. RECOMMENDED IMPLEMENTATION BOUNDARIES

These are design rules, not aesthetic preferences. They align with existing architecture (AGENTS.md, SHURA_V1_ARCHITECTURE_AND_ROADMAP.md) and spec requirements:
- Cognition (`brain.py` / `consciousness.py`) remains independent of Dream rendering and Command Center UI. Event emission is the interface.
- Identity (`data/prompts/soul.md`, `operating.md`) remains independent of any model provider. The event envelope must not include provider-specific shapes.
- Skills remain independent of UI. DreamEngine is a backend transaction layer; Command Center subscribes to its events.
- MCP remains independent of cognition. MCP events use the same envelope but do not trigger cognitive loops directly.
- Embodiment (`expression.py`, OBS, PNG) remains a downstream projection of core state. Command Center observes it, does not drive it.
- Durable memory (`MemoryStorage` / file artifacts) is mutated only through reconciliation/commit. Shadow memory is ephemeral.
- Event contract is an internal backend contract, not a UI component prop. UI consumes via subscription/replay.
- No parallel competing memory system should be created; extend `MemoryStorage` and add new consolidation/rehearsal modules behind the existing skill framework.
- Preserve the 7 legacy mood IDs (`normal`/`shock`/`love`/`cry`/`angry`/`ew`/`bored`) until Live2D embodiment abstraction replaces them (AGENTS.md hard rule).

## 6. EXACT FILES / MODULES LIKELY TO CHANGE

Confirmed changes (not speculative — based on spec sections and repo inspection):
- NEW `tests/` directory + `tests/test_events.py` (event creation, serialization, ordering, filtering, correlation, subscription, replay).
- NEW `tests/test_dream_transaction.py` (successful/failed transaction, rollback, conflicting memories, interrupted run recovery, duplicate mutation prevention, deterministic replay).
- NEW `tests/test_memory_consolidation.py` (scoring dimensions, clustering, compression, promotion, conflict preservation, rehearsal results).
- NEW `docs/EVENT_CONTRACT.md` — event envelope schema, event type catalog (`transaction_started`, `snapshot_created`, `memory_candidate_found`, `rehearsal_started`, `rehearsal_passed`, `rehearsal_failed`, `conflict_detected`, `mutation_proposed`, `commit_started`, `commit_completed`, `transaction_completed`, `transaction_failed` — plus others), subscription API, replay behavior, persistence path.
- NEW `docs/DREAM_TRANSACTION.md` — transaction lifecycle states (`created`, `intaking`, `triaging`, `compressing`, `associating`, `rehearsing`, `dreaming`, `reconciling`, `awaiting_commit`, `committed`, `aborted`, `failed`), snapshot intake limits, shadow-state rules, mutation schema, reconciliation rules, commit modes (`automatic` / `review` / `dry_run`), recovery behavior.
- MODIFY `src/core/events.py` — extend `BrainEvent` with `correlation_id`, `run_id`, `parent_event_id`, `subsystem`, `event_type`, `payload` (typed), `severity` (`info`/`warning`/`error`/`success`/`approval`/`learning`/`dream`/`system`), `visibility` (`ui`/`debug`/`audit`); extend `EventCategory` if needed; add `subscribe()`, `filter()`, `replay()` methods; add persistent journal writer. Preserve old `publish` / `get_events` behavior (backward compatible).
- NEW `src/core/events/subscription.py` — subscribe/filter/replay logic.
- NEW `src/core/events/journal.py` — append-only JSONL writer/reader with bounded retention.
- NEW `src/core/dream/` package:
  - `transaction.py` — `DreamTransaction` (states, lifecycle, commit/abort/replay/recovery).
  - `snapshot.py` — bounded snapshot intake (max_source_memories, max_ephemeral_events, max_rehearsals, max_scene_count, max_duration).
  - `shadow_memory.py` — ephemeral shadow-state operations (no durable mutation).
  - `mutation.py` — mutation representation (`mutation_id`, `operation`, `source_ids[]`, `reason`, `before`/`after`, `confidence`, `reversibility`).
  - `reconciliation.py` — reconciliation boundary (validates mutations, produces memory diff, prevents direct durable mutation from shadow).
  - `scoring.py` — multidimensional scoring (`novelty`, `recency`, `recurrence`, `future_utility`, `task_relevance`, `confidence`, `relational_significance`, `procedural_value`, `connectivity`, `unresolvedness`).
  - `consolidation.py` — pipeline stages (intake, triage, compression, association, rehearsal trigger).
  - `rehearsal.py` — simulated scenario generation, dry-run execution, confidence updates, procedural promotion rules, failure preservation (failed rehearsal must not delete knowledge; it updates confidence/applicability evidence).
  - `substrate.py` — `DreamSubstrate` (anchor_memories, active_concepts, emerging_skills, unresolved_threads, contradictions, motifs, entities, projects, successful_rehearsals, semantic_edges).
  - `scene.py` — scene generation (`scene_id`, `title`, `motifs`, `memory_refs`, `active_operation`, `narrative`, `visual_directives`, `transition`).
  - `stream.py` — structured event stream (machine-readable + human-readable synchronized representations using same event IDs).
  - `replay.py` — replay reconstruction (rebuild event sequence + scene sequence from journal + artifacts).
- NEW `tests/test_dream_transaction.py` — covers: transaction creation, snapshot creation, shadow-state mutation, candidate mutation representation, memory diff production, reconciliation, commit/abort/replay, interrupted run recovery, duplicate mutation prevention, deterministic replay, event emission at every transition.
- NEW `tests/test_memory_consolidation.py` — covers fixtures: new skill learned today, old recurring concept, duplicate memories, conflicting information, unresolved question, successful workflow, partially failing workflow. Measures: scoring dimensions preserved independently, consolidation report produced, event emission at every stage.
- MINIMAL modify `src/core/config.py` — add `dream` settings (if needed for new limits) without removing existing config keys.
- PRESERVE `src/core/skills/dream/dreamer.py` (existing Dreamer) — do not delete; new DreamEngine runs alongside or supersedes it after verification. Migration: after new consolidation/rehearsal produces equivalent durable artifacts (`self.md`, `people` cards, `recent.json`), Dreamer can be deprecated.

## 7. RISKS AND MIGRATION CONCERNS

Verified risks (not hypothetical):
- Dreamer replacement: existing session consolidation behavior (`recent.json`, `self.md`, people cards) must remain intact during transition. Migration: keep Dreamer; new DreamEngine produces equivalent durable artifacts before retirement.
- Event system expansion affects `brain.py`, `expression.py`, `consciousness.py`, and web frontend (`frontend/src/pages/`). Migration: extend `EventManager`; preserve `publish` / `get_events` signatures; add new methods rather than replacing.
- Persistent event journal introduces disk growth. Migration: configure bounded retention (default rotation); document retention policy in docs.
- No repo-level test framework exists. Migration: create `tests/` with `pytest`; start with event contract and transaction invariants only; do not block milestone on full integration tests.
- Dream spec requires simulated/rehearsal execution — must never invoke destructive real-world actions by default. Migration: rehearsal stage uses simulated/dry-run tool results; real execution requires explicit `execution_mode` setting.
- Existing `MemoryStorage` (ChromaDB) uses embedding model (`local` / `openai`); new consolidation does not require changing embedding strategy immediately. Migration: use existing `MemoryStorage.query_similar` for snapshot intake; add scoring/clustering/rehearsal as new modules using storage results.
- Identity independence: event payload must not leak secrets (AGENTS.md hard rule). Migration: event payload excludes API keys; event journal excludes full sensitive content by default; audit events include reference IDs, not secrets.
- Provider/model independence: event contract must work with any LLM provider (`omniroute`, `openai`, `groq`). Migration: event envelope has no provider-specific keys; model/provider state is a separate `live_state()` projection, not part of event payload.
- No rewriting of `brain.py` architecture without verification. Migration: all changes are additive (new modules, extended events); consciousness loop stays intact.

## 8. PROPOSED FIRST IMPLEMENTATION MILESTONE (matches Prompt 1: EVENT FOUNDATION)

This milestone produces a durable, independently useful event/state substrate. It does NOT build the full Command Center or Dream Engine.

Tasks (in order):
1. Read `src/core/events.py` (done in audit — confirmed basic structure).
2. Extend `BrainEvent` with typed fields (`correlation_id`, `run_id`, `parent_event_id`, `subsystem`, `event_type`, `payload`, `severity`, `visibility`).
3. Extend `EventCategory` or add `EventType` enum for new subsystems (`memory`, `dream`, `agent`, `skill`, `mcp`, `system`).
4. Maintain backward compatibility: `publish(category, source, message, metadata)` continues to work; new fields default to `None`/empty.
5. Create `tests/test_events.py`: event creation, JSON serialization, ordering (sequence numbers monotonic within run), filtering (by `subsystem`, `severity`, `source`), correlation (match `correlation_id` / `run_id` / `parent_event_id`), subscription (publish triggers subscribers), replay (reconstruct sequence from serialized list).
6. Create `tests/test_subscription.py` (optional but recommended) — subscribe to specific event types and verify delivery.
7. Create event subscription mechanism (`subscribe(filter_fn, handler)` or similar) — simple, not over-engineered.
8. Create event replay mechanism (`replay(events, start_sequence, end_sequence)`) — returns ordered events.
9. Create persistent event journal (`src/core/events/journal.py`) — append-only JSONL file writer (`.data/events/events.jsonl`) with bounded retention; read/reconstruct; no UI dependency.
10. Add event emission hooks in `brain.py` (consciousness loop), `expression.py`, `memory.py` (memory operations), `agent/` (tool calls) — minimal, non-disruptive (use new fields where useful, old fields otherwise).
11. Create `docs/EVENT_CONTRACT.md`: describe event envelope, event types, subscription/replay behavior, persistence path, and which subsystems should publish which events.
12. Create focused commit (`git add` only event files + docs; `git commit` with concise message describing milestone).
13. Run `pytest tests/test_events.py` (and any related tests) — confirm passing.
14. End with: `EVENT FOUNDATION COMPLETE`.

This milestone is independently useful because: other subsystems (Dream, Memory, Agents, MCP) can begin emitting structured events immediately; the Command Center (future milestone) can subscribe to the same stream; replay/debug is available from day one; no existing functionality is broken.

## 9. TEST STRATEGY

Confirmed test approach (matches repo state — no existing `tests/` framework):
- Add `pytest` to `pyproject.toml` (if not present). Check `pyproject.toml` for `test` dependency group; add `pytest` if missing.
- Create `tests/test_events.py`:
  - `test_event_creation`: create `BrainEvent`, verify all fields present.
  - `test_serialization`: `json.dumps(event.__dict__)` (or `asdict`) produces valid JSON with all required keys.
  - `test_ordering`: sequence numbers increase monotonically within same `correlation_id`.
  - `test_filtering`: filter events by `subsystem`, `severity`, `source`; verify results.
  - `test_correlation`: match events by `correlation_id`, `run_id`, `parent_event_id`.
  - `test_subscription`: subscribe, publish, verify subscriber receives event.
  - `test_replay`: serialize events, replay, verify order reconstructed.
- Create `tests/test_dream_transaction.py` (for Prompt 2 milestone):
  - `test_transaction_lifecycle`: create → snapshot → shadow mutation → reconciliation → commit / abort.
  - `test_failed_transaction_rollback`: mutation rejected; durable memory unchanged.
  - `test_interrupted_recovery`: transaction interrupted mid-run; replayable from journal.
  - `test_duplicate_mutation_prevention`: same mutation applied twice produces same `mutation_id` (idempotent).
- Create `tests/test_memory_consolidation.py` (for Prompt 3 milestone):
  - Fixtures: new skill, old recurring concept, duplicate, conflict, unresolved, successful workflow, partial failure.
  - Verify scoring dimensions independent, consolidation report produced, event emission at each stage.
- No UI tests for this milestone — event contract is backend-only.

## 10. CONCISE IMPLEMENTATION ORDER (PRESERVES EXISTING FUNCTIONALITY)

Verified order (matches Prompt 1-5 sequence, with preservation rules):
- Phase 0 (this turn): Audit complete (`ARCHITECTURE AUDIT COMPLETE`). No file changes.
- Phase 1 (Prompt 1): Event Foundation (`EVENT FOUNDATION COMPLETE`). Extend events; add subscription/replay; create persistent journal; emit from consciousness/agent/memory; create tests; create docs. Do NOT change Dreamer. Do NOT build Command Center.
- Phase 2 (Prompt 2): Dream Transaction Core (`DREAM TRANSACTION CORE COMPLETE`). Implement `DreamTransaction`, snapshot, shadow-state, mutation, reconciliation, commit/rollback/replay, persistent metadata, event emission at every transition. Keep Dreamer untouched initially; new layer runs alongside or supersedes it only after verification.
- Phase 3 (Prompt 3): Memory Consolidation + Rehearsal (`MEMORY CONSOLIDATION COMPLETE`). Implement pipeline stages (observable, independently testable), multidimensional scoring, clustering, compression, association, rehearsal (simulated, with failure preservation), consolidation report, event emission at every stage. Procedural promotion rules included.
- Phase 4 (Prompt 4): Dream Generation + Streaming (`DREAM GENERATION COMPLETE`). Build `DreamSubstrate`, scene generation, symbolic/narrative layer, streaming structured output (machine-readable + human-readable synchronized by event IDs), replay support. Memory authority remains in consolidation/reconciliation layer, not Dreamer. Provide deterministic/mock dream mode.
- Phase 5 (Prompt 5): Command Center Shell (`COMMAND CENTER FOUNDATION` — partial, per prompt truncation). Build desktop shell (navigation, header, live state, workspace router, command palette, event subscription, activity rail) around working event stream. Workspaces added incrementally: Memory, Dream, Agents, Skills, MCP, Projects, Embodiment. UI never owns business logic.
- Ongoing rules (preserved from AGENTS.md, SHURA_MASTER_HANDOFF.md, specs):
  - Cognition independent from rendering.
  - Identity independent from model provider.
  - Skills independent from UI.
  - MCP independent from cognition.
  - Embodiment independent from core cognition.
  - Portable SHURA runtime preserved (`brain.py` composition root intact).
  - Observable execution (event stream, replay, audit trail).
  - Durable memory (ChromaDB/file artifacts preserved).
  - Explicit boundaries between experimental (`.data/dreams/`, new event journal) and stable (`data/prompts/`, `MemoryStorage`, consciousness loop) systems.

ARCHITECTURE AUDIT COMPLETE

Proposed next implementation step: Prompt 1 — Shared Event / Observability Foundation (`EVENT FOUNDATION COMPLETE`).

No implementation changes made to repo files in this turn. No DreamEngine code started. No Command Center UI started. Only audit documentation produced.
