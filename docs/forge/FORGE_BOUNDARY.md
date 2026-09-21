# FORGE Boundary

**Status:** Implemented (Phase M1 completion)  
**Owner:** FORGE frontend/avatar layer  
**Canonical reference:** `docs/architecture.md` §2.3, §6, §9, §12

---

## Purpose

FORGE is the human-facing workspace/avatar environment. It is the outer layer of the
ProjectSHURA ecosystem — the place where Viollett and SHURA work together. FORGE
consumes semantic state from the layers below and produces a renderer-agnostic state
object (`ForgeState`) that any frontend or avatar renderer can consume.

FORGE is **not** a chat window. It is a workspace/studio/cockpit. The reference
product direction is llm-vtuber-style continuous presence — the avatar should
eventually be able to remain present above or alongside other desktop applications.

---

## What FORGE Owns

| Concept | Location | Notes |
|---|---|---|
| ForgeState | `src/core/forge/contract.py` | Single semantic state object. Aggregates presence + ATLAS + dream + events. |
| ForgePresenceState | `src/core/forge/contract.py` | Enum: offline, idle, listening, thinking, speaking, interrupted, dreaming, error. |
| ForgeProjection | `src/core/forge/contract.py` | Builds ForgeState from core interfaces. Read-only. |
| Frontend UI | `src/web/frontend/` | React + Vite SPA (skeleton only in M1). |
| Workspace state | FORGE frontend store | Navigation selection, open panels, UI settings. |
| User interaction state | FORGE frontend | Pending approvals, command input history. |

---

## What FORGE Does NOT Own

- **Identity** — `data/prompts/soul.md` stays in ProjectSHURA. FORGE never touches it.
- **Cognition** — brain/consciousness loop stays in ProjectSHURA. FORGE never imports it.
- **Event creation** — FORGE does not create events. It subscribes/replays only.
- **Dream mutation** — `/dream/run` is the mutation endpoint. FORGE observes through
  `/dream/projection` and `/forge/state`.
- **ATLAS mutation** — ATLAS CRUD goes through `/atlas/*` endpoints. FORGE observes
  through `/atlas/snapshot` and `/forge/state`.
- **Expression rendering** — TTS, OBS, avatar pose switching: owned by `Expression`
  adapter (`src/core/expression.py`). FORGE observes the result through events.
- **Provider configuration** — `BrainConfig` stays in ProjectSHURA core.

---

## ForgeState Contract

`ForgeState` is the single object FORGE consumes. It is **semantic and
renderer-agnostic**. It must never contain:

**FORBIDDEN:**
- PNG file paths or sprite indexes
- OBS scene names or source IDs
- Live2D model indexes or parameters
- VRM/3D model references
- UI coordinates, viewport sizes, panel positions
- Frontend widget IDs
- Arbitrary CSS state
- Renderer-specific animation instructions

**REQUIRED (semantic):**
- `presence_state` — current semantic presence state (offline/idle/listening/thinking/speaking/interrupted/dreaming/error)
- `is_connected` — whether the runtime is connected
- `emotion` — semantic emotion label (may map to legacy mood IDs)
- `motion` — semantic motion label
- `is_speaking` — whether SHURA is currently speaking
- `is_sleeping` — whether consciousness is asleep
- `is_dreaming` — whether a dream/consolidation run is active
- `active_project` — ATLAS active project (project_id, name, description, status)
- `recent_work_items` — last work items (title, status, priority, type, assigned_to)
- `active_milestones` — non-completed milestones
- `recent_decisions` — recent architectural decisions
- `dream_state` — DreamStateProjection fields (run_id, run_state, concepts, threads, etc.)
- `recent_events` — last 20 events (event_type, subsystem, message, severity, payload_summary)
- `notifications` — user-attention items (initially empty; future mechanism)

The `emotion` field maps to legacy mood IDs where applicable. The `motion` field is
a semantic animation label that any renderer can interpret.

---

## Dependency Rule

```
ProjectSHURA core (events, brain, consciousness, expression, dream, presence)
  ↑ consumed by
ATLAS (src/core/atlas/)  — imports EventManager only
  ↑ consumed by
FORGE (src/core/forge/)  — imports EventManager + PresenceRuntime + AtlasService snapshot + Dream projection
  ↑ consumed by
Web layer (src/web/app.py) — imports brain + atlas + forge
  ↑ consumed by
Frontend (src/web/frontend/) — consumes HTTP endpoints only
```

**FORGE never imports:** `brain`, `consciousness`, `expression`, `dream` (domain),
`presence` (runtime internals beyond `PresenceRuntime`), or any renderer module.

**FORGE does import:**
- `events` — `EventManager` (for recent events)
- `presence.runtime` — `PresenceRuntime` (for current presence state, emotion, motion)
- `atlas.service` — `AtlasService.snapshot()` (for project/work context)
- `dream.projection` — `get_current_dream_projection()` (for dream state)

All of these are read-only consumption. FORGE never calls mutation methods on them.

---

## Web Endpoint Contract

### Observation (read-only)

| Endpoint | Purpose |
|---|---|
| `/forge/state` | Aggregate ForgeState (presence + ATLAS + dream + events) |
| `/dream/projection` | DreamStateProjection (read-only) |
| `/atlas/snapshot` | Full ATLAS domain snapshot (read-only) |
| `/events` | Recent in-memory events |
| `/workspace/dream-events` | Dream lifecycle events for workspace |
| `/status` | `is_speaking`, `is_sleeping`, `active_skills` |
| `/skills` | Skill registry (enabled/active/config) |

### Mutation (explicit commands)

| Endpoint | Purpose |
|---|---|
| `/dream/run` | Trigger dream/consolidation pass |
| `/dream/wake` | Wake consciousness |
| `/atlas/init` | Initialize ATLAS service (idempotent) |
| `/atlas/projects` | Create/list/update/delete projects |
| `/atlas/work-items` | Create/list/transition work items |
| `/atlas/milestones` | Create/complete milestones |
| `/atlas/decisions` | Record decisions |
| `/atlas/artifacts` | Add/remove artifacts |
| `/skills/{name}/toggle` | Enable/disable a skill |
| `/config` | Update brain config |
| `/chat` | Send text → perception + output |
| `/interrupt` | Interrupt speech |

**Rule:** The `/forge/state` endpoint is read-only. It does not mutate anything. All
mutation goes through explicit command endpoints.

---

## Frontend Architecture (M1 status)

`src/web/frontend/` — React + Vite SPA. Currently a skeleton. Not fully implemented.

**Planned navigation surfaces (from `docs/design/COMMAND_CENTER_V1.md`):**
1. Overview — system state summary
2. Workspace — primary collaboration surface
3. Memory — memory observations from DreamSnapshot + events
4. Dream Studio — Dream state + events
5. Agents — agent/task visibility
6. Skills — skill registry + invocation
7. MCP / Tools — MCP server/tool inspection
8. Artifacts — workspace artifact visibility
9. Activity — event feed / audit trail
10. System — health/config/status

**Embodiment stage:** A central SHURA avatar presence (PNG/sprite in M1, Live2D/3D
upgrade path preserved). The embodiment stage observes `ForgeState` and translates
semantic state to visual representation.

---

## Presence → Embodiment Mapping (from `docs/design/SHURA_EMBODIMENT.md`)

The mapping from `ForgeState` / `DreamStateProjection` fields to visual states:

| ForgeState / Projection field | Embodiment state | Visual (M1 PNG / future Live2D) |
|---|---|---|
| `presence_state` = listening | Listening | Subtle ear/attention animation |
| `presence_state` = thinking | Thinking | Thinking pose + subtle motion |
| `presence_state` = speaking | Speaking | Talking pose + typing animation |
| `presence_state` = interrupted | Interrupted | Interrupted pose + red indicator |
| `dream_state.run_state` = started | Working / active | Talking pose + typing |
| `dream_state.run_state` = snapshot_created | Observing / reading | Thinking pose |
| `dream_state.run_state` = reconciliation_started/completed | Processing / integrating | Working pose + glow |
| `dream_state.run_state` = completed | Completed / satisfied | Success pose + celebration |
| `dream_state.run_state` = failed | Error / blocked | Error pose + red indicator |
| `presence_state` = idle, no active dream | Idle / available | Idle pose + ambient animation |

This mapping is implemented as a **presentation adapter** in FORGE, not in brain/
consciousness/expression. The flow is: brain → events → projection → ForgeState →
embodiment adapter → visual rendering.

---

## llm-vtuber Product Direction

The highest-priority visual/product reference for FORGE is the concept demonstrated
by llm-vtuber-style systems: the avatar should eventually be able to remain
**continuously present** above or alongside the user's other desktop applications
instead of existing only inside a separate chatbot window.

This is a **product-direction reference, not an implementation blueprint.** The
architecture supports this through:
- `PresenceRuntime` — always-on semantic state
- `ForgeState` — continuous semantic state snapshot
- `/forge/state` — HTTP endpoint any frontend can poll or subscribe to
- Event subscription — `EventManager.subscribe()` for real-time updates

The desktop overlay/always-on presence is a FORGE frontend implementation detail.
It does not affect the core architecture.

---

## Open Questions

- Should FORGE have a WebSocket endpoint for real-time event streaming, or is HTTP
  polling sufficient for M2?
- Should the FORGE frontend be a standalone desktop app (Electron/Tauri) or remain
  a web app that can be embedded in a desktop overlay?
- What is the minimum viable embodiment stage for M2 — PNG/sprite with the presentation
  contract, or a basic Live2D integration?
- How should FORGE handle multiple concurrent workspaces (multiple projects open)?
