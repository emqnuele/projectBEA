# Harness Interoperability — V1 Protocol (VERIFIED + PROPOSED)

Status: Design / operating protocol — defines safe interaction between ProjectSHURA and development harnesses (`Hermes`, `Crush`, `JCode`, `Pi`, `OpenCode`, `Zed`, and future harnesses).

Verified harnesses mentioned in `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` and `docs/HERMES_COMMAND_CENTER_STATUS.md`:
- Hermes (verified working v0.21.1; SHURA skill active; MCP discovery working — Majik verified 148 tools)
- Crush (`docs/CRUSH.md` exists; `.crushrc`; `crush.db`; `.crush/` directory present — untracked)
- JCode / Pi / OpenCode (mentioned in architecture docs; no direct verification of live installations in this workspace — PROPOSED compatibility framework only)

---

## Interoperability Contract (PROPOSED — must be preserved)

Every harness must read the canonical context before beginning work. The canonical context is durable (file-based) and independent of the harness's transcript or conversational memory.

### Required Read Sequence (before any implementation action)

1. `docs/AGENTS.md` (current version — verified present, 41KB in master handoff; must be updated to include autonomous loop rules if not already present)
2. `docs/vision/SHURA_V1_VISION.md` (verified created in this design pass — must exist before autonomous work continues)
3. `docs/design/CURRENT_STATE.md` (verified current repo state — verified by file inspection and git status)
4. `docs/operations/LOOP_STATE.md` (current autonomous loop phase, milestone, active task, completed work, open blockages)
5. `docs/operations/SESSION_HANDOFF.md` (last session's work, decisions, next task, safety reminders)
6. `docs/tasks/V1_TASK_GRAPH.md` (dependency-aware task graph with READY/IMPLEMENTED/TESTED/VERIFIED/BLOCKED statuses)
7. `docs/tasks/V1_ROADMAP.md` (milestone-based roadmap with exit criteria)
8. `docs/design/ARCHITECTURE_MAP.md` (integration relationships — verified design file)
9. `docs/reference/OPENHUMAN_REFERENCE.md` (if design/reference question relates to workspace model — must treat as REFERENCE, not source of truth)
10. `docs/design/OPENHUMAN_TO_FORGE.md` (translation analysis — must reference when workspace/task design questions arise)
11. `docs/design/FORK_STRATEGY.md` (fork/reference/reimplementation decision — must reference when integration questions arise)
12. Relevant source/spec files (verified by `read_file` or `search_files` before editing): `brain.py`, `events.py`, `dream/domain.py`, `dream/projection.py`, `docs/EVENT_CONTRACT.md`, `docs/DREAM_ENGINE.md`, `docs/ARCHITECTURE_AUDIT.md`.

After reading, the harness must confirm:
- Identity preserved (`data/prompts/soul.md` unchanged unless identity sync documented).
- `.env` unchanged (`git diff -- .env` empty).
- `.hermes/config.yaml` unchanged (line 4041 token unchanged; C4 mechanism unchanged — separate infrastructure issue, reported separately, not retried indefinitely).
- Dream Engine boundary preserved (`git diff -- src/core/dream/` only intended changes).
- Event contract preserved (`docs/EVENT_CONTRACT.md` unchanged; new events, if any, follow taxonomy; no arbitrary message-based state inference).
- No forbidden coupling introduced (UI/project/component does not import brain/consciousness internals for mutation logic; identity independent of provider/model; cognition independent of avatar PNG/OBS directly).

### Safe Handshake Protocol (VERIFIED — must be durable for future autonomous sessions)

The harness must leave a durable session handoff file (`docs/operations/SESSION_HANDOFF.md`) after any implementation action, even if interrupted. The file must be readable by any future harness (Hermes, Crush, manual user) without conversational context.

The autonomous loop (`docs/operations/AUTONOMOUS_LOOP.md`) defines the sequence that every harness must follow. The loop must stop safely when:
- Any safety boundary is violated (identity divergence, secret exposure, C4 trigger, test failure, Dream boundary collapse, forbidden coupling).
- The user explicitly stops it.
- A bounded task completes and no READY task exists (loop stops at next selection; does not invent unverified work).

---

## Multi-Harness Coordination Rules (PROPOSED — framework for future expansion)

When multiple harnesses interact (e.g., Hermes for architecture/design, Crush for code review, JCode for implementation), the canonical operating state must remain consistent:

1. **Single source of truth for loop state**: Only `docs/operations/LOOP_STATE.md` records the current autonomous phase, milestone, active task, completed work, blockages. No harness creates a separate loop state.
2. **Single source of truth for task graph**: Only `docs/tasks/V1_TASK_GRAPH.md` defines tasks, dependencies, statuses. No harness creates parallel task tracking without updating this file.
3. **Single source of truth for session handoff**: Only `docs/operations/SESSION_HANDOFF.md` records what was completed, tested, and decided. No harness relies solely on its own transcript for continuity.
4. **Identity and secrets preserved across harnesses**: `data/prompts/soul.md`, `.env`, `.hermes/config.yaml` must not change unless identity sync process is followed (`docs/IDENTITY_SYNC.md` verified; governed review required). Any identity change must be documented with evidence; autonomous loop stops on identity divergence.
5. **Event journal durable across harnesses**: `data/events/events.jsonl` is the persistent event journal. Any harness that emits events uses `EventManager.publish()` (verified mechanism). Any harness that observes events uses `subscribe()` / `replay()` (verified mechanism). No harness creates a separate event database.
6. **Projection interface stable across harnesses**: `/dream/projection` endpoint (verified present; read-only; uses `build_projection()` with `brain.event_manager`) provides a stable interface. Any harness observing Dream state must use this endpoint (or the `DreamStateProjection` model directly through `build_projection()`), not direct brain internals.
7. **No harness creates a parallel identity layer**: Any harness that produces prompts, operating instructions, or persona definitions must place them under the identity layer (`data/prompts/`) and follow the identity sync process (verified: identity layer separate from operating layer per `docs/AGENTS.md` and `SHURA_MASTER_HANDOFF.md`).
8. **Autonomous loop stops when user directs**: The loop protocol (`docs/operations/AUTONOMOUS_LOOP.md`) includes explicit stopping conditions and user authorization requirements. A harness must not override user instructions or continue autonomous work after user interruption.

---

## Harness-Specific Requirements (VERIFIED / PROPOSED)

### Hermes (VERIFIED — current primary harness)
- Status: Working (`docs/HERMES_COMMAND_CENTER_STATUS.md` verified).
- Requirements for autonomous loop: Must read `docs/operations/LOOP_STATE.md` before selecting work. Must confirm identity unchanged. Must confirm `.env` unchanged. Must confirm Dream boundary preserved. Must use projection layer (`/dream/projection`) for Dream observation, not direct brain internals.

### Crush (VERIFIED — exists; `.crushrc`, `.crush/`, `crush.db` present — untracked)
- Requirements: Must not assume `brain.py` internals available directly. Must observe ProjectSHURA through web endpoints (`/dream/projection`, `/status`, `/skills`, `/events`) or through durable file state (`docs/operations/LOOP_STATE.md`, `tests/` results). Must not modify `.env` or identity files. Must update session handoff if any work completed.

### JCode / Pi / OpenCode (PROPOSED — mentioned in architecture specs; no direct verification of installation or current behavior in workspace)
- Requirements: Must treat `docs/operations/LOOP_STATE.md` and `docs/tasks/V1_TASK_GRAPH.md` as canonical operating state. Must not create parallel task tracking. Must respect ProjectSHURA identity layer separation. Must use event/projection interfaces for Dream observation.
