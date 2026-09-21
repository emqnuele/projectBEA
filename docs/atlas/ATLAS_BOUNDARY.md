# ATLAS Domain Boundary

**Status:** Implemented (Phase M1 completion)  
**Owner:** ATLAS operational layer  
**Canonical reference:** `docs/architecture.md` §2.2, §4.5, §12

---

## Purpose

ATLAS is the operational/orchestration layer that sits between ProjectSHURA core and
FORGE. It owns the durable project registry, work items, milestones, decisions, and
artifacts. It provides a read-only snapshot that FORGE and the web layer can consume.

ATLAS is **not** a documentation folder. It is a code module (`src/core/atlas/`) with
a clear domain boundary. The `docs/` folder is the knowledge/documentation layer that
ATLAS will eventually index and retrieve from — but ATLAS the module is the runtime
service that manages project/work state.

---

## What ATLAS Owns

| Concept | Model | Notes |
|---|---|---|
| Project | `Project` | Top-level container. Has status (active/paused/completed/archived). |
| Work item | `WorkItem` | Task, bug, feature, or decision record. Has status, priority, type, depends_on, assigned_to. |
| Milestone | `Milestone` | Named phase boundary. Ordered. Has target_date. |
| Decision | `Decision` | Architectural decision record. Has context, decision, consequences. |
| Artifact | `Artifact` | Reference to an external resource (file, URL, doc, image, code). |
| Snapshot | `AtlasSnapshot` | Read-only aggregate of all above. Built by `AtlasService.snapshot()`. |

---

## What ATLAS Does NOT Own

- **Identity** — `data/prompts/soul.md` stays in ProjectSHURA. ATLAS never touches it.
- **Cognition** — brain/consciousness loop stays in ProjectSHURA. ATLAS never imports it.
- **Rendering** — PNG, OBS, Live2D, 3D, UI coordinates: all FORGE/Expression territory.
- **Event transport** — ATLAS uses `EventManager` only. It does not create a new bus.
- **Dream state** — DreamEngine domain stays in `src/core/dream/`. ATLAS does not import it.
- **Memory storage** — ChromaDB/memory stays in ProjectSHURA. ATLAS does not touch it.
- **Provider configuration** — `BrainConfig` stays in ProjectSHURA core.

---

## Event Contract

All ATLAS mutations emit `atlas.*` events through the existing `EventManager`. The
event type constants are in `src/core/atlas/models.py` — `AtlasEventType`.

**Subsystem:** `atlas`  
**Category:** `EventCategory.AGENT` (orchestration layer)  
**Source:** `atlas.service`

```
atlas.project.created     → payload: {project_id, name, description}
atlas.project.updated     → payload: {project_id, updates: [field names]}
atlas.project.active_changed → payload: {project_id, previous}
atlas.project.deleted     → payload: {project_id}

atlas.work_item.created  → payload: {item_id, project_id, title, priority, work_type}
atlas.work_item.updated  → payload: {item_id, updates: [field names]}
atlas.work_item.transitioned → payload: {item_id, project_id, from, to}
atlas.work_item.deleted  → payload: {item_id}

atlas.milestone.created  → payload: {milestone_id, project_id, name}
atlas.milestone.updated  → payload: {milestone_id, updates: [field names]}
atlas.milestone.completed → payload: {milestone_id, project_id}

atlas.decision.recorded  → payload: {decision_id, project_id, title}
atlas.decision.updated   → payload: {decision_id, updates: [field names]}

atlas.artifact.added     → payload: {artifact_id, project_id, name, kind, location}
atlas.artifact.removed   → payload: {artifact_id}
```

**No renderer details in ATLAS payloads.** No PNG paths, OBS scene names, Live2D
indices, UI coordinates, or CSS state.

---

## Web Endpoint Contract

| Endpoint | Method | Purpose | Mutation? |
|---|---|---|---|
| `/atlas/init` | POST | Lazy-initialize AtlasService on brain | Yes (one-time) |
| `/atlas/snapshot` | GET | Read-only full ATLAS snapshot | **No** |
| `/atlas/projects` | GET | List all projects | **No** |
| `/atlas/projects` | POST | Create project | Yes |
| `/atlas/projects/{id}` | GET | Get one project | **No** |
| `/atlas/projects/{id}` | POST | Update project | Yes |
| `/atlas/projects/{id}/active` | POST | Set active project | Yes |
| `/atlas/projects/{id}/delete` | POST | Delete project (cascade) | Yes |
| `/atlas/projects/{id}/work-items` | GET | List work items for project | **No** |
| `/atlas/projects/{id}/work-items` | POST | Create work item | Yes |
| `/atlas/work-items/{id}` | GET | Get one work item | **No** |
| `/atlas/work-items/{id}/transition` | POST | Transition status | Yes |
| `/atlas/milestones` | GET | List milestones | **No** |
| `/atlas/milestones` | POST | Create milestone | Yes |
| `/atlas/milestones/{id}/complete` | POST | Complete milestone | Yes |
| `/atlas/decisions` | GET | List decisions | **No** |
| `/atlas/decisions` | POST | Record decision | Yes |
| `/atlas/artifacts` | GET | List artifacts | **No** |
| `/atlas/artifacts` | POST | Add artifact | Yes |
| `/atlas/artifacts/{id}/delete` | POST | Remove artifact | Yes |

---

## Dependency Rule

```
ProjectSHURA core (events, brain, consciousness, expression, dream, presence)
  ↑ consumed by
ATLAS (src/core/atlas/)  — imports EventManager only
  ↑ consumed by
FORGE (src/core/forge/)  — imports PresenceRuntime + AtlasService + Dream projection
  ↑ consumed by
Web layer (src/web/app.py) — imports brain + atlas + forge
  ↑ consumed by
Frontend (src/web/frontend/) — consumes HTTP endpoints only
```

**ATLAS never imports:** `brain`, `consciousness`, `expression`, `dream`, `presence`
(runtime), or any renderer module.

** ATLAS does import:** `events` (EventManager, EventCategory, EventSeverity, EventVisibility).

---

## Persistence

In this milestone (M1), ATLAS is **in-memory**. The `AtlasService` holds all state
in process memory. On restart, the registry is empty.

**M2 plan:** Add a file-based or database-backed persistence layer. Options:
- JSON file per project (simple, human-readable)
- SQLite (structured, queryable)
- Reuse existing `data/` conventions

Persistence must NOT store identity content. It stores operational/project state only.

---

## What FORGE Gets From ATLAS

The `/forge/state` endpoint calls `AtlasService.snapshot()` and includes in the
`ForgeState`:
- `active_project` — currently active project (name, status, description)
- `recent_work_items` — last 10 work items (title, status, priority, type, assigned_to)
- `active_milestones` — non-completed milestones (name, status, order)
- `recent_decisions` — last 5 decisions (title, status, decided_at)

FORGE displays these. It does not mutate them through the `/forge/state` endpoint.

---

## Open Questions

- Should ATLAS get a proper persistence layer in M2, or should project state live
  in the existing `docs/` folder as structured markdown?
- Should ATLAS have an indexing/retrieval service that scans `docs/` for architecture
  decisions and project context?
- Should ATLAS events be surfaced in the FORGE activity feed, or are they too granular?
