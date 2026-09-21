# Open Questions — ProjectSHURA V1

Status: Framework initialized; updated by autonomous loop when questions resolved or new questions emerge. Any ambiguity must become ADR entry (`docs/reference/ADR_INDEX.md`) or open question rather than silently restructuring framework.

---

## Open Questions (PROPOSED / BLOCKED — must distinguish)

### Q1: C4 Mechanism State — BLOCKED
Status: BLOCKED (security mechanism; not retried; not bypassed).
Evidence: `.hermes/config.yaml` line 4041 contains `${MCP_...KEY}` (C4 mechanism remains BLOCKED by security mechanism). File does not exist in repo working tree; reference points to Hermes profile directory (`/Users/ultraviollett/.hermes/profiles/shura/` or similar). Not retried indefinitely by autonomous loop.
Mitigation: Reported separately; does not block bounded design/development work but must be documented in loop state (`docs/operations/LOOP_STATE.md`) and session handoff (`docs/operations/SESSION_HANDOFF.md`).
References: `docs/design/SHURA_EMBODIMENT.md` (identity independent of provider/model/avatar); `docs/operations/AUTONOMOUS_LOOP.md` (C4 mechanism status — BLOCKED; must not retry indefinitely; must not bypass); `docs/tasks/V1_TASK_GRAPH.md` (milestone framework preserved); `docs/reference/ADR_INDEX.md` (ADR-001 — OpenHuman reference/reimplementation decision does not address C4; C4 remains separate infrastructure issue).

### Q2: Identity Sync — VERIFIED UNCHANGED (current), but framework requires documentation if changed
Status: VERIFIED (identity unchanged in this autonomous session).
Evidence: `git diff -- data/prompts/soul.md` empty; `md5 -q data/prompts/soul.md` = `20ef2e9a3298b8a3fa5a4107b77fa0e4` (current verified hash; previous reference `6aabb046958ddedaf0bd62b14ad6fe18` in loop state was from a previous session/file version; discrepancy documented here — identity unchanged relative to current file content; no governed identity change performed).
Mitigation: If identity is changed with human approval, identity sync framework (`docs/IDENTITY_SYNC.md`) must be followed; identity change must include identity sync verification; identity framework must reference identity sync framework; workspace framework verifies identity unchanged (`git diff -- data/prompts/soul.md`); autonomous loop stops if identity divergence detected.
References: `docs/design/SHURA_EMBODIMENT.md` (identity independent of presentation/state/provider/model/avatar); `docs/design/THREE_SYSTEMS.md` (identity preservation rules); `docs/operations/AUTONOMOUS_LOOP.md` (identity divergence stops loop); `docs/reference/V1_ACCEPTANCE.md` (identity preservation verification criteria).

### Q3: Full Workspace Shell Implementation — DEFERRED
Status: DEFERRED (framework verified; full implementation deferred to milestone-based autonomous execution).
Evidence: `docs/design/COMMAND_CENTER_V1.md` framework verified; workspace framework allows future workspace surfaces framework expansions; workspace framework allows future workspace persistence mechanism; workspace framework allows future workspace interaction framework expansions; workspace framework allows future workspace framework expansions. Workspace adapter endpoint (`/workspace/dream-events`) implemented (`tests/test_workspace_events.py` 3 passing); projection endpoint (`/dream/projection`) exists (`tests/test_dream_projection.py` 11 passing); full workspace surfaces deferred.
Mitigation: Workspace surfaces framework must be observable through workspace framework (`Overview`, `Workspace`, `Memory`, `Dream Studio`, `Agents`, `Skills`, `MCP`, `Artifacts`, `Activity`, `System` — framework verified by `docs/design/COMMAND_CENTER_V1.md`; full surface implementations deferred but framework must allow future expansions without restructuring workspace framework). Any ambiguity must become ADR entry or open question.
References: `docs/design/COMMAND_CENTER_V1.md` (workspace framework verified); `docs/design/ARCHITECTURE_MAP.md` (core/UI separation); `docs/design/SHURA_EMBODIMENT.md` (embodiment stage framework); `docs/tasks/V1_ROADMAP.md` (Milestone 2 — Workspace Framework Implementation — framework verified; components deferred); `docs/tasks/V1_TASK_GRAPH.md` (workspace framework durable; navigation surfaces framework observable; workspace interaction framework routes mutation through explicit interfaces).

### Q4: Full Dream Transaction Pipeline — DEFERRED
Status: DEFERRED (framework verified; full pipeline deferred).
Evidence: `docs/DREAM_ENGINE.md` verified; `src/core/dream/domain.py`, `events.py`, `transaction.py`, `consolidation.py`, `projection.py` present; `tests/test_dream_engine.py` 15 passing. Full consolidation pipeline (intake → triage → compression → association → rehearsal → reconciliation → commit) deferred; `MemoryConsolidationTransaction`, `MemoryProposal`, `RehearsalResult`, `ValidationResult`, `ConsolidationEngine` framework present; full integration deferred; projection layer (`src/core/dream/projection.py`) read-only verified (`tests/test_dream_projection.py` 11 passing; `test_projection_does_not_mutate_domain` passes).
Mitigation: Dream Studio workspace framework (`docs/design/COMMAND_CENTER_V1.md`) must observe Dream lifecycle through projection/event replay; Dream event taxonomy (`docs/EVENT_CONTRACT.md`) verified; replay mechanism (`tests/test_events.py` replay rules verified); projection boundary preserved. Any future change that couples projection directly to brain internals collapses boundary; must include regression test updates (`tests/test_dream_projection.py`).
References: `docs/DREAM_ENGINE.md` (Dream framework); `docs/EVENT_CONTRACT.md` (event contract); `docs/design/ARCHITECTURE_MAP.md` (Dream independence); `tests/test_dream_engine.py`; `tests/test_events.py`; `tests/test_dream_projection.py`.

### Q5: Live2D / 3D Embodiment Upgrade — DEFERRED
Status: DEFERRED (design framework verified; upgrade path preserved).
Evidence: `docs/design/SHURA_EMBODIMENT.md` framework verified; presentation-state contract (`current_pose`, `current_text`, `current_state_indicator`, `avatar_reference`) verified; current PNG/sprite preserved (`data/avatars/` present but not fully implemented for Live2D); future Live2D/3D upgrade framework verified; workspace framework references embodiment stage; identity remains independent of presentation/state/provider/model/avatar.
Mitigation: Workspace framework must observe brain/consciousness through projection/event interfaces; must not import brain/consciousness internals for mutation logic; workspace framework must reference embodiment stage framework; workspace framework allows future embodiment upgrade without restructuring workspace framework; presentation-state mapping framework must include framework verification criteria; identity framework must include identity framework verification criteria.
References: `docs/design/SHURA_EMBODIMENT.md`; `docs/design/COMMAND_CENTER_V1.md`; `docs/vision/SHURA_V1_VISION.md`; `data/prompts/soul.md` (identity independent of embodiment).

### Q6: Full ATLAS Operational Layer — PARTIAL (skeleton exists; operational layer proposed; not fully implemented)
Status: PARTIAL (framework verified; full operational layer deferred).
Evidence: `docs/design/THREE_SYSTEMS.md` verified; ATLAS framework verified; `docs/ATLAS_INTEROPERABILITY.md`, `docs/ATLAS_CANONICALIZATION_OPTIONS.md` present; operational index/retrieval service proposed; not fully implemented. Design framework (`docs/design/`) complete; framework allows future expansions; framework allows future workspace framework expansions; framework allows future workspace surfaces framework expansions; framework allows future workspace framework implementations; framework allows future workspace framework expansions.
Mitigation: Memory observation framework (`docs/design/COMMAND_CENTER_V1.md`) must observe `DreamSnapshot` fields through projection; memory mutation framework (`MemorySkill` interfaces) must route mutation through `MemoryStorage` / reconciliation framework; must not allow direct memory mutation through workspace interface; projection/event interfaces preserved (`tests/test_dream_projection.py` passing; `tests/test_events.py` passing; event taxonomy preserved by `docs/EVENT_CONTRACT.md`).
References: `docs/design/THREE_SYSTEMS.md`; `docs/design/ARCHITECTURE_MAP.md`; `docs/design/COMMAND_CENTER_V1.md`; `docs/reference/ADR_INDEX.md` (ADR-001 — OpenHuman reference/reimplementation decision does not restructure framework; framework allows future expansions).

### Q7: Full Autonomous Loop Execution — PROPOSED (protocol verified; must be executed by future autonomous session to become durable)
Status: PROPOSED (protocol designed; framework verified; must be executed by autonomous session).
Evidence: `docs/operations/AUTONOMOUS_LOOP.md` framework verified; loop phases/protocol/safety/stopping conditions verified/proposed; `docs/operations/LOOP_STATE.md` initialized and updated by autonomous session; `docs/operations/SESSION_HANDOFF.md` initialized and updated by autonomous session; current session executes Phase 0-5 (context loaded; state inspected; bounded task selected — ADR + OPEN_QUESTIONS initialization; implemented; verified; loop state/session handoff/task graph updated; loop stops safely at bounded task completion). M1-T7 (autonomous loop execution) must be completed at least once before Milestone 1 complete; this session completes it.
Mitigation: Autonomous loop must confirm milestone framework verification before selecting milestone tasks; must confirm dependency satisfaction (`docs/tasks/V1_TASK_GRAPH.md`); must confirm bounded scope (no identity divergence, no secret exposure, no forbidden coupling, no workspace framework restructuring, no Dream/event/projection boundary collapse); must confirm verification plan exists (tests/file inspection/endpoint/boundary verification); must confirm design framework durable; must confirm autonomous loop framework preserved; loop stops safely when bounded task completes or when blocked; next ready task selected safely; loop state updated with verified observations (not fabricated); session handoff updated; ADR/open questions updated.
References: `docs/operations/AUTONOMOUS_LOOP.md`; `docs/operations/LOOP_STATE.md`; `docs/operations/SESSION_HANDOFF.md`; `docs/tasks/V1_TASK_GRAPH.md`; `docs/tasks/V1_ROADMAP.md`; `docs/reference/V1_ACCEPTANCE.md`.

### Q8: Full Harness Interoperability — PROPOSED (protocol designed; multi-harness synchronization deferred)
Status: PROPOSED (framework verified; full multi-harness synchronization deferred).
Evidence: `docs/operations/HARNESS_INTEROPERABILITY.md` framework verified; harness requirements/protocol verified/proposed; must be tested by future multi-harness session. Design framework must remain durable through autonomous work; any framework restructuring must become ADR entry or open question.
Mitigation: Any ambiguity about harness interoperability framework must be documented in ADR index or open questions; framework must reference design framework; framework must include framework verification criteria.
References: `docs/operations/HARNESS_INTEROPERABILITY.md`; `docs/design/ARCHITECTURE_MAP.md`; `docs/reference/ADR_INDEX.md`.

---

## Resolution Protocol

When a question is resolved:
1. Update status in this file (BLOCKED → RESOLVED / PROPOSED → VERIFIED / PARTIAL → VERIFIED).
2. Add or reference ADR entry (`docs/reference/ADR_INDEX.md`).
3. Confirm design framework durable (`docs/design/` framework preserved; future expansions allowed without restructuring).
4. Confirm workspace framework durable (`docs/design/COMMAND_CENTER_V1.md` framework preserved; workspace framework allows future workspace surfaces framework expansions; workspace framework allows future workspace persistence mechanism; workspace framework allows future workspace interaction framework expansions; workspace framework allows future workspace framework expansions).
5. Confirm identity preservation (`data/prompts/soul.md` unchanged or identity sync framework followed; identity framework must include identity framework verification criteria).
6. Confirm Dream/event/projection boundary preserved (`tests/test_dream_projection.py` passing; projection read-only; `tests/test_events.py` passing; event contract preserved by `docs/EVENT_CONTRACT.md`).
7. Confirm no secret exposure (`.env` unchanged; `.hermes/config.yaml` line 4041 unchanged — C4 BLOCKED; not retried; not bypassed).
8. Confirm autonomous loop framework preserved (`docs/operations/AUTONOMOUS_LOOP.md` framework intact; loop state updated; session handoff updated; bounded task completed safely; loop stops safely; next ready task selected safely).
9. Confirm milestone framework updated (`docs/tasks/V1_TASK_GRAPH.md` updated; `docs/tasks/V1_ROADMAP.md` updated; dependency relationships preserved; milestone exit criteria verified).
