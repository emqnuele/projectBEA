# SHURA V1 Vision — Design Document (VERIFIED + PROPOSED)

Status: Design / architecture pass
Branch: shura-foundation
Source authority hierarchy (verified in AGENTS.md + memory):
  1. Verified current repo implementation (source of truth for what exists)
  2. SHURA specs in Downloads/SHURA_Command_Center_and_Dream_Specs/ (design targets)
  3. docs/AGENTS.md / docs/SHURA_MASTER_HANDOFF.md (historical architecture)
  4. docs/ARCHITECTURE_AUDIT.md / docs/projectshura-architecture-audit-pattern.md (audit results)
  5. docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md (existing planning baseline)
  6. Gitingest / OpenHuman artifact (external REFERENCE implementation for FORGE, not source of truth)

---

## 1. Verified Current Implementation (VERIFIED — not proposed)

ProjectSHURA is a ProjectBEA-derived runtime rebuilt as SHURA. Verified by file inspection and git history:

- Brain / composition root: `src/core/brain.py` (`AIVtuberBrain`) — loads soul + operating manual, creates `EventManager`, `Expression`, `Consciousness`, `PerceptionBus`, `SkillRegistry`, connects to modules.
- Consciousness loop: `src/core/consciousness.py` — drains `PerceptionBus`, calls LLM, dispatches tools.
- Events: `src/core/events.py` (`BrainEvent`, `EventCategory`, `EventManager`) with `subscribe()`, `replay()`, `publish()`, persistent JSONL journal (`data/events/events.jsonl`). No correlation/run ID before Phase 2; extended in the event contract (`docs/EVENT_CONTRACT.md`).
- Dream Engine (Phase 2 verified): `src/core/dream/domain.py` (`DreamRun`, `DreamSnapshot`), `events.py` (taxonomy + emission helpers), `transaction.py` (minimal `MemoryConsolidationTransaction`), `consolidation.py` (`ConsolidationEngine`). No visual scene generation. No streaming event output separate from journal. Event contract uses existing `EventManager`.
- Memory: `MemoryStorage` (ChromaDB persistent client), `MemorySkill` (`memory.py`), `generator.py` (diary generation). No shadow-state/consolidation pipeline fully implemented (framework exists, full pipeline deferred).
- Skills: `DreamSkill` (`surface.py` + `dreamer.py`), `MemorySkill`, `SocialMemory`, `ChatSurface`, `VoiceSurface`, `IdleSurface`, `MinecraftSurface`. All use `SkillRegistry`.
- Web / UI: FastAPI (`src/web/app.py`) + React/Vite skeleton (`src/web/frontend/`). Endpoints include `/chat`, `/audio`, `/discord/chat`, `/discord/audio`, `/voice/transcript`, `/memory/save`, `/skills`, `/skills/{name}/toggle`, `/events`, `/history`, `/status`, `/config`, `/dream/run`, `/dream/wake`, `/health`. Frontend has `LandingPage`, `ChatPage`, `BrainActivityPage`, `ConfigPage`, `SkillsPage`, `DashboardLayout`. Not a workspace-based cockpit.
- CLI: `src/cli.py`.
- MCP integration configured (`.hermes/config.yaml`) — `majniks-studio` (verified 148 tools, live verified in audit), `hugging_face`, `amplitude`. Integration audit verifies with `execute_code` POST, not just `lsof`/port checks.
- Avatar / embodiment: PNG avatar resources (`load_avatar_resources`, `png_map`), OBS websocket (`obs_websocket.py`), `Expression` adapter. Legacy mood IDs preserved (`normal`, `shock`, `love`, `cry`, `angry`, `ew`, `bored`). No Live2D/3D embodiment.
- Identity: `data/prompts/soul.md`, `operating.md`, `chat.md`, `monologue.md`, `minecraft.md`. Separate layers preserved.
- Configuration: `BrainConfig` (`src/core/config.py`) → `config.json`. Includes skills config (`memory`, `dream`, `social_memory`, `minecraft`, `discord`, `monologue`).
- Tests: `tests/test_events.py` (22 passing), `tests/test_dream_engine.py` (15 passing), `tests/test_memory_consolidation.py` (verified present), plus the new projection tests (`tests/test_dream_projection.py`, 11 passing) added in this design pass.

No claim made that the full Dream Transaction spec is implemented. Only the Phase 2 foundation (`DreamRun`, `DreamSnapshot`, event taxonomy, non-destructive emission hooks) is verified. The full `DreamTransaction` lifecycle, `shadow_memory_state`, `rehearsal_results`, `dream_scenes`, `DreamSubstrate`, streaming output, and memory consolidation pipeline stages remain PROPOSED / deferred.

No claim made that the full Command Center workspace system exists. Only the `/dream/projection` endpoint (read-only projection interface added this turn) and `/dream/run` mutation endpoint exist. The workspace-based cockpit with navigation, global header, workspace router, command palette, event subscription, live SHURAState projection, Memory/Dream/Agents/Skills/MCP/Projects/Embodiment surfaces — all PROPOSED based on `SHURA_COMMAND_CENTER_SPEC.md`.

---

## 2. Design Intent: Why V1 Must Look Different

The objective is NOT to produce a polished dashboard. The objective is a coherent operating environment in which:

1. SHURA is present as an embodied agent, not an abstract API endpoint.
2. SHURA's current state is observable (not hidden inside brain internals).
3. The user can observe work in progress (tasks, agents, events, dream state) without disrupting it.
4. The system can operate autonomously (read vision, inspect state, select task, implement, test, update state, continue) when the user is not actively directing it.
5. The architecture is portable (not locked to one model provider, one embodiment format, one harness, or one frontend framework).
6. The identity layer remains independent of provider, model, avatar PNG file path, or temporary runtime mood.

The design metaphor is: **command center / shared studio / cockpit** — not a settings panel, not an admin dashboard, not a generic SaaS interface.

---

## 3. Core Architectural Rules (PROPOSED — must be preserved through V1)

These rules are derived from the verified architecture (`docs/AGENTS.md`, `docs/ARCHITECTURE_AUDIT.md`, `docs/SHURA_MASTER_HANDOFF.md`, event contract, brain composition, identity separation):

1. **Identity independence**: `data/prompts/soul.md` and operating rules must not include provider names, avatar file paths, OBS settings, or temporary mood IDs as identity content. Identity is separate from substrate.
2. **Cognition independence from embodiment**: `brain.py`, `consciousness.py`, `perception/bus.py` must not import `expression.py`, `png_map`, avatar file references, or OBS interfaces directly. Event emission (`EventCategory.OUTPUT`, `EventCategory.EMBODIMENT`) is the interface.
3. **Dream Engine boundary**: `src/core/dream/` owns domain logic (`DreamRun`, `DreamSnapshot`, event taxonomy, consolidation engine framework). The projection layer (`projection.py`, added this design pass) is a separate read-only boundary. Mutation must flow through `DreamSkill` or explicit application commands (`/dream/run` endpoint), never through projection.
4. **Event contract is internal backend infrastructure**: `docs/EVENT_CONTRACT.md` defines the envelope (`event_type`, `subsystem`, `run_id`, `parent_event_id`, `payload`, `severity`, `visibility`). UI consumes via `subscribe()` / replay; UI does not own event taxonomy.
5. **Skill independence from UI**: Skills (`memory/`, `dream/`, `social/`, `chat/`, `voice/`, etc.) are registered via `SkillRegistry`. The web/app endpoints observe skill state (`/skills`, `/skills/{name}/toggle`) rather than driving skills through arbitrary brain internals.
6. **Memory mutation through reconciliation/commit**: Durable memory (`MemoryStorage`, ChromaDB) must not be modified directly by Dream imagination. Shadow-state/proposal/reconciliation/commit boundary (`MemoryConsolidationTransaction`, `MemoryProposal`) must be respected once fully implemented. The framework (`transaction.py`, `consolidation.py`) exists; full pipeline integration is deferred.
7. **ProjectSHURA modular and portable**: Components must be swappable (`LLMClient` factory, `TTSInterface`, `STTInterface`, `OBSInterface`, skill surfaces). No component should assume the presence of another unless explicitly composed in `brain.py`.
8. **Legacy mood IDs preserved**: `normal`, `shock`, `love`, `cry`, `angry`, `ew`, `bored` are load-bearing for OBS until a Live2D embodiment abstraction replaces them (per `AGENTS.md` hard rule).
9. **No fabricated results**: Every implementation claim must have matching execution evidence (tests passing, endpoint accessible, file present, git diff verified). If a capability is mentioned only in specs, label it PROPOSED or DEFERRED.
10. **Verification before claim**: Before any design section claims an architecture change is implemented, confirm with `git diff`, `python -m unittest`, `read_file`, or `terminal()` inspection.

---

## 4. V1 Complete Definition (PROPOSED — observable criteria)

V1 is achieved when the repository supports the following observable behaviors (not aesthetic perfection):

A. **System presence**: SHURA is present as a visible agent in a workspace environment. The user sees SHURA (current embodiment: PNG/sprite-based, future: Live2D or 3D model). SHURA's presence is not decorative; it reflects current state (idle, working, thinking, dreaming, error, attention, success).
B. **Workspace navigation**: The user can navigate between core surfaces: Overview, Workspace/Work, Memory/Context, Dream Studio, Agents, Skills, MCP/Tools, Artifacts, Activity/Event stream. Navigation is persistent and does not lose context.
C. **Live SHURA state**: The interface shows current system status (mode, model/provider reference — though identity remains provider-independent, the current provider choice is operational state), active skills, active agents/sub-agents, memory awareness, current project/session reference, current task/state.
D. **Event observation**: The user can observe structured events (`dream.started`, `reconciliation_started`, `reconciliation_completed`, `memory.proposal`, etc.) through a live feed or audit surface, backed by the durable `events.jsonl` journal and replay mechanism.
E. **Task visibility**: The user can see what tasks are queued, running, blocked, completed. Tasks are linked to agents/sub-agents. Tasks can be inspected, paused, resumed, and completed.
F. **Dream Studio**: The user can observe Dream Engine state through `/dream/projection` (read-only observation) and trigger Dream runs through `/dream/run` (explicit mutation). Dream events (`dream.started`, `snapshot_created`, `reconciliation_started`, `reconciliation_completed`, `completed`, `failed`) are visible. Dream snapshot fields (`source_memory_ids`, `active_concepts`, `unresolved_threads`, `contradictions`, `metrics`) are observable.
G. **Agent/sub-agent visibility**: Agents are not hidden inside brain internals. The user can observe agent assignments, executions, tool calls, results, failures, approvals, and completions.
H. **Memory visibility**: Memory observations (`DreamSnapshot` fields, event replay results) are visible. The user can inspect source memory IDs, active concepts, unresolved threads, contradictions, and metrics. Durable mutation is routed through reconciliation/commit (not direct from UI).
I. **MCP/tool visibility**: The user can inspect configured MCP servers (`majniks-studio`, `hugging_face`, `amplitude`), discover available tools, observe tool execution events, and see results/status.
J. **Harness continuity**: The autonomous development loop works across harness contexts. `AGENTS.md` is updated. `docs/operations/LOOP_STATE.md` and `docs/operations/SESSION_HANDOFF.md` are maintained. The system can read these before acting.
K. **Autonomous operation**: SHURA can perform bounded autonomous work: load context, inspect repo state, read `docs/vision/` and `docs/tasks/`, identify ready tasks from `V1_TASK_GRAPH.md`, implement a bounded task (e.g., add a projection endpoint, add a test, update documentation), verify with `python -m unittest`, review diff, update `docs/operations/LOOP_STATE.md`, select next ready task. It stops at defined safety boundaries.
L. **Portability preserved**: The architecture does not couple identity to a single provider (verified: `omniroute_llm.py`, `openai_compat.py`, `groq_llm.py`, `openrouter_llm.py` exist; identity layer `data/prompts/soul.md` has no provider references). The architecture does not couple cognition to avatar PNG files (verified: `brain.py` uses `load_avatar_resources` but identity layer is separate from `png_map` references).
M. **No fabricated implementation**: Every feature present is backed by passing tests (`tests/test_dream_engine.py`, `tests/test_events.py`, `tests/test_memory_consolidation.py`, `tests/test_dream_projection.py`) or accessible endpoints (`/dream/projection`, `/dream/run`, `/events`, etc.) or verified file structures (`docs/design/`, `docs/operations/`, `docs/tasks/`). Features described only in specifications (`DreamSubstrate`, `scene.py`, full memory consolidation pipeline, full workspace shell with all surfaces) are explicitly labeled PROPOSED.

---

## 5. Design Philosophy for V1

The objective is a durable, coherent, observable, autonomous-capable system — not a polished product.

The user should be able to leave SHURA alone, and the system should continue meaningful bounded work (read specs, inspect state, select next ready task from the task graph, implement/test/update state) without making dangerous changes.

The user should be able to return and observe exactly:
- What phase we are in.
- What milestone.
- What task was completed.
- What tests passed.
- What changed.
- What decisions were made.
- What is ready next.
- What is blocked (e.g., C4 mechanism, Live Majik MCP, full Live2D embodiment).

The design documents themselves are part of the operating system. They must be kept current. They must distinguish VERIFIED from PROPOSED. They must reference the actual files that exist.

This design document is part of that operating system. It is not a decorative planning artifact. It must remain accurate.
