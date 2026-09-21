# Command Center V1 Design — SHURA Workspace / Cockpit

Status: Design document — framework established; full workspace shell deferred to future milestone; projection endpoint (`/dream/projection`) and design architecture verified.

Based on verified references (`docs/SHURA_COMMAND_CENTER_SPEC.md`, `docs/DREAM_ENGINE.md`, `docs/EVENT_CONTRACT.md`, `docs/ARCHITECTURE_MAP.md`, `docs/design/SHURA_EMBODIMENT.md`, `docs/reference/OPENHUMAN_REFERENCE.md`) and verified current implementation (`src/web/app.py`, `frontend/`, `brain.py`, `events.py`, `projection.py`).

---

## Design Intent (PROPOSED — must guide all future workspace implementation)

The Command Center is the workspace in which Viollett and SHURA work together. It is not a chat-only interface. It must feel like a studio / cockpit / command environment — not a generic SaaS dashboard.

This design defines the V1 framework (layout, surfaces, data sources, interaction patterns) without requiring full implementation of every workspace surface. The framework must be durable: future workspace expansions (Memory surfaces, Agents workspace, Dream Studio full surface, Project workspace) must fit into this framework without restructuring.

---

## Workspace Framework Structure (VERIFIED design framework; PROPOSED full implementation)

Verified framework elements (design docs and endpoint exist; workspace skeleton designed but not fully implemented):
- Design docs: `docs/design/THREE_SYSTEMS.md`, `docs/design/ARCHITECTURE_MAP.md`, `docs/design/COMMAND_CENTER_V1.md` (this file), `docs/vision/SHURA_V1_VISION.md`, `docs/design/SHURA_EMBODIMENT.md`
- Web endpoint: `/dream/projection` (read-only projection interface — verified by `tests/test_dream_projection.py` and `src/web/app.py`)
- Event observation mechanism: `EventManager.subscribe()` / replay (`docs/EVENT_CONTRACT.md`, verified by `tests/test_events.py`)
- Workspace framework: Navigation surfaces (Overview, Workspace, Memory, Dream Studio, Agents, Skills, MCP, Artifacts, Activity, System) — designed; full surface components deferred.

### Application Shell Layout (PROPOSED — framework only; components may be partially implemented in future milestones)

Based on `docs/SHURA_COMMAND_CENTER_SPEC.md` and `docs/reference/OPENHUMAN_REFERENCE.md` workspace model (OpenHuman workspace surfaces: Home, Conversations, Brain, Channels, Flows, Skills, Settings; adapted to SHURA architecture):

```
┌───────────────────────────────────────────────────────────────────────┐
│ GLOBAL HEADER (system status / identity-independent status)         │
│ SHURA // current phase // active task // model reference (operational)  │
├─────────────┬──────────────────────────────┬───────────────────────────┤
│             │                              │                           │
│ NAVIGATION  │     MAIN WORKSPACE           │    LIVE STATE / CONTEXT  │
│ (persistent)│    (primary collaboration)   │    (observable, not hidden)│
│             │                              │                           │
│ Overview    │ Dynamic workspace surface:   │ SHURA embodiment stage    │
│ Workspace   │ - active project/session     │ (current PNG; future      │
│ Memory      │ - open artifacts/tasks        │  Live2D/3D — design contract│
│ Dream Studio│ - agent/task visibility      │  in SHURA_EMBODIMENT.md)  │
│ Agents      │ - workspace interaction       │                           │
│ Skills      │                              │ Active agents / skills    │
│ MCP / Tools │                              │ Current event feed        │
│ Artifacts   │                              │ System health / metrics    │
│ Activity    │                              │ Notifications / approvals  │
│ Settings    │                              │                           │
├─────────────┴──────────────────────────────┴───────────────────────────┤
│ GLOBAL EVENT / ACTIVITY RAIL (durable replay + live events)             │
└───────────────────────────────────────────────────────────────────────┘
```

This layout is a framework design. The components within each region (workspace surface, embodiment stage, event feed, navigation) are defined in this document but implemented incrementally (`docs/tasks/V1_TASK_GRAPH.md`).

### Navigation Surfaces (PROPOSED framework; not all fully implemented)

For V1 framework, the navigation surfaces must exist as durable framework elements (even if some surfaces show placeholder or minimal content). The framework must allow future surfaces without restructuring navigation:

1. **Overview**: System state summary (current loop phase from `docs/operations/LOOP_STATE.md`, active milestone from roadmap, recent completed tasks, active agents, Dream state indicator, health/status). Must observe through projection and event replay (`/events` endpoint, `EventManager.get_events()`), not direct brain internals.
2. **Workspace**: Primary collaboration surface. Shows current project/session reference, open tasks/agents, workspace interaction (command input, task creation/invocation). Must observe through projection (`/dream/projection`) and event subscription; mutation through explicit commands (`/dream/run` for Dream; future task/service endpoints for agent/task mutation — not arbitrary brain mutation).
3. **Memory**: Memory observations from `DreamSnapshot` fields (`source_memory_ids`, `active_concepts`, `unresolved_threads`, `contradictions`, `metrics`) and event replay (`replayed_event_ids`, `replayed_lifecycle_events`). Not full Memory workspace (that requires full consolidation pipeline integration — deferred). For V1 framework: read-only observation through `/dream/projection` endpoint; future Memory surfaces expand from this framework.
4. **Dream Studio**: Dream state observation (`DreamStateProjection` fields) + event feed (Dream lifecycle events: `dream.started`, `snapshot_created`, `reconciliation_started`, `reconciliation_completed`, `completed`, `failed`). Not full Dream Studio with scene generation (`DreamSubstrate` deferred) or streaming event output (deferred). For V1 framework: observation + replay only.
5. **Agents**: Agent/task visibility framework. Shows assigned agents, queued/running/blocked/completed tasks, sub-agent references (if applicable). Not full autonomous agent execution framework (autonomous loop protocol in `docs/operations/AUTONOMOUS_LOOP.md` defines execution; workspace shows observation). For V1 framework: observation framework established; full agent/task execution framework deferred.
6. **Skills**: Skill registry observation (`/skills` endpoint: enabled, active, config reference) + invocation framework. Must observe `SkillRegistry`; must not directly access brain skill internals for mutation (mutation through `/skills/{name}/toggle` endpoint, not arbitrary brain access).
7. **MCP / Tools**: MCP server/tool visibility framework. Shows configured servers (`.hermes/config.yaml`: `majniks-studio`, `hugging_face`, `amplitude`), discovered tools, tool execution events (`EventCategory.TOOL`), results/status. Must observe through event replay/subscription; mutation through application interfaces, not direct server mutation from UI.
8. **Artifacts**: Artifact/workspace file visibility framework. References workspace/project artifacts; not a full file manager. Must observe workspace/project state; future artifact surfaces expand from framework.
9. **Activity**: Event feed / audit framework. Durable replay (`EventJournal.read_all()` + replay filters) + live event feed (`EventManager.subscribe()` results). Must show structured events (`event_type`, `subsystem`, `run_id`, `payload`, `severity`, `visibility`) — not arbitrary message parsing. Must preserve replay semantics (original event IDs preserved; no new IDs created; sequence preserved — verified by `tests/test_events.py`).
10. **System**: System health/config/status framework. References `BrainConfig` (`/config` endpoint), health (`/health` endpoint), status (`/status` endpoint — `is_speaking`, `is_sleeping`, `active_skills`). Must observe through endpoints/projection; mutation through `/config` endpoint (explicit command), not arbitrary brain access.

### Workspace Interaction Pattern (PROPOSED — framework for workspace behavior)

The workspace must support the following interaction patterns (design framework; specific component implementations deferred to milestone-based implementation):

- **Selection**: Navigation selection changes visible workspace surface without losing context (persistent workspace state — not brain/consciousness mutation).
- **Task visibility**: Active task visible in workspace; recent completed tasks visible in workspace or Activity rail; queued tasks visible (derived from `docs/operations/LOOP_STATE.md` + future task registry — framework only for V1).
- **Agent observation**: Active agent visible (if agent framework implemented); agent execution events visible in Activity rail; agent results/status visible in workspace or agent surface.
- **Event subscription**: Live event feed observable in workspace or dedicated Activity surface; durable replay accessible through event replay mechanism (`replay(run_id=..., subsystem=...)`); replay does not create new event IDs (verified by `tests/test_events.py` `test_replay_does_not_create_new_ids`).
- **Command input**: Workspace interaction through command input (future command palette or direct workspace command input). Must route mutation through explicit application interfaces (`/dream/run`, future task/service endpoints, `/skills/{name}/toggle`) — not arbitrary brain mutation.
- **Workspace persistence**: Workspace/project/session reference must persist across workspace navigation (framework design; implementation deferred — future database/file-based workspace state mechanism must be added without restructuring workspace framework).
- **Empty / loading / error states**: Every workspace surface must define empty state (no active task / no events / no agent / no memory observations), loading state (workspace initializing / event replay loading / agent starting), and error state (event replay failure — handled safely by projection; agent failure — visible through event feed; system error — visible through health/status endpoint + event emission). These states are framework design elements; specific UI components deferred.

---

## SHURA Embodiment Integration (VERIFIED framework + PROPOSED presentation upgrade path)

Based on `docs/design/SHURA_EMBODIMENT.md` (verified design file):

The workspace framework must include a central SHURA embodiment stage (`docs/design/SHURA_EMBODIMENT.md` — framework design verified; full Live2D/3D implementation deferred). The framework must observe the presentation-state contract:

- `current_pose`: idle | talking | thinking | working | dreaming | error | attention | success | interrupted | resumed (derived from `DreamStateProjection` fields + brain/consciousness state + event replay — not arbitrary brain internals).
- `current_text`: message being spoken (derived from `Expression.set_text()` / `type_text()` — existing mechanism verified by `expression.py` inspection; future workspace must observe through stable interface, not direct brain access).
- `current_state_indicator`: active | sleeping | interrupted | resumed (derived from brain/consciousness state + event replay; observable through projection; not identity).
- `avatar_reference`: PNG/sprite reference (current `avatar_map`); future Live2D/3D reference (deferred; framework must allow reference change without restructuring workspace framework).

The workspace framework must display the SHURA embodiment stage in a consistent position (global header or dedicated workspace region — framework design allows either; specific placement deferred to workspace component implementation). The framework must not couple cognition directly to rendering (verified by architecture rules and projection layer design: brain/consciousness produces events; projection reads events; embodiment adapter translates projection to visual states; no direct brain → avatar mutation).

---

## Framework Verification Criteria (VERIFIED framework + PROPOSED full implementation criteria)

The workspace framework (navigation structure, workspace model, data sources, interaction patterns, presentation-state mapping) must be verified by:
- Design document presence (`docs/design/COMMAND_CENTER_V1.md` — this file — verified; framework elements described).
- Endpoint framework verified (`/dream/projection` read-only verified by `tests/test_dream_projection.py`; `/events` replay/subscription mechanism verified by `tests/test_events.py`; `/status` health verified by endpoint access).
- Workspace framework design does not violate verified architecture rules (`docs/design/ARCHITECTURE_MAP.md` — integration relationships verified; `docs/design/THREE_SYSTEMS.md` — system boundaries verified; `docs/design/FORK_STRATEGY.md` — reference/reimplementation decision verified).
- Future workspace components must fit framework without restructuring navigation or workspace model (design framework allows this; full component set deferred; framework durability verified by framework design, not by full component presence).

Full workspace surface implementations (Memory workspace, Agents workspace, Dream Studio full surface, Project workspace, Artifact workspace, full workspace persistence mechanism) are deferred to milestone-based implementation (`docs/tasks/V1_TASK_GRAPH.md` and `docs/tasks/V1_ROADMAP.md`). The framework must remain durable through these future expansions.
