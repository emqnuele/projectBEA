# OpenHuman Reference Analysis — REFERENCE ONLY

Status: REFERENCE (not source of truth for ProjectSHURA)
Source file: `/Users/ultraviollett/.hermes/attachments/tinyhumansai-openhuman-8a5edab282632443.txt`
Verified characteristics of the artifact:
  - Size: 50,358,637 bytes
  - Lines: 1,309,666 (truncated in reads)
  - Content type: repository directory snapshot (`tinyhumansai/openhuman/`)
  - Not tracked in `git status` of ProjectSHURA
  - Not present in working tree (`find src/` shows no openhuman code)
  - Contains React/Vite frontend structure (`app/src/App.tsx`, pages, components, hooks), Rust backend (`build.rs`, `Cargo.toml`), agent/task/workflow framework, mascot/avatar presentation, event/subscription model, desktop application architecture.

This document exists to document what we LEARNED from the reference and how it translates into FORGE requirements. It does NOT claim that OpenHuman architecture should be copied directly into ProjectSHURA.

---

## What the Reference Provides (VERIFIED by directory inspection)

A. Product experience model:
- A central workspace application (not just chat).
- A visible agent/mascot presence (the user's primary interaction target).
- Navigation with workspace surfaces: Home, Conversations, Brain, Channels, Flows, Skills, Settings.
- Task/activity representation (workflows, runs, approvals).
- Event feed / audit trail.
- Sub-agent / agent process observation.
- Tool/MCP inventory and usage.
- Project/session context persistence.
- Real-time updates (socket/event stream).

B. Technical architecture reference:
- React/Vite frontend with component-level organization.
- FastAPI-style backend (inferred from endpoint patterns and service layer names in the artifact listing).
- State management via centralized store (`store/` directory with slices: accounts, agentProfile, chatRuntime, connectivity, theme, etc.).
- Event/socket layer (`socketService`, `coreSocket`, `coreRpcClient`).
- Agent library (`AgentLibraryPanel`, `agentProfilesApi`).
- Workflow/task framework (`flowsApi`, `workflowRunsApi`, `FlowCanvas`, `NodePalette`).
- Skill registry (`SkillsExplorerTab`, `SkillCard`, `skillRegistryApi`).
- Memory/intelligence layer (`MemoryWorkspace`, `memorySourcesService`, `IntelligenceMemoryTab`).
- Desktop/runtime model (`LocalTransport`, `CloudHttpTransport`, `TunnelTransport`).
- Settings/config persistence with theme, voice, routing, permissions.

---

## Translation to FORGE (PROPOSED)

| OpenHuman Concept (REFERENCE) | FORGE Equivalent (PROPOSED) | Relationship to ProjectSHURA | Status |
|---|---|---|---|
| Central agent mascot (avatar) | Central SHURA embodiment (`Shura_01` / current PNG/sprite; future Live2D/3D) | Uses `Expression` adapter (`expression.py`) for presentation; identity stays in `data/prompts/soul.md` | PROPOSED embodiment upgrade; current PNG preserved |
| Workspace surfaces (Home, Conversations, Brain, Channels, Flows, Skills, Settings) | Navigation modules (`Overview`, `Workspace`, `Memory`, `Dream Studio`, `Agents`, `Skills`, `MCP`, `Artifacts`, `Activity`) | FORGE workspace surfaces observe `ProjectSHURA` state; they do not replace brain/consciousness | PROPOSED |
| Agent/task/workflow framework (`flows/`, `tasks/`, `agentLibrary/`) | Agent/task model inside FORGE workspace (`agents/` panel); event observation through `EventManager.subscribe()` | FORGE displays agent/task state; `ProjectSHURA` brain/consciousness executes agents/tools | PROPOSED |
| Event/socket layer (`socketService`, `coreSocket`) | Existing `EventManager.subscribe()` + replay (`events.py`); web endpoint `/events`; future event adapter for UI subscription | FORGE uses existing event infrastructure; does not create a separate event bus | VERIFIED (`events.py` exists and works) |
| Memory/intelligence (`MemoryWorkspace`, `memorySourcesService`) | ATLAS durable context + `MemoryStorage` observable through projection (`DreamSnapshot` fields) | ATLAS holds durable architecture/knowledge; ProjectSHURA holds runtime memory; FORGE observes both | PARTIAL (ATLAS skeleton exists; operational layer proposed) |
| Skill registry (`SkillsExplorerTab`, `skillRegistryApi`) | Skill visibility in FORGE (`/skills` endpoint, `SkillsPage` in frontend skeleton) | FORGE observes `SkillRegistry`; skills remain independent of UI | VERIFIED (`src/web/app.py` `/skills` endpoint exists; frontend skeleton exists) |
| Settings/config (`settings/` slices, `coreConfig`) | `BrainConfig` (`config.py` → `config.json`) + future UI settings layer | ProjectSHURA owns identity/model routing/config; FORGE UI owns presentation settings (theme, layout) | PARTIAL (config exists; presentation settings proposed) |
| Desktop runtime (`LocalTransport`, `CloudHttpTransport`) | Web layer (`FastAPI` + React/Vite) + CLI (`cli.py`); no native desktop binary required for V1 | FORGE runs locally through existing web server; future desktop wrapper is deferred | PROPOSED desktop wrapper deferred |

---

## Key FORGE Design Principles Derived from Reference + ProjectSHURA Constraints

1. **Workspace metaphor, not dashboard metaphor**. The user should feel like they are entering SHURA's workspace — not opening a control panel. This aligns with the Command Center spec (`docs/SHURA_COMMAND_CENTER_SPEC.md`) and the OpenHuman workspace model.
2. **Agent presence is primary**. The central SHURA embodiment is not decorative. Its states (idle, working, thinking, dreaming, error, attention, success) must reflect real runtime conditions (event replay, active skills, current task phase, current model/provider reference — though identity remains independent of provider).
3. **Strict core/UI separation preserved**. The OpenHuman pattern shows a centralized store (`store/`) that the UI consumes. ProjectSHURA must not collapse brain/consciousness/event logic into the UI store. The projection layer (`projection.py` + `/dream/projection` endpoint) demonstrates the boundary: UI reads through a stable projection interface, not through direct brain internals.
4. **Task visibility without task ownership confusion**. For V1, tasks can be observed through the workspace/event stream; full autonomous task execution (agent assignment, execution, approval, commit) is the autonomous loop target (`docs/operations/AUTONOMOUS_LOOP.md`), not a V1 UI feature.
5. **Reimplementation preferred over direct fork** (see `docs/design/FORK_STRATEGY.md`). OpenHuman's React component organization, event/subscription patterns, agent/task framework design, and workspace layout should be REIMPLEMENTED in FORGE, not directly imported. The reference serves as a design target, not code upstream.
6. **No dependency cycle created**. The projection endpoint (`/dream/projection`) uses `brain.event_manager` but does not import consciousness/expression/avatar directly. This must remain true for any future endpoint. Any endpoint that requires brain internals must go through an explicit service/application boundary.
