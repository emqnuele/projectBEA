# Autonomous Development Loop — V1 Protocol (VERIFIED + PROPOSED)

Status: Design / operating protocol — must be implemented as durable process.
Based on verified current test state (48 passing), verified repo structure (`docs/`, `tests/`, `src/`), and the autonomous loop requirements from the design pass instructions.

This protocol must work without the user's continuous direction. It must stop safely. It must prove work was tested.

---

## 1. Loop Entry Conditions (VERIFIED / PROPOSED boundary)

Before autonomous work begins, the harness / agent must verify:

A. Context loaded (`docs/operations/LOOP_STATE.md` exists and is current; `docs/operations/SESSION_HANDOFF.md` exists; `docs/tasks/V1_TASK_GRAPH.md` exists; `docs/vision/SHURA_V1_VISION.md` exists; `docs/design/ARCHITECTURE_MAP.md` exists; `docs/reference/OPENHUMAN_REFERENCE.md` exists).
B. Repository clean or explained (`git status` shows only expected modifications — no uncommitted secrets, no identity file divergence without explanation, no `.env` changes).
C. Identity verified (`data/prompts/soul.md` present; identity sync status documented in `docs/IDENTITY_SYNC.md`; MD5 identity check `6aabb046958ddedaf0bd62b14ad6fe18` preserved unless governed change documented).
D. Tests pass (`python -m unittest tests/test_dream_engine.py tests/test_events.py tests/test_dream_projection.py` returns OK — verified by previous execution). If tests fail, autonomous loop stops and reports failure in loop state.
E. No dangerous modifications pending (no `.env` modifications, no secret exposure, no identity file rewrites, no git history rewrites). If any of these conditions fail, loop stops and reports BLOCKED.

---

## 2. Autonomous Loop Phases (PROPOSED — must become durable process)

Each autonomous session follows this sequence exactly:

### Phase 0 — LOAD CONTEXT
1. Read `docs/operations/SESSION_HANDOFF.md`.
2. Read `docs/operations/LOOP_STATE.md`.
3. Read `docs/tasks/V1_TASK_GRAPH.md`.
4. Read `docs/tasks/V1_ROADMAP.md`.
5. Read `docs/design/CURRENT_STATE.md` (verified current repo state).
6. Inspect `git status --short`, `git branch --show-current`, `git log -1 --oneline`.
7. Confirm `.env` unchanged (`git diff -- .env` empty).
8. Confirm identity files unchanged (unless governed change documented with identity sync record).
9. Confirm C4 config state unchanged (`.hermes/config.yaml` line 4041 token unchanged; `.env` unchanged; identity files unchanged). Note C4 remains BLOCKED (security mechanism); this does not block autonomous loop but is documented in loop state.
10. Confirm Dream Engine boundary preserved (`src/core/dream/domain.py`, `events.py`, `projection.py` unmodified by autonomous actions; any projection updates must follow boundary rules).
11. Confirm event contract preserved (`docs/EVENT_CONTRACT.md` unchanged; event taxonomy unchanged unless new event types added with documentation).

### Phase 1 — INSPECT STATE
1. Read current loop state (what phase, what milestone, what active task, what completed, what blocked).
2. Inspect test results (run `python -m unittest` on relevant test modules; record pass/fail counts).
3. Inspect repository modifications (`git diff --stat`, `git status --short`).
4. Inspect event journal (`data/events/events.jsonl` — verify persistence, replay, rotation behavior preserved).
5. Inspect Dream Engine state (if `run_id` active, read projection; verify projection deterministic; verify no mutation through projection).
6. Inspect ATLAS context (`docs/design/`, `docs/reference/`, `docs/vision/` — verify references current).
7. Record observations in `docs/operations/LOOP_STATE.md` (verified observations only; no fabricated observations).

### Phase 2 — SELECT READY TASK
1. Read task graph (`docs/tasks/V1_TASK_GRAPH.md`).
2. Identify tasks with status READY (dependencies satisfied; no BLOCKED dependency; previous tasks IMPLEMENTED + TESTED + VERIFIED).
3. Prefer the next bounded task in the milestone sequence (`docs/tasks/V1_ROADMAP.md`).
4. Confirm task boundaries (does the task modify identity? If yes, STOP — identity changes require governed review. Does the task modify `.env`? STOP. Does the task rewrite core identity (`soul.md`)? STOP. Does the task couple cognition to avatar PNG directly? STOP — must preserve `brain.py` / `expression.py` separation. Does the task collapse Dream Engine boundary? STOP — projection layer must remain read-only; mutation through `/dream/run` or service layer only).
5. Confirm task test plan (`tests/test_...` files referenced; new tests must be focused and deterministic).
6. Confirm task does not expand scope beyond bounded change (no giant frontend rewrite; no full workspace shell implementation; only the next bounded architectural slice).

### Phase 3 — IMPLEMENT BOUNDED TASK
1. Read relevant source (`read_file` verified files; `search_files` for related symbols; trace definitions to usages).
2. Implement only the files required by the task description.
3. Include focused tests (`tests/test_...` — at minimum: deterministic behavior, safe malformed-state handling, no mutation of unrelated systems, no forbidden direct coupling).
4. Verify with `python -m unittest` (narrow relevant module first; broader suite if practical).
5. Inspect `git diff -- <changed files>` — confirm only intended files changed; confirm no unrelated refactoring.

### Phase 4 — VERIFY BOUNDARY PRESERVATION
1. Confirm Dream Engine domain untouched (`git diff -- src/core/dream/domain.py src/core/dream/events.py src/core/dream/transaction.py` shows no unauthorized changes).
2. Confirm identity untouched (`git diff -- data/prompts/soul.md .env` shows no unauthorized changes).
3. Confirm event contract preserved (new events, if any, use `EventCategory.DREAM` / `subsystem="dream"` / structured payload; no arbitrary message-based state inference).
4. Confirm projection layer boundary preserved (projection reads domain + replay; does not mutate domain; does not import brain/consciousness/expression directly for mutation logic — only through stable interfaces).
5. Confirm web/app endpoint safe (`/dream/projection` read-only; `/dream/run` routes mutation through `brain.run_dream()`; no direct brain mutation from endpoint).
6. Confirm test results (`python -m unittest` passes).

### Phase 5 — UPDATE STATE
1. Update `docs/operations/LOOP_STATE.md` with what was completed (verified observation, not proposal).
2. Update `docs/tasks/V1_TASK_GRAPH.md` with new task status (READY → IMPLEMENTED → TESTED → VERIFIED, or BLOCKED with reason).
3. If a new document was created (`docs/design/...`, `docs/reference/...`, `docs/operations/...`), reference it in loop state.
4. If an architecture decision was made, add it to `docs/reference/ADR_INDEX.md` (or create one entry).
5. If an open decision remains unresolved, add it to `docs/reference/OPEN_QUESTIONS.md` (or `docs/design/OPEN_QUESTIONS.md` if created).
6. Confirm no identity divergence (`docs/IDENTITY_SYNC.md` or loop state notes any identity-related changes — must have human review if identity changed).

### Phase 6 — SELECT NEXT READY TASK
1. Re-read loop state (Phase 5 results).
2. Identify next READY task from `docs/tasks/V1_TASK_GRAPH.md`.
3. Confirm next task does not conflict with verified current state (e.g., does not require a feature that was deferred; does not assume full workspace shell exists when only skeleton exists).
4. Confirm autonomous work can continue safely (tests pass, identity unchanged, secrets unchanged, C4 state unchanged, projection boundary preserved).

---

## 3. Safety Boundaries — When Loop Must Stop (VERIFIED + PROPOSED)

The autonomous loop must STOP and report BLOCKED (not continue blindly) under these conditions (verified by design requirements and previous audit rules):

1. Identity divergence (`soul.md` changed without identity sync verification; MD5 identity check fails without documented governed change).
2. Secret exposure (`.env` modified; `.hermes/config.yaml` secret token changed; API key exposed in code/test output; new file contains secret reference).
3. C4 mechanism triggered (security mechanism blocks execution; user must explicitly approve; autonomous loop must not attempt to bypass).
4. Dream Engine boundary collapse (`domain.py` / `events.py` / `projection.py` unauthorized mutation through projection or direct domain mutation from web/app endpoint without explicit command routing).
5. Test failure (`python -m unittest` fails on narrow or broad suite; autonomous work does not proceed with broken tests).
6. Unbounded scope expansion (autonomous task tries to expand from bounded change to full workspace shell; tries to build full Dream Transaction pipeline before projection boundary stable; tries to implement full ATLAS operational layer before skeleton documented).
7. Missing durable context (`docs/operations/LOOP_STATE.md` missing or stale; `docs/tasks/V1_TASK_GRAPH.md` missing; session handoff missing; autonomous agent cannot determine current state).
8. Forbidden coupling introduced (UI/project/component imports `brain.consciousness`, `brain.event_manager` for mutation logic rather than through event/projection/application interfaces; identity references appear in provider/model code; cognition imports expression/avatar internals).
9. No user consent for destructive actions (autonomous loop must not commit to git, push, rewrite history, or release without explicit user authorization — this is a loop boundary, not a design proposal; it must be preserved).

---

## 4. Loop State Format (VERIFIED + PROPOSED)

The loop state file (`docs/operations/LOOP_STATE.md`) must always contain the following sections (updated after each autonomous session):

```
# LOOP STATE — [Date / Timestamp]
## CURRENT CONTEXT
- Branch: shura-foundation (or current branch name verified by `git branch`)
- Last commit: [hash] [message]
- Active milestone: [milestone from V1_ROADMAP.md]
- Active phase: [current loop phase: 0 / 1 / 2 / 3 / 4 / 5 / 6]
- Active task: [task ID from V1_TASK_GRAPH.md] — [task title] — status: [READY / IN_PROGRESS / IMPLEMENTED / TESTED / VERIFIED / BLOCKED]
- Recent completed tasks (last 3): [list with verification evidence]
## CURRENT STATE OBSERVATIONS (VERIFIED)
- Identity: soul.md unchanged (or identity sync record referenced if changed with human approval); MD5 `6aabb046958ddedaf0bd62b14ad6fe18` (or new verified hash with explanation)
- .env unchanged; no secret exposure
- .hermes/config.yaml line 4041 unchanged: `${MCP_...KEY}` (C4 blocked — separate infrastructure issue; loop notes this but does not retry indefinitely)
- Dream boundary preserved: domain/events/projection unchanged by autonomous work; projection endpoint `/dream/projection` exists; no mutation through projection
- Tests: [count passing] / [count total] — modules tested: [list]
- Repository modifications: [git diff --stat summary]
## DECISIONS MADE (VERIFIED or PROPOSED — must distinguish)
- [Decision description] — verified by [evidence file/test/endpoint] OR proposed (not yet implemented)
## OPEN QUESTIONS / OPEN DECISIONS
- [List with reference to docs/reference/OPEN_QUESTIONS.md if exists]
## BLOCKED / RISKS
- [Blocked item with reason — C4 mechanism, missing feature, test failure, identity issue, architecture conflict]
- [Risk with mitigation — projection boundary, event contract stability, identity divergence, provider lock-in risk]
## NEXT READY TASK
- [Task ID from V1_TASK_GRAPH.md] — [title] — [brief justification: dependencies satisfied, no blocked dependency, bounded scope, verification plan]
```

---

## 5. Session Handoff Requirements (VERIFIED + PROPOSED)

Every autonomous session must update (`docs/operations/SESSION_HANDOFF.md`) with:
- Date / harness used / branch / model reference (operational reference, not identity)
- Work completed (verified by tests + git diff + file inspection)
- Test results (specific test module names + pass/fail counts)
- Decisions (verified observations vs proposed architecture changes — must distinguish)
- Architecture changes (only if bounded; must preserve identity, event contract, Dream boundary)
- Next task reference (from `docs/tasks/V1_TASK_GRAPH.md`)
- Blockages (C4 mechanism status — blocked; identity sync status — verified; Dream boundary — preserved; event contract — preserved)
- Context preservation (loop state file reference; ATLAS reference documents referenced; design docs referenced)

The session handoff must be readable by a different harness (`Hermes`, `Crush`, `JCode`, `Pi`, `OpenCode`) without access to this conversation. It relies on file references (`docs/operations/LOOP_STATE.md`, `docs/tasks/V1_TASK_GRAPH.md`, source file paths) rather than conversational context.

---

## 6. What the User Should Observe When Returning (VERIFIED + PROPOSED)

When the user returns after an autonomous session, they should find:
- Updated `docs/operations/LOOP_STATE.md` (verified observations, not fabricated).
- Updated `docs/tasks/V1_TASK_GRAPH.md` (task status changes with evidence references).
- Updated `docs/operations/SESSION_HANDOFF.md` (work completed, tests run, decisions made).
- New or modified implementation files only within bounded task scope (verified by `git diff -- <changed files>`).
- No `.env`, identity file, or secret modifications (verified by `git status` and `git diff`).
- No C4 mechanism bypass (verified by `.hermes/config.yaml` line 4041 unchanged; `.env` unchanged; identity unchanged).
- All relevant tests passing (`python -m unittest` verified).
- Projection endpoint (`/dream/projection`) unchanged in its read-only behavior (verified by endpoint inspection and projection tests).
- Dream Engine domain boundary preserved (verified by `git diff -- src/core/dream/` — only intended changes, no boundary collapse).
- A clear NEXT READY TASK listed in loop state, with justification (dependencies satisfied, no blocked dependency, bounded scope, verification plan).
- Any OPEN QUESTIONS or OPEN DECISIONS documented in `docs/reference/OPEN_QUESTIONS.md` or loop state, rather than silently resolved in conversation.
