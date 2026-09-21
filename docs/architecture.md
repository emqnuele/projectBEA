# Architecture — ProjectSHURA v1

← [Back to README](../README.md)

---

## 1. Overview

ProjectSHURA is a modular personal AI runtime built around a single persistent identity
(SHURA) and a single consciousness loop. The architecture is divided into three tiers
that must remain strictly separated:

```
                         ┌─────────────────────────────────────────┐
                         │                FORGE                      │
                         │  Frontend / avatar / workspace / UI shell │
                         │  Consumes semantic state from below.      │
                         │  NEVER mutates core directly.             │
                         └───────────────────┬─────────────────────┘
                                             │ observes via
                                             │ projection + events
                         ┌───────────────────▼─────────────────────┐
                         │               ATLAS                      │
                         │  Operational / orchestration layer        │
                         │  Projects, work items, milestones,        │
                         │  decisions, artifacts, session context.   │
                         │  Emits atlas.* events. Read-only snapshot.│
                         └───────────────────┬─────────────────────┘
                                             │ consumes events
                         ┌───────────────────▼─────────────────────┐
                         │            PROJECTSHURA CORE              │
                         │  Identity + runtime + cognition + skills  │
                         │  brain | consciousness | expression |     │
                         │  perception | events | dream | skills     │
                         └─────────────────────────────────────────┘
```

**Rule:** FORGE and ATLAS consume stable interfaces from core. Core never imports
FORGE or ATLAS. No dependency cycles.

---

## 2. Three Systems

### 2.1 PROJECTSHURA (runtime + identity)

**Purpose:** The persistent synthetic persona runtime — identity, cognition, skills,
memory, dream, expression, event emission, and provider-agnostic reasoning.

**Verified components:**
- `AIVtuberBrain` (`src/core/brain.py`) — composition root
- `Consciousness` (`src/core/consciousness.py`) — single mind loop
- `PerceptionBus` (`src/core/perception/bus.py`) — sensory input aggregation
- `Expression` (`src/core/expression.py`) — output sink (TTS + OBS + avatar)
- `EventManager` + `BrainEvent` + `EventJournal` (`src/core/events.py`)
- `PresenceRuntime` + `PresenceProjection` (`src/core/presence/`)
- `DreamRun` / `DreamSnapshot` domain + Dream projection (`src/core/dream/`)
- `Skill` / `SkillRegistry` + surfaces (`src/core/skills/`)
- `LLMInterface` / `TTSInterface` / `OBSInterface` ABCs (`src/interfaces/`)
- LLM factory + omniroute/openai/groq/openrouter (`src/modules/llm/`)
- FastAPI web layer (`src/web/app.py`) + React/Vite frontend skeleton
- CLI (`src/cli.py`)

**Non-responsibilities:**
- Does NOT own workspace navigation, persistent project workspace, or cockpit UI
  (those belong to FORGE).
- Does NOT own durable architecture documentation, decision logs, or cross-session
  knowledge indexing (those belong to ATLAS).
- Does NOT couple cognition to PNG/OBS/Live2D or any specific renderer.

### 2.2 ATLAS (operational / orchestration layer)

**Purpose:** Durable project-level knowledge, architecture, documentation, decisions,
context indexing, session continuity, and cross-session reference — the persistent
memory layer that survives individual runtime sessions and harness changes.

**Implemented (this milestone):**
- `src/core/atlas/models.py` — `Project`, `WorkItem`, `Milestone`, `Decision`,
  `Artifact`, `AtlasSnapshot`, `AtlasEventType`
- `src/core/atlas/service.py` — `AtlasService`: domain service with full CRUD,
  event emission, cascade delete, read-only snapshot, and optional persistence
  via `AtlasRepository` (JSON snapshot to `data/atlas/state.json`)
- `src/core/atlas/repository.py` — `AtlasRepository` + `AtlasData`: durable
  state persistence. Writes full domain snapshot on every mutation. Survives
  process restarts. Loads snapshot on service init. No renderer details.
- `src/core/atlas/__init__.py` — public API
- Web endpoints: `/atlas/snapshot`, `/atlas/projects`, `/atlas/work-items`,
  `/atlas/milestones`, `/atlas/decisions`, `/atlas/artifacts`, `/atlas/init`
- Event emission: all mutations emit `atlas.*` events through `EventManager`

**Non-responsibilities:**
- Does NOT import brain, consciousness, expression, dream, or any renderer.
- Does NOT own identity (`data/prompts/soul.md` stays in ProjectSHURA).
- Does NOT own event transport (uses `EventManager` only).
- Persistence is opt-in: `AtlasService` without a `storage_path` runs in-memory
  only (for tests). With `storage_path`, `AtlasRepository` writes the full domain
  snapshot to `data/atlas/state.json` on every mutation. The event journal is a
  separate audit trail owned by `EventManager`.

### 2.3 FORGE (frontend / avatar / workspace layer)

**Purpose:** The workbench / command center / workspace environment — the external
interface of ProjectSHURA for collaboration, observation, task management, agent
coordination, and autonomous work execution.

**Implemented:**

*Backend (Step 2):*
- `src/core/forge/contract.py` — `ForgeState` (semantic, renderer-agnostic state
  object), `ForgePresenceState` enum, `ForgeProjection` (builds `ForgeState` from
  core interfaces; accepts `is_speaking`/`is_sleeping` from the brain, never
  infers them from PresenceRuntime)
- `src/core/forge/__init__.py` — public API
- `brain.get_forge_state()` (`src/core/brain.py`) — **owns** FORGE projection
  construction. Wires EventManager + PresenceRuntime + ATLAS snapshot + dream
  projection + brain flags into `ForgeProjection` and returns `ForgeState.to_dict()`.
  The web layer delegates to this method; it does NOT build the projection inline.
- Web endpoint: `/forge/state` — calls `brain.get_forge_state()`; read-only

*Frontend (Step 3 — first vertical slice):*
- `src/web/frontend/src/context/ForgeContext.jsx` — React context + `useForgeState()`
  hook. Polls `/forge/state` (2s interval) for full semantic state and `/status`
  (500ms interval) for lightweight live signals (`is_speaking`, `is_sleeping`).
  Merges both into a single consumer-facing state object. Read-only.
- `src/web/frontend/src/components/forge/PresentationAdapter.jsx` — **the replaceable
  presentation boundary.** Pure function `mapPresentation(forgeState, options)` that
  maps semantic state → visual presentation props. Supports two modes:
    - `"orb"` (default): CSS/SVG presence indicator. Color = emotion, glow = speaking,
      opacity = sleeping, scale = motion. Extensible to other visual modes.
    - `"3d"`: Placeholder for the SHURA 3D model. Not implemented yet. When the 3D
      model is viable (may require Blender MCP), this mode emits model-ready props
      (modelUrl, expressionHint, poseHint) without changing the adapter interface.
  The adapter imports nothing from the backend. It is pure presentation logic.
- `src/web/frontend/src/components/forge/SHURAPresenceDisplay.jsx` — the visible
  SHURA presence element. Combines orb (from PresentationAdapter), text status line,
  emotion label, and ATLAS project badge. Proves: "SHURA exists visually as a
  persistent presence."
- `src/web/frontend/src/components/forge/ATLASContextPanel.jsx` — compact "current
  work" panel. Active project name + status, active tasks (in_progress + todo),
  current milestone, recent decisions. Answers "What project am I working on?"
- `src/web/frontend/src/components/forge/ActivityFeed.jsx` — event timeline. Recent
  events from `forgeState.activity.recent_events`, color-coded by type, most recent
  first.
- `src/web/frontend/src/pages/ForgePage.jsx` — new route. Composes all above
  components. Includes a chat input that POSTs to `/chat` — proves the complete
  interaction loop: user message → SHURA processes → `is_speaking` flips → Forge orb
  reacts within polling interval → SHURA finishes → Forge shows idle.
- `src/web/frontend/src/App.jsx` + `DashboardLayout.jsx` + `Sidebar.jsx` — wired
  into the existing dashboard navigation. Forge accessible from sidebar "Forge" button.

**Polling architecture:**
- Full state: `/forge/state` every 2000ms
- Light state: `/status` every 500ms (is_speaking, is_sleeping, active_skills)
- Light state overlays full state for faster live signal updates
- Both intervals are configurable via `ForgeProvider` props
- Clean cleanup on unmount

**Contract:** `ForgeState` must NEVER contain:
- PNG paths, OBS scene names, Live2D model indexes, UI coordinates, frontend widget
  IDs, arbitrary CSS state, or renderer-specific animation instructions.

**3D model pathway:**
- The SHURA 3D model (user-owned, may require Blender MCP for further work) is
  supported via `PresentationAdapter` mode `"3d"`. When active and a model URL is
  configured, the adapter emits model-ready props. The current `"orb"` mode is the
  default and requires no external assets.
- The adapter interface is mode-agnostic — adding the 3D renderer does not require
  changes to ForgeContext, SHURAPresenceDisplay, or any backend code.

**Non-responsibilities:**
- Does NOT own SHURA identity (`soul.md` stays in ProjectSHURA).
- Does NOT own core cognition (brain/consciousness loop stays independent).
- Does NOT directly mutate `DreamRun` or `MemoryStorage`.
- Does NOT create a separate event bus (uses `EventManager.subscribe()` + replay).
- Does NOT put renderer details into backend state.

---

## 3. Component Diagram (current)

```
                                    FORGE (frontend / avatar / workspace)
                                    ┌──────────────────────────────────┐
                                    │  /forge/state  → ForgeState      │
                                    │  /atlas/*      → ATLAS CRUD      │
                                    │  /dream/projection → read-only   │
                                    │  /workspace/dream-events         │
                                    └────────┬─────────────────────────┘
                                             │ consumes projection + events
                                             ▼
                         ┌─────────────────────────────────────────────┐
                         │                  ATLAS                      │
                         │  AtlasService (domain service +            │
                         │    optional AtlasRepository persistence)   │
                         │  models: Project, WorkItem, Milestone,    │
                         │          Decision, Artifact, AtlasSnapshot │
                         │  emits: atlas.* events through EventManager│
                         │  persistence: data/atlas/state.json        │
                         └────────┬────────────────────────────────────┘
                                  │ consumes events from core
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         PROJECTSHURA CORE                                 │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐  ┌───────────────────┐  │
│  │ AIVtuber │  │ Conscious-   │  │ Expression │  │  EventManager +   │  │
│  │ Brain    │  │ ness         │  │ (TTS+OBS   │  │  BrainEvent +     │  │
│  │ (comp.   │  │ (single mind │  │  +avatar)  │  │  JSONL journal    │  │
│  │ root)    │  │  loop)       │  │            │  │                   │  │
│  └────┬─────┘  └──────┬───────┘  └─────┬──────┘  └────────┬──────────┘  │
│       │               │                │                   │             │
│       ▼               ▼                ▼                   ▼             │
│  ┌──────────┐  ┌────────────┐  ┌────────────┐  ┌───────────────────┐  │
│  │Perception│  │ Skill      │  │ Presence   │  │  Dream Engine     │  │
│  │Bus       │  │Registry    │  │Runtime +   │  │  (DreamRun,       │  │
│  │(input    │  │+ surfaces  │  │Projection  │  │   DreamSnapshot,  │  │
│  │agg.)     │  │(chat,voice,│  │(semantic   │  │   projection,     │  │
│  │          │  │ minecraft, │  │ state from │  │   consolidation)  │  │
│  │          │  │ dream...)  │  │ events)    │  │                   │  │
│  └──────────┘  └────────────┘  └────────────┘  └───────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  brain.get_forge_state() — owns FORGE projection construction       │  │
│  │  Wires: EventManager + PresenceRuntime + ATLAS snapshot +           │  │
│  │         dream projection + is_speaking/is_sleeping flags            │  │
│  │  Returns: ForgeState.to_dict()  (renderer-free)                    │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      PROVIDER / MODULE LAYER                              │
│  LLM: omniroute | openai | groq | openrouter  (src/modules/llm/)        │
│  TTS: edge | kokoro | orpheus              (src/modules/tts/)            │
│  STT: groq | openrouter                     (src/modules/STT/)           │
│  OBS: websocket                             (src/modules/obs/)           │
│  Interfaces: LLMInterface, TTSInterface, OBSInterface (src/interfaces/) │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Event Architecture

### 4.1 EventManager (`src/core/events.py`)

The single event bus. All state changes, lifecycle events, and observations flow
through `EventManager.publish()`. It owns:
- `BrainEvent` dataclass — canonical event envelope
- `EventJournal` — append-only JSONL persistence (`data/events/events.jsonl`)
- `subscribe()` / `unsubscribe()` — composable filter-based subscriptions
- `replay()` / `filter_events()` — deterministic replay (preserves original IDs)

**Event categories:** `system`, `input`, `output`, `thought`, `skill`, `tool`,
`error`, `memory`, `agent`, `dream`, `embodiment`

### 4.2 Presence events (`src/core/presence/events.py`)

Canonical presence event type names. Emitted by `PresenceRuntime` and adapters.
Subsystem values: `presence`, `expression`, `agent`, `dream`, `shell`, `stt`.

```
presence.connected / presence.disconnected / presence.state.changed
presence.emotion.changed / presence.motion.requested
speech.started / speech.chunk / speech.finished / speech.interrupted
agent.turn.started / agent.turn.completed / agent.turn.failed
tool.started / tool.progress / tool.completed / tool.failed
input.listening.started / input.transcript.partial / input.transcript.final
input.listening.finished
```

**Presence events MUST NOT contain:** PNG filenames, OBS commands, Live2D indices,
provider-specific avatar instructions, UI coordinates.

### 4.3 PresenceRuntime (`src/core/presence/runtime.py`)

Owns semantic Presence state. Emits presence.* events. Knows nothing about PNGs,
OBS, Live2D, VRM, audio devices, or provider-specific renderer APIs.

States: `offline`, `idle`, `listening`, `thinking`, `speaking`, `interrupted`

### 4.4 PresenceProjection (`src/core/presence/projection.py`)

Deterministic translation from canonical events to Presence state. Subscribes to
event types, derives state from lifecycle flags. Never touches renderer APIs.

### 4.5 ATLAS events (`src/core/atlas/models.py` — `AtlasEventType`)

All ATLAS mutations emit `atlas.*` events through the same `EventManager`:

```
atlas.project.created / updated / active_changed / deleted
atlas.work_item.created / updated / transitioned / deleted
atlas.milestone.created / updated / completed
atlas.decision.recorded / updated
atlas.artifact.added / removed
```

Subsystem: `atlas`. Category: `EventCategory.AGENT` (orchestration layer).

---

## 5. Dream Engine

Located in `src/core/dream/`. A backend transaction/subsystem layer. Does not own
event transport, persistence, or UI rendering.

**Domain:** `DreamRun` (lifecycle: created → started → snapshot_created → ...
→ completed / failed), `DreamSnapshot` (durable state observation, no PNG/avatar
references)

**Events:** `dream.started`, `dream.snapshot_created`, `dream.reconciliation_started`,
`dream.reconciliation_completed`, `dream.completed`, `dream.failed`
(subsystem: `dream`, category: `EventCategory.DREAM`)

**Projection:** `DreamStateProjection` + `build_projection()` — read-only. Never
mutates `DreamRun`. Consumes domain objects + event replay.

**Web endpoint:** `/dream/projection` (read-only), `/dream/run` (mutation command),
`/dream/wake`

---

## 6. Dependency Direction

```
identity (data/prompts/soul.md, operating.md)
  ↓
runtime / cognition (brain, consciousness, expression, perception)
  ↓
semantic domain events (EventManager, BrainEvent, EventJournal)
  ↓
projections / state views (PresenceProjection, DreamStateProjection)
  ↓
workspace / orchestration (ATLAS: models, service, events)
  ↓
UI / avatar / desktop presence (FORGE: ForgeState, ForgeProjection, /forge/state)
```

**Critical invariant:** No layer may import a layer above it.
- FORGE must not be imported by ATLAS, dream, presence, events, or core.
- ATLAS must not be imported by dream, presence, events, or core.
- Dream domain must not import projection (projection imports domain).
- Expression must not import consciousness or brain internals.

---

## 7. Identity / Core Separation

**Identity layer (protected):**
- `data/prompts/soul.md` — SHURA's personality, values, aesthetic sensibility
- `data/prompts/operating.md` — behavior rules, anti-sycophancy, intellectual posture
- These files must NOT contain: model provider names, avatar file paths, OBS settings,
  current mood, temporary project names, session IDs.
- Changes require explicit governed review. See `docs/IDENTITY_SYNC.md`.

**Core layer (runtime):**
- `BrainConfig` (`src/core/config.py` → `config.json`) — operational config only.
  Contains provider references, OBS settings, avatar paths — but NOT identity content.

**Separation rule:** Changing providers does not change identity. Changing identity
requires explicit governed review. The identity files contain no provider names.

---

## 8. Provider Abstraction

All backend services are accessed through abstract interfaces:

- `LLMInterface` — `chat()`, `chat_audio()`, `reload_config()`, `generate_json()`
- `TTSInterface` — `speak()`, `generate_audio()`, `reload_config()`
- `OBSInterface` — `connect()`, `disconnect()`, `set_image()`, `set_media()`,
  `type_text()`, `set_text()`

Concrete implementations: `src/modules/llm/` (omniroute, openai, groq, openrouter),
`src/modules/tts/` (edge, kokoro, orpheus), `src/modules/STT/` (groq, openrouter),
`src/modules/obs/` (websocket).

The LLM factory (`src/modules/llm/factory.py`) selects the active provider from
config. Identity is independent of this choice.

---

## 9. Web Layer

`src/web/app.py` — FastAPI application. Global `brain_instance` (singleton). Key
endpoints:

| Endpoint | Purpose | Mutation? |
|---|---|---|
| `/health` | Health check | No |
| `/config` | Get/update brain config | Yes (explicit) |
| `/status` | `is_speaking`, `is_sleeping`, `active_skills` | No |
| `/chat` | Text chat → perception + background output | Yes (via brain) |
| `/audio` | Audio upload → transcript + response | Yes (via brain) |
| `/dream/run` | Trigger dream/consolidation pass | Yes (explicit) |
| `/dream/wake` | Wake consciousness | Yes (explicit) |
| `/dream/projection` | Read-only DreamStateProjection | **No** |
| `/workspace/dream-events` | Dream lifecycle events for workspace | **No** |
| `/forge/state` | Aggregate ForgeState (presence+ATLAS+dream+events) | **No** |
| `/atlas/snapshot` | Read-only ATLAS domain snapshot | **No** |
| `/atlas/projects` | Create/list projects | Yes (explicit) |
| `/atlas/work-items` | Create/list/transition work items | Yes (explicit) |
| `/atlas/milestones` | Create/list/complete milestones | Yes (explicit) |
| `/atlas/decisions` | Record/list decisions | Yes (explicit) |
| `/atlas/artifacts` | Add/list/remove artifacts | Yes (explicit) |
| `/skills` | List skills | No |
| `/skills/{name}/toggle` | Enable/disable skill | Yes (explicit) |
| `/events` | Recent events (in-memory) | No |

**Rule:** Observation endpoints (`/dream/projection`, `/forge/state`, `/atlas/snapshot`,
`/events`, `/workspace/dream-events`) are read-only. Mutation goes through explicit
command endpoints (`/dream/run`, `/atlas/*`, `/skills/{name}/toggle`).

---

## 10. Frontend

`src/web/frontend/` — React 19 + Vite + Tailwind CSS (v4) SPA. Consumes:

- `/forge/state` — full semantic state (polling, 2s interval)
- `/status` — lightweight live signals (polling, 500ms interval)
- `/chat` — text interaction (form submit)
- `/config`, `/sessions`, `/dream/*`, `/atlas/*`, `/skills/*` — existing endpoints

### 10.1 Forge vertical slice (Step 3)

The Forge frontend is the first genuinely usable Forge-facing layer. It is a React
application that proves the complete loop: user interaction → SHURA runtime → state
change → Forge projection → visible response.

**File structure:**
```
src/web/frontend/src/
├── context/
│   └── ForgeContext.jsx          — data layer: polling, state merging, hook
├── components/
│   └── forge/
│       ├── PresentationAdapter.jsx  — semantic → visual mapping (replaceable boundary)
│       ├── SHURAPresenceDisplay.jsx — visible SHURA presence (avatar + status + emotion)
│       ├── ATLASContextPanel.jsx    — compact current-work panel from ATLAS
│       └── ActivityFeed.jsx         — event timeline from ForgeState
└── pages/
    └── ForgePage.jsx              — route: new view in DashboardLayout sidebar
```

**Architecture:**
- `ForgeContext` is the single source of truth for Forge UI state. All components
  consume `useForgeState()`. No component fetches directly.
- `PresentationAdapter` is the only component that knows about visual presentation.
  All other components receive already-mapped props or raw semantic state.
- The chat input in `ForgePage` POSTs to `/chat` — same endpoint as ChatPage.
  This is intentional: the interaction loop is proven through the existing channel.

### 10.2 PresentationAdapter mode system

`PresentationAdapter.mapPresentation(state, { mode, modelUrl })` supports:

| Mode | Description | Status |
|---|---|---|
| `"orb"` | CSS presence indicator: color=emotion, glow=speaking, opacity=sleeping | Default, implemented |
| `"3d"` | Placeholder for SHURA 3D model. Emits modelUrl, expressionHint, poseHint | Not implemented |

The mode system is the abstraction boundary for future avatar implementations.
Switching from orb to 3D (or to Live2D, or to any other renderer) requires changes
only in `PresentationAdapter` and the rendering component — never in ForgeContext
or the backend.

### 10.3 Desktop presence pathway

The long-term goal is for SHURA to sit above or alongside the user's other desktop
applications — a persistent presence, not a chatbot window. The current Forge is a
web page in a browser. The architecture supports the transition via:

1. **PresentationAdapter mode system** — the adapter interface is renderer-agnostic.
   A desktop wrapper (Electron, Tauri, or native) could consume the same `/forge/state`
   endpoint and use a different PresentationAdapter mode for the native surface.

2. **ForgeState is desktop-transportable** — it contains no browser-specific state.
   A desktop client could poll `/forge/state` and render SHURA's presence in a
   transparent, always-on-top window using any renderer that implements the adapter
   interface.

3. **Polling model is transport-agnostic** — the current 2s/500ms polling works in a
   browser. A future desktop client could use the same endpoints, or a future SSE/
   WebSocket transport could replace polling without changing the state model.

4. **No browser lock-in** — ForgeContext and all forge components are plain React.
   They could be embedded in a larger desktop application shell without modification
   to the state model or the adapter interface.

The llm-vtuber product reference (`docs.llmvtuber.com`) informs the UX direction —
transparent background, always-on-top, draggable presence, reacting to speech. The
architecture supports this direction; the implementation is deferred to a later step.
- `/forge/state` — semantic state for the workspace/avatar layer
- `/dream/projection` — Dream state observation
- `/atlas/snapshot`, `/atlas/*` — project/work context
- `/events` — event feed
- `/status`, `/config`, `/skills`, `/dream/run` — control operations

The frontend must never bypass the projection/event layer to reach into brain
internals directly.

---

## 11. Persistence

- **Event journal:** `data/events/events.jsonl` (append-only JSONL, bounded rotation)
- **Memory:** ChromaDB at `data/memory_db/` (durable semantic memory)
- **Session/history:** `data/conversations/` (session JSON files)
- **Self-lore:** `data/memory/self.md`, `data/memory/recent.json`, `data/memory/self_profile.json`
- **Config:** `config.json` (runtime config, NOT identity)
- **ATLAS:** `data/atlas/state.json` — full domain snapshot written by `AtlasRepository`
  on every mutation. Loaded on `AtlasService` init. Survives process restarts.
  Opt-in: `AtlasService` without `storage_path` runs in-memory only (tests).
  The event journal is a separate audit trail; ATLAS domain state is the current
  snapshot, not an event log.

---

## 12. What Belongs Where

| Concern | Belongs in | Why |
|---|---|---|
| SHURA's personality, values, aesthetic | `data/prompts/soul.md` (ProjectSHURA) | Identity is protected |
| Behavior rules, anti-sycophancy | `data/prompts/operating.md` (ProjectSHURA) | Operating behavior |
| Consciousness loop, reasoning | `src/core/consciousness.py` (ProjectSHURA) | Cognition |
| Event emission, journal | `src/core/events.py` (ProjectSHURA) | Event substrate |
| Semantic presence state | `src/core/presence/` (ProjectSHURA) | State, not renderer |
| Dream domain, projection | `src/core/dream/` (ProjectSHURA) | Backend subsystem |
| Provider implementations | `src/modules/` (ProjectSHURA) | Provider-specific code |
| OBS/TTS/avatar rendering | `src/core/expression.py` + `src/modules/obs/` (ProjectSHURA) | Downstream adapter |
| Project registry, work items, decisions | `src/core/atlas/` (ATLAS) | Operational layer |
| ATLAS event emission | `src/core/atlas/service.py` → EventManager (ATLAS) | Uses existing event bus |
| Workspace state, UI state | FORGE (frontend) | Presentation state |
| Avatar rendering state (PNG/Live2D) | FORGE + Expression adapter | Embodiment, not cognition |
| Durable architecture docs, ADRs | `docs/` (ATLAS) | Knowledge layer |
| Session continuity, loop state | `docs/operations/` (ATLAS) | Cross-session context |
| Frontend UI implementation | `src/web/frontend/` (FORGE) | Presentation only |

---

## 13. Roadmap Relationship: M1 → M2

**M1 (current — shura-foundation branch):** Foundation + first Forge vertical slice complete.
- Single consciousness loop, event foundation, presence architecture, dream engine,
  memory consolidation framework, projection layer, skill surfaces, web layer.
- 169 tests passing (164 domain tests + 5 Playwright harness capability tests).
- ATLAS domain + service + repository (JSON persistence to `data/atlas/state.json`)
  + web endpoints implemented. ATLAS initialized at brain startup, not lazily.
- FORGE contract + `brain.get_forge_state()` projection owner + `/forge/state`
  endpoint implemented. `is_speaking`/`is_sleeping` passed from brain, never
  inferred from PresenceRuntime.
- **Forge vertical slice (Step 3):** React frontend with ForgeContext polling,
  PresentationAdapter (orb + 3d placeholder modes), SHURAPresenceDisplay,
  ATLASContextPanel, ActivityFeed, ForgePage route wired into dashboard sidebar.
  Complete interaction loop proven: chat input → /chat → SHURA speaks → Forge orb
  reacts within polling interval.
- All architectural boundaries enforced and tested.

**M2 (next):** ATLAS operationalization + FORGE expansion + desktop presence pathway.
- ATLAS knowledge indexing (cross-session retrieval from docs/).
- ATLAS event consumption (selective intake of project-relevant events from
  broader ProjectSHURA event stream — workspace changes, tool events, dream
  insights — without making ATLAS a universal event sink).
- FORGE expansion: additional workspace surfaces beyond the first vertical slice
  (Overview, Memory, Dream Studio, Agents, Skills, MCP, Artifacts, System).
- FORGE embodiment upgrade: replace orb mode with Live2D/3D renderer when
  SHURA model is viable (may require Blender MCP). PresentationAdapter mode
  system is ready for this transition.
- Desktop presence pathway: transparent, always-on-top Forge mode. PresentationAdapter
  and ForgeState are transport-agnostic and ready for a desktop wrapper.
- Dream Studio full surface (observation + event replay).
- Memory workspace surface (DreamSnapshot fields through projection).

See `docs/tasks/V1_TASK_GRAPH.md` and `docs/tasks/V1_ROADMAP.md` for the full task graph.
