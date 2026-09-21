# V1 Roadmap — Milestones and Exit Criteria (PROPOSED — durable operating document)

Status: Planning framework — must guide milestone-based work; must be updated by autonomous loop (`docs/operations/AUTONOMOUS_LOOP.md`) and session handoff (`docs/operations/SESSION_HANDOFF.md`).

Verified current foundation (before V1):
- Dream Engine Phase 2 verified (`docs/DREAM_ENGINE.md`; `tests/test_dream_engine.py` 15 passing).
- Event Foundation verified (`docs/EVENT_CONTRACT.md`; `tests/test_events.py` 22 passing).
- Memory consolidation framework (`docs/MEMORY_CONSOLIDATION.md`; `tests/test_memory_consolidation.py` present).
- Projection layer added and verified (`tests/test_dream_projection.py` 11 passing; `docs/design/SHURA_EMBODIMENT.md`; `docs/design/ARCHITECTURE_MAP.md`).
- Design framework established (`docs/design/THREE_SYSTEMS.md`, `docs/design/SHURA_V1_VISION.md`, `docs/reference/OPENHUMAN_REFERENCE.md`, `docs/reference/OPENHUMAN_TO_FORGE.md`, `docs/reference/FORK_STRATEGY.md`).
- Workspace framework designed (`docs/design/COMMAND_CENTER_V1.md`, `docs/design/VISUAL_SYSTEM.md`).
- Autonomous loop protocol designed (`docs/operations/AUTONOMOUS_LOOP.md`).
- Loop state template (`docs/operations/LOOP_STATE.md`).
- Session handoff template (`docs/operations/SESSION_HANDOFF.md`).
- Harness interoperability protocol (`docs/operations/HARNESS_INTEROPERABILITY.md`).
- Visual design system (`docs/design/VISUAL_SYSTEM.md`).

---

## Milestone Sequence (PROPOSED — derived from current verified state + design specs + architecture audit; must be refined by autonomous loop when milestones complete)

### Milestone 0: Current Foundation Verified (VERIFIED — completed before this design pass)
- Dream Engine Phase 2 (`DreamRun`, `DreamSnapshot`, event taxonomy, non-destructive emission, projection layer boundary) — verified by 48 passing tests.
- Event Foundation (`EventCategory`, `BrainEvent`, `EventManager` with subscribe/replay/publish, JSONL journal) — verified by tests.
- Memory framework (`MemoryConsolidationTransaction`, `MemoryProposal`, `ConsolidationEngine`) — framework present.
- Design framework (`docs/design/` structure, `docs/vision/SHURA_V1_VISION.md`, `docs/reference/`) — verified by file presence.
- Projection layer (`projection.py`, `/dream/projection` endpoint) — verified by new tests.
- Exit criteria: Dream boundary preserved; event contract preserved; identity preserved; all targeted tests passing; design framework present; autonomous loop protocol designed.

### Milestone 1: Durable Autonomous Operating System (PROPOSED — M1-T8 verified; autonomous loop framework established; loop state and session handoff updated by autonomous session)
- `AGENTS.md` updated with autonomous loop rules, architecture rules, verification rules, boundary rules, harness handoff rules, identity preservation rules, design framework references (`docs/vision/SHURA_V1_VISION.md`, `docs/design/THREE_SYSTEMS.md`, `docs/design/ARCHITECTURE_MAP.md`, `docs/operations/AUTONOMOUS_LOOP.md`, `docs/operations/LOOP_STATE.md`, `docs/operations/SESSION_HANDOFF.md`).
- `docs/operations/AUTONOMOUS_LOOP.md` verified (present; framework complete; must be executed by future autonomous session to become durable).
- `docs/operations/LOOP_STATE.md` initialized (present; must be updated by autonomous session).
- `docs/operations/SESSION_HANDOFF.md` initialized (present; must be updated by autonomous session).
- `docs/tasks/V1_TASK_GRAPH.md` initialized (task graph framework with V1 milestone tasks; must be refined with dependency relationships; must be updated as tasks complete).
- `docs/tasks/V1_ROADMAP.md` initialized (milestone-based roadmap; must be refined with specific milestone exit criteria; must reference `docs/tasks/V1_TASK_GRAPH.md`).
- `docs/reference/ADR_INDEX.md` initialized (architecture decision records; must reference design decisions made during V1; first entry must reference OpenHuman reference/reimplementation decision — `docs/reference/FORK_STRATEGY.md`).
- `docs/reference/OPEN_QUESTIONS.md` initialized (must reference C4 mechanism as BLOCKED; identity sync if changed; Live2D/3D embodiment upgrade; full workspace implementation; full ATLAS operational layer; full Dream Transaction pipeline; full autonomous loop execution testing).
- `docs/reference/V1_ACCEPTANCE.md` initialized (observable acceptance criteria — must reference design framework; must include verification criteria for identity preservation, Dream boundary, projection read-only behavior, event contract preservation, workspace framework presence, autonomous loop protocol presence, session handoff presence, harness interoperability protocol presence, design framework completeness).
- Exit criteria: AGENTS.md durable; loop protocol designed; loop state initialized; session handoff initialized; task graph framework initialized; roadmap framework initialized; ADR index initialized; open questions reference initialized; acceptance criteria framework initialized; no identity divergence; no secret exposure; no C4 retry; no Dream boundary collapse; no event contract collapse; workspace framework present (design framework verified); autonomous loop can read context and select next bounded task safely.

### Milestone 2: Workspace Framework Implementation (PROPOSED — framework verified; components deferred)
- Workspace framework (`docs/design/COMMAND_CENTER_V1.md`) must become durable through component implementation (not full workspace shell; bounded workspace component additions per milestone).
- Navigation surfaces framework (`Overview`, `Workspace`, `Memory`, `Dream Studio`, `Agents`, `Skills`, `MCP`, `Artifacts`, `Activity`, `System`) must exist as durable framework (navigation structure verified; individual surface components implemented incrementally per `docs/tasks/V1_TASK_GRAPH.md`).
- SHURA embodiment stage framework (`docs/design/SHURA_EMBODIMENT.md`) must exist (design verified; presentation-state contract verified; current PNG/sprite preserved; future Live2D/3D upgrade path preserved; workspace framework references embodiment stage).
- Workspace data sources (`docs/design/ARCHITECTURE_MAP.md`) must observe ProjectSHURA through projection/event interfaces (verified framework; must be preserved through component implementation).
- Workspace interaction framework must route mutation through explicit interfaces (`/dream/run` for Dream mutation; future service/task endpoints for agent/task mutation; `/skills/{name}/toggle` for skill mutation; `/config` for config mutation) — must never create arbitrary brain mutation through workspace interaction.
- Workspace persistence mechanism (file-based workspace/project/session reference + workspace state persistence) must exist (framework designed; mechanism deferred but framework must allow mechanism addition without restructuring workspace framework).
- Exit criteria: Workspace framework durable; navigation framework present; workspace surfaces framework present (at least Overview + Workspace + Memory + Dream Studio + Activity framework surfaces; future surfaces deferred); embodiment stage framework present and observing presentation-state contract; workspace interaction framework routes mutation through explicit interfaces; workspace persistence framework present; design framework references all workspace components; tests pass for workspace framework components (`tests/test_...` must cover workspace framework behaviors — framework only; full component set deferred).

### Milestone 3: Dream Studio Full Surface (PROPOSED — framework verified; components deferred)
- Dream Studio workspace surface must observe Dream state through projection (`DreamStateProjection` + event replay; verified framework; must be preserved through full surface implementation).
- Dream Studio must include Dream lifecycle observation (event replay for `dream.started`, `snapshot_created`, `reconciliation_started`, `reconciliation_completed`, `completed`, `failed` — event taxonomy verified; replay mechanism verified).
- Dream Studio must include Dream snapshot observation (`DreamSnapshot` fields: `source_memory_ids`, `active_concepts`, `unresolved_threads`, `contradictions`, `metrics`) — projection interface verified (`tests/test_dream_projection.py`).
- Dream Studio must include Dream transaction/reconciliation observation (`MemoryConsolidationTransaction` status; `MemoryProposal`; `RehearsalResult`; `ValidationResult` — framework verified; full pipeline observation deferred).
- Dream Studio must include event replay mechanism (`EventJournal.read_all()` + replay filters) — verified by `tests/test_events.py` (`test_replay_does_not_create_new_ids`, `test_replay_preserves_hierarchy`, `test_round_trip_jsonl`).
- Dream Studio must include Dream event taxonomy (`docs/DREAM_ENGINE.md`, `docs/EVENT_CONTRACT.md` — verified framework).
- Dream Studio must include Dream Studio framework design (`docs/design/COMMAND_CENTER_V1.md` — framework includes Dream Studio; full Dream Studio surface components deferred but framework must allow future expansion: scene generation, streaming event output, Dream Substrate observation, visual scene representation, symbolic/narrative dream representation).
- Exit criteria: Dream Studio framework durable; Dream observation through projection/event replay verified; event replay mechanism verified; Dream event taxonomy verified; Dream framework design allows future scene/substrate/streaming expansion without restructuring workspace framework.

### Milestone 4: Memory / Context Integration (PROPOSED — framework verified; full integration deferred)
- Memory observations through `DreamSnapshot` (`projection.py` verified; framework established).
- Memory consolidation framework (`docs/MEMORY_CONSOLIDATION.md`; `transaction.py`, `consolidation.py` — framework verified; full pipeline deferred).
- ATLAS durable context (`docs/design/THREE_SYSTEMS.md` — ATLAS framework verified; operational layer deferred; framework allows future index/retrieval service addition).
- Memory workspace framework (`docs/design/COMMAND_CENTER_V1.md` — Memory surface framework verified; full Memory workspace components deferred: timeline, graph, tree, semantic clusters, memory diff, health inspection, procedure memory, relational memory).
- Memory observation framework must use projection/event interfaces (verified framework; must be preserved through Memory workspace implementation).
- Memory mutation framework (`MemorySkill` interfaces — `docs/SHURA_MASTER_HANDOFF.md`, `docs/MIGRATION_AUDIT_20260913.md`) must route mutation through `MemoryStorage` / reconciliation framework (verified framework; must not allow direct memory mutation through workspace interface).
- Exit criteria: Memory framework durable; ATLAS framework durable; Memory workspace framework present (at least Memory surface framework; full Memory workspace deferred); memory mutation framework routes through `MemorySkill`; projection/event interfaces preserved.

### Milestone 5: Agents / Tasks / MCP Integration (PROPOSED — framework verified; full agent execution framework deferred)
- Agent/task framework (`docs/design/ARCHITECTURE_MAP.md` — agent/task framework verified; full framework deferred to future milestone).
- Agent/task observation framework (`docs/operations/AUTONOMOUS_LOOP.md` — loop protocol verified; `docs/tasks/V1_TASK_GRAPH.md` — framework verified; `docs/operations/LOOP_STATE.md` — loop state framework verified).
- Agent/task visibility framework (`docs/design/COMMAND_CENTER_V1.md` — Agents workspace framework verified; full agent workspace components deferred: agent assignment, sub-agent representation, agent execution observation, agent approval framework, agent failure/retry framework).
- Agent/task execution framework (future — must observe `ProjectSHURA` brain/consciousness through event/projection interfaces; must not create arbitrary brain mutation; must route mutation through service/application interfaces; autonomous loop defines execution protocol but full autonomous execution framework deferred to future milestone).
- MCP framework (`docs/HERMES_COMMAND_CENTER_STATUS.md` — MCP discovery verified: `majniks-studio` 148 tools verified; `hugging_face`, `amplitude` configured; `.hermes/config.yaml` preserved). MCP workspace framework (`docs/design/COMMAND_CENTER_V1.md` — MCP surface framework verified; full MCP workspace components deferred: server/tool inventory, tool execution framework, tool permission framework, tool event observation framework).
- Tool framework (`docs/EVENT_CONTRACT.md` — `EventCategory.TOOL`; `Agent` / `LLMClient` / `ToolRegistry` — framework verified; full tool execution framework deferred).
- Exit criteria: Agent/task framework durable; autonomous loop framework durable; task graph framework durable; agent/task observation framework present; MCP framework durable; tool framework durable; event/projection interfaces preserved; no forbidden coupling introduced.

### Milestone 6: Embodiment / Workspace Polish (PROPOSED — framework verified; full embodiment upgrade deferred)
- Embodiment framework (`docs/design/SHURA_EMBODIMENT.md` — framework verified; presentation-state contract verified; future Live2D/3D upgrade path preserved; current PNG/sprite preserved).
- Workspace framework durability (`docs/design/COMMAND_CENTER_V1.md` — framework verified; workspace framework must allow future workspace surface expansions without restructuring).
- Workspace persistence mechanism (`docs/design/COMMAND_CENTER_V1.md` — framework verified; mechanism deferred; framework allows mechanism addition without restructuring workspace framework).
- Workspace visual design (`docs/design/VISUAL_SYSTEM.md` — framework verified; color tokens, typography roles, spacing/layout framework, animation rules verified; full component visual design deferred but must follow framework).
- Workspace accessibility/readability framework (`docs/design/VISUAL_SYSTEM.md` — framework verified; must be preserved through component implementation).
- Workspace interaction framework (`docs/design/COMMAND_CENTER_V1.md` — framework verified; must preserve event/projection interfaces; must not create arbitrary brain mutation through workspace interaction).
- Workspace framework must allow future workspace surfaces (`Memory` full surface, `Agents` full surface, `Dream Studio` full surface, `Projects`, `Artifacts`, `Settings` full surface) without restructuring navigation or workspace model.
- Exit criteria: Embodiment framework durable; workspace framework durable; workspace persistence framework present; visual design framework present; accessibility/readability framework preserved; workspace framework allows future expansions; no boundary collapse.

### Milestone 7: V1 Prototype Validation (PROPOSED — must be verified before claiming V1 complete)
- V1 vision criteria verified (`docs/vision/SHURA_V1_VISION.md` — criteria A-M verified or proposed; criteria verified by file presence, endpoint access, test results, projection boundary verification, identity preservation verification, event contract preservation verification, workspace framework presence verification, autonomous loop framework presence verification).
- Workspace framework present (`docs/design/COMMAND_CENTER_V1.md` — framework verified; components deferred but framework durable).
- Workspace surfaces framework present (Overview + Workspace + Memory framework + Dream Studio framework + Agents framework + Skills framework + MCP framework + Artifacts framework + Activity framework + System framework — framework verified; full surface implementations deferred to milestone-based work).
- Embodiment stage framework present (`docs/design/SHURA_EMBODIMENT.md` — framework verified; presentation-state contract verified; workspace framework references embodiment stage).
- Autonomous loop framework present (`docs/operations/AUTONOMOUS_LOOP.md` — framework verified; must be executed by autonomous session to become durable; loop state updated; session handoff updated).
- Harness interoperability framework present (`docs/operations/HARNESS_INTEROPERABILITY.md` — framework verified; must be tested by future multi-harness session).
- Design framework durable (`docs/design/` complete; `docs/vision/` complete; `docs/reference/` complete; `docs/operations/` complete; `docs/tasks/` framework complete; `docs/tasks/V1_TASK_GRAPH.md` and `docs/tasks/V1_ROADMAP.md` initialized; must be updated as work progresses).
- No identity divergence (verified); no secret exposure (verified); no Dream boundary collapse (verified); no event contract collapse (verified); no forbidden coupling (verified); projection layer preserved (verified); workspace framework preserves core/UI separation (verified by framework design and `docs/design/ARCHITECTURE_MAP.md`).
- All bounded tasks in `docs/tasks/V1_TASK_GRAPH.md` must have verification criteria (tests, endpoint inspection, file inspection, boundary verification). All milestone tasks must reference `docs/tasks/V1_ROADMAP.md` exit criteria.
- Exit criteria: V1 framework durable; workspace surfaces framework durable; embodiment framework durable; autonomous loop framework durable; harness interoperability framework durable; design framework durable; no architecture ambiguity unaddressed (any ambiguity must become an ADR entry in `docs/reference/ADR_INDEX.md` or open question in `docs/reference/OPEN_QUESTIONS.md`); user can observe workspace framework (navigation surfaces exist; workspace framework observable through workspace components — full components deferred but framework must be observable); autonomous loop can read context (`docs/operations/LOOP_STATE.md`, `docs/tasks/V1_TASK_GRAPH.md`, design framework), select bounded ready task, implement/test/update state, and stop safely.
---

## Milestone Dependency Order (PROPOSED — must be preserved; updates through autonomous loop)

Verified current milestone (completed in previous turns + this design pass): Milestone 0 (Foundation Verified + Design Framework Established).

Proposed milestone sequence (derived from verified current state, design specs, architecture requirements, reference analysis, autonomous loop protocol):

```
Milestone 0 → Milestone 1 → Milestone 2 → Milestone 3 → Milestone 4 → Milestone 5 → Milestone 6 → Milestone 7
  (verified)    (loop/ops)   (workspace    (Dream      (Memory/    (Agents/    (Embodi-    (V1
                  framework)  framework)    Studio)    ATLAS)      MCP)        ment)        Valid)
```

Milestone dependencies (must be preserved — autonomous loop must confirm dependency satisfaction before selecting next milestone task):
- Milestone 1 depends on Milestone 0 (loop framework requires verified Dream/event/domain boundaries; workspace framework must observe stable projection interface).
- Milestone 2 depends on Milestone 0 + Milestone 1 (workspace framework must observe loop state and task graph; workspace framework requires autonomous loop framework for task observation; workspace framework must observe Dream projection interface).
- Milestone 3 depends on Milestone 0 + Milestone 2 (Dream Studio framework must observe Dream projection interface; Dream Studio framework requires workspace framework for workspace surface framework; Dream Studio framework requires loop framework for event/task/state observation).
- Milestone 4 depends on Milestone 0 + Milestone 3 (Memory framework must observe Dream projection interface and event replay; Memory framework requires workspace framework for workspace observation framework; Memory framework requires loop framework for session/task/state observation; Memory framework requires Dream framework for memory consolidation framework observation).
- Milestone 5 depends on Milestone 0 + Milestone 4 (Agent/task framework requires workspace framework for agent/task observation framework; Agent/task framework requires loop framework for autonomous task selection; Agent/task framework requires event/projection framework for agent execution observation; Agent/task framework requires memory framework for agent context/memory observation).
- Milestone 6 depends on Milestone 0 + Milestone 5 (Embodiment framework requires workspace framework for workspace framework durability; Embodiment framework requires agent/task framework for agent/task state mapping; Embodiment framework requires loop framework for loop phase/state mapping; Embodiment framework requires Dream framework for Dream state mapping; Embodiment framework requires memory framework for memory/state mapping).
- Milestone 7 depends on all previous milestones (V1 validation requires all framework elements durable; V1 validation requires workspace surfaces framework observable; V1 validation requires autonomous loop executed at least once; V1 validation requires harness interoperability tested; V1 validation requires design framework durable; V1 validation requires identity preserved; V1 validation requires Dream/event/projection boundaries preserved).

---

## Roadmap Updates (VERIFIED — current roadmap framework; must be updated by autonomous loop when milestones complete)

The current roadmap framework (`docs/tasks/V1_ROADMAP.md` — must be initialized/updated by autonomous loop; must reference milestone exit criteria and dependency relationships) must include:
- Milestone definitions (verified/proposed framework; must reference verified milestone 0; must reference proposed milestones 1-7).
- Milestone exit criteria (observed/testable criteria; must reference `docs/tasks/V1_TASK_GRAPH.md` tasks for each milestone; must include verification criteria: identity preserved, Dream/event/projection boundaries preserved, workspace framework durable, autonomous loop framework durable, harness interoperability framework durable, design framework durable).
- Milestone dependency relationships (must match roadmap dependency order above; must be preserved; must be verified by autonomous loop when selecting tasks).
- Milestone status updates (verified by autonomous loop; loop state updates must reference milestone progress; milestone progress must be observable through design framework, workspace framework, autonomous loop framework).

The autonomous loop must update milestone status when bounded milestone tasks complete (verified through task graph updates). The loop must not claim milestone complete until milestone exit criteria satisfied (verified by framework presence + test results + boundary verification + design framework verification + workspace framework verification + autonomous loop execution verification).
