# Three Systems — V1 Definitions (VERIFIED + PROPOSED)

Based on verified repo inspection (`brain.py`, `events.py`, `skills/`, `dream/`, `memory/`, `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md`, `docs/ARCHITECTURE_AUDIT.md`, `docs/AGENTS.md`) and the design specifications (`Downloads/SHURA_Command_Center_and_Dream_Specs/`).

---

## PROJECTSHURA (VERIFIED — exists in repo)

**Purpose**: The persistent synthetic persona runtime — identity, cognition, skills, memory, dream, expression, event emission, and provider-agnostic reasoning.

**Verified components** (from file inspection + passing tests):
- `AIVtuberBrain` (`brain.py`)
- `Consciousness` (`consciousness.py`)
- `PerceptionBus` (`perception/bus.py`)
- `Expression` (`expression.py`)
- `EventManager` (`events.py`) + persistent JSONL journal
- `MemorySkill` + `MemoryStorage` (ChromaDB)
- `SocialMemory`
- `DreamSkill` + `Dreamer` + `DreamRun` + `DreamSnapshot` + projection boundary (`projection.py` — added in previous turn, verified by 48 passing tests)
- `Agent` / `LLMClient` / `ToolRegistry`
- `Config` (`config.py` → `config.json` + `BrainConfig`)
- `HistoryManager`
- Skill surfaces: `chat`, `voice`, `idle`, `minecraft`
- `FastAPI` web layer (`src/web/app.py`) + React/Vite skeleton (`frontend/`)
- CLI (`src/cli.py`)

**Non-responsibilities** (PROPOSED boundary — must be preserved):
- Does NOT own workspace navigation, persistent project workspace, or full workspace-based cockpit (those belong to FORGE).
- Does NOT own durable architecture documentation, decision logs, or cross-session knowledge indexing (those belong to ATLAS).
- Does NOT own harness orchestration as its primary interface (FORGE interfaces with harnesses; ProjectSHURA provides the runtime that harness agents access).

**State ownership**:
- Identity (`data/prompts/soul.md`, `operating.md`)
- Runtime config (`config.json` / `BrainConfig`)
- Memory (durable + ephemeral shadow-state framework)
- Event journal (`data/events/events.jsonl`)
- Skill registry / active skills
- Brain/composition root state (`AIVtuberBrain` instance)
- Session / history (`HistoryManager`)

**Inputs**: User input (text/audio), perception events (`PerceptionBus`), tool results (`Agent`), memory retrieval (`MemoryStorage`), configuration (`BrainConfig`).

**Outputs**: Assistant messages (text + mood), TTS audio, OBS expressions (avatar poses + text bubbles), event emission (`EventCategory` taxonomy), durable memory mutations (through reconciliation/commit framework — framework verified, full pipeline deferred).

**Persistence**: JSONL event journal, SQLite memory (`MemoryStorage` via ChromaDB), session/history files, `recent.json`, `self.md`, people cards, config file.

**Events emitted**: `system`, `input`, `output`, `thought`, `skill`, `tool`, `error`, `memory`, `agent`, `dream`, `embodiment` (verified taxonomy in `docs/EVENT_CONTRACT.md`). Dream-specific events: `dream.started`, `dream.snapshot_created`, `dream.reconciliation_started`, `dream.reconciliation_completed`, `dream.completed`, `dream.failed` (verified in `docs/DREAM_ENGINE.md`, `tests/test_dream_engine.py`).

**API / interfaces**: Internal Python interfaces (`brain.py` methods: `initialize()`, `generate_response()`, `generate_audio_response()`, `run_dream()`, `wake_up()`, `start_skills()`, `reload_configuration()`); web endpoints (`/chat`, `/audio`, `/discord/chat`, `/discord/audio`, `/voice/transcript`, `/memory/save`, `/skills`, `/skills/{name}/toggle`, `/events`, `/history`, `/status`, `/config`, `/dream/run`, `/dream/wake`, `/health`, `/dream/projection`); CLI (`main.py` / `cli.py`).

---

## ATLAS (VERIFIED — partial skeleton exists; PROPOSED — must become operational)

**Purpose**: Durable project-level knowledge, architecture, documentation, decisions, context indexing, session continuity, and cross-session reference — the persistent memory layer that survives individual runtime sessions and harness changes.

**Verified skeleton** (from file inspection):
- `docs/ATLAS_INTEROPERABILITY.md` (exists, skeleton, not modified during previous sequence)
- `docs/ATLAS_CANONICALIZATION_OPTIONS.md` (exists)
- `docs/ARCHITECTURE_AUDIT.md` (exists, 21KB)
- `docs/SHURA_MASTER_HANDOFF.md` (exists, 38KB, historical truth for inherited BEA architecture)
- `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` (exists, 10KB, planning baseline)
- `docs/IMPLEMENTATION_ROADMAP.md` (exists)
- `docs/INTEGRATION_MATRIX.md` (exists)
- `docs/RISKS_AND_CONFLICTS.md` (exists, 13KB)

**Current verified gap**: ATLAS is documentation-heavy but does not have an operational runtime layer — no automated indexing, no cross-session knowledge retrieval service, no durable architecture registry that feeds automatically into FORGE workspace context. The skeleton exists; operationalization is PROPOSED.

**Proposed operational layer** (must be built in V1 or post-V1):
- Canonical knowledge base (derived from docs + design specs + architecture audits + spec references)
- Project architecture registry (what ProjectSHURA is, what ATLAS is, what FORGE is, what the Dream Engine does, what the event contract requires)
- Session continuity (current branch, active milestone, last completed task, current loop phase, active blockages — derived from `docs/operations/LOOP_STATE.md` and `docs/operations/SESSION_HANDOFF.md`)
- Cross-session context retrieval (when SHURA resumes work, it reads ATLAS context + loop state + session handoff before reading source files)
- Reference mapping (OpenHuman → FORGE translation, Dream spec → current domain, event contract → current event types, identity rules → current identity layer)
- Decision log (why architecture choices were made, what was deferred, what was rejected)
- Open questions registry (`docs/design/OPEN_QUESTIONS.md` — proposed)

**State ownership** (PROPOSED):
- `docs/vision/`, `docs/design/`, `docs/operations/`, `docs/reference/`, `docs/tasks/`
- `docs/architecture/` (refined from existing `docs/architecture.md`)
- `docs/reference/OPENHUMAN_REFERENCE.md` (analysis of gitingest artifact for FORGE design reference)
- `docs/reference/V1_ACCEPTANCE.md` (observable criteria for V1)
- `docs/operations/LOOP_STATE.md` (current autonomous loop phase, milestone, active task, recent decisions, open blockages)
- `docs/operations/SESSION_HANDOFF.md` (durable handoff format for harness changes)
- `docs/tasks/V1_TASK_GRAPH.md` (dependency-aware task graph)
- `docs/tasks/V1_ROADMAP.md` (milestone-based roadmap with exit criteria)
- `docs/reference/ADR_INDEX.md` (architecture decision records)

**Inputs**: Design specs (`Downloads/SHURA_Command_Center_and_Dream_Specs/`), architecture audits (`docs/ARCHITECTURE_AUDIT.md`), openhuman reference (`tinyhumansai-openhuman` artifact), current repo state (`git status`, file structures, passing/failing tests).

**Outputs**: Context for autonomous loop (what phase, what milestone, what ready task, what blocked), reference for human review, design validation (does the current repo match the canonical architecture?), session continuity (when harness switches, ATLAS provides the durable context).

**Persistence**: Markdown files in `docs/`. Not a database. Read quickly by harness agents. Updated explicitly by autonomous loop and by design passes.

---

## FORGE (PROPOSED — does not exist as operational runtime; design only in this pass; framework skeleton may be added)

**Purpose**: The workbench / command center / workspace environment — the external interface of ProjectSHURA for collaboration, observation, task management, agent coordination, and autonomous work execution.

**Relationship to verified components**:
- Uses `ProjectSHURA` runtime (brain, events, skills, memory, dream) through stable application interfaces (`brain.run_dream()`, `brain.event_manager.subscribe()`, `brain.event_manager.replay()`, `/dream/projection` endpoint, `DreamStateProjection`).
- Consumes `ATLAS` context (current milestone, task graph, loop state, architecture references, session handoff) before selecting work.
- Does NOT absorb the brain runtime; does NOT become the identity layer; does NOT replace the Dream Engine domain boundary.

**Non-responsibilities** (must be preserved):
- Does NOT own SHURA identity (`soul.md` remains in ProjectSHURA identity layer).
- Does NOT own core cognition (brain/consciousness loop remains independent).
- Does NOT directly mutate `DreamRun` or `MemoryStorage` (mutation routed through `DreamSkill` / application service layer).
- Does NOT become a generic SaaS dashboard; must feel like a workspace/studio.

**Verified design reference**: `Downloads/SHURA_Command_Center_and_Dream_Specs/SHURA_COMMAND_CENTER_SPEC.md` (spec), `SHURA_DREAM_ENGINE_SPEC.md` (spec), OpenHuman reference (`tinyhumansai/openhuman` artifact — 1.3M lines of directory structure, React/Vite frontend, agent/task/workflow architecture, mascot/agent presentation, event/subscription model, desktop/runtime model). OpenHuman is a REFERENCE for product experience and workspace model, not a direct upstream.

**Design direction derived from verified sources + reference**:
- Central workspace (not a chat-only UI).
- SHURA embodied agent present (current: PNG/sprite-based; future: Live2D/3D — must have a defined presentation-state contract that does not couple to brain internals).
- Navigation surfaces: Overview (system state), Workspace (primary collaboration), Memory (observations from DreamSnapshot + memory events), Dream Studio (Dream state + events), Agents (sub-agents/tasks), Skills (skill registry + invocation), MCP/Tools (server/tool inspection), Artifacts, Activity/Event stream (durable replay + live feed), System (health/config/status).
- Workspace model: projects/open files/tasks/agents/state visible together, not hidden behind navigation.
- Event subscription: `EventManager.subscribe()` mechanism already exists; FORGE uses it (does not create a new event bus).
- Task/agent observation: visible execution, blocked states, approvals, completions, failures.
- Command palette / quick actions: not required for V1, but the architecture must leave an extension point (navigation + workspace design must allow future command input without restructuring).

**State ownership** (PROPOSED):
- Workspace/project/session state (what is open, what task is active)
- Agent/task state (assigned, queued, running, blocked, completed)
- UI presentation state (navigation selection, visible panels, collapsed/expanded state)
- Event subscription state (what filters/subscriptions are active for UI observation)
- User interaction state (pending approvals, interrupted tasks, command input history — not persistent identity state)

**Inputs**: User interaction (navigation selection, task creation, agent invocation, command input), `ProjectSHURA` runtime events (`brain.event_manager.subscribe()` results), `ATLAS` context (`docs/operations/LOOP_STATE.md`, `docs/tasks/V1_TASK_GRAPH.md`), external services (MCP server responses, tool results).

**Outputs**: User-visible workspace state, event observation feed, task execution results, agent coordination results, approval decisions (routed back to brain/consciousness through application interfaces, not arbitrary access), updated loop state (`docs/operations/LOOP_STATE.md` updates when autonomous work completes).

**Persistence**: Workspace/project/session data (future database or file-based workspace state), event observation history (derived from `events.jsonl`, not a separate UI database), user settings (separate from `BrainConfig` — UI settings are presentation settings, not identity/cognition settings).

**Critical boundary preservation** (verified + proposed):
- UI does not own cognition. The brain/consciousness loop (`brain.py`) remains independent of `FORGE` workspace rendering. `Expression` adapter is a downstream projection of core state; `FORGE` UI also observes core state through the same event/projection mechanism. There is no direct brain → UI mutation path that bypasses the event/projection layer.
- Dream Engine does not depend on UI. The Dream domain (`domain.py`, `events.py`, `projection.py`) uses `EventManager` for emission; `FORGE` subscribes/replays. There is no `DreamEngine` import in the UI layer that creates a dependency cycle. The `/dream/projection` endpoint demonstrates this: it takes `run_id`, creates a minimal `DreamRun`, passes it through `build_projection()` with `brain.event_manager`, and returns `to_dict()`. No direct mutation. No import of consciousness/expression/avatar.
- Identity independent from provider. `FORGE` displays current provider/model reference (operational state) but the identity files (`data/prompts/soul.md`) contain no provider names. Changing providers does not change identity. Changing identity requires explicit governed review (per memory rules + identity sync skill).
