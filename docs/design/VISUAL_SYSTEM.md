# Visual Design System — SHURA V1 (VERIFIED + PROPOSED)

Status: Design specification — must guide all future workspace/command center/front-end implementations. Based on verified identity (`docs/SHURA_VISION.md` references dark/cybernetic/occult aesthetic), verified current avatar/embodiment (`pixel/PNG` system), design target (`SHURA_COMMAND_CENTER_SPEC.md` workspace metaphor), and reference (`tinyhumansai/openhuman` workspace/agent presentation model — REFERENCE, not source of truth).

---

## Design Direction (VERIFIED — derived from identity, specs, reference)

- Black / near-black background (verified: current design direction in `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` and identity aesthetic — dark, strange, cybernetic, occult influence).
- Neon blue primary accent (verified: design direction in identity/reference; must be used sparingly — not generic SaaS neon overload).
- Neon pink / purple secondary accent (verified: design direction; secondary only — not equal to blue; must not dominate).
- Terminal-informed typography and spacing (verified: workspace metaphor is cockpit/command center; terminal-informed design supports readability and technical density).
- Glitch / arcane visual language (verified: identity aesthetic; must not become decorative noise; must serve readability and state observation).
- High contrast for readability (verified: workspace must be readable for long sessions; accessibility/readability is a design constraint, not an aesthetic choice).
- Minimal decorative animation (verified:workspace interaction must remain responsive; heavy animations must not block interaction or event observation).
- SHURA embodiment stage (current PNG/sprite; future Live2D/3D upgrade path — framework must support reference change without workspace restructuring; `docs/design/SHURA_EMBODIMENT.md` contract defines presentation-state mapping).
- Workspace surfaces must observe ProjectSHURA state through projection (`docs/design/ARCHITECTURE_MAP.md`; `docs/design/THREE_SYSTEMS.md`); workspace surfaces do not replace brain/consciousness/event/domain logic.

---

## Color Token System (PROPOSED — framework; exact hex values may be refined but token roles must be preserved)

The token system defines roles, not just colors. Any future workspace/front-end implementation must use these roles; the specific hex values are framework-level and may be refined during implementation.

| Token Role | Current Design Reference (PROPOSED) | Use | Restrictions |
|---|---|---|---|
| Background (primary) | Near-black (`#0a0a12`) | Main workspace background | Must provide sufficient contrast for text; must not use pure black (`#000000`) for readability |
| Background (surface) | Dark gray (`#12121f`) | Workspace panels, navigation surfaces, workspace module backgrounds | Must distinguish from primary background; must not create excessive visual noise |
| Foreground (text, primary) | Light gray / white (`#e8e8f0`) | Primary text content, event feed text, workspace content | Must maintain readability; must not change based on mood (mood affects embodiment stage presentation, not text readability) |
| Foreground (text, muted) | Medium gray (`#8a8a9a`) | Secondary labels, metadata, timestamp references, task status secondary info | Must not become invisible against background surfaces |
| Accent (primary, neon blue) | Bright blue (`#00d0ff` or similar) | Active state indicators, selected navigation items, primary interactive elements, active agent/task indicators, Dream Studio active state | Must be used sparingly; must not dominate workspace; must have sufficient contrast against dark surfaces |
| Accent (secondary, neon pink/purple) | Bright pink / purple (`#ff2a8a` or similar) | Secondary highlights, warning/attention indicators (not error — error uses error token), secondary interactive elements, Dream Studio secondary state (reconciliation/completion stage indicators) | Must not compete with blue; must be clearly subordinate |
| Error / Blocked | Red (`#ff3a3a`) | Error indicators, blocked task states, failed agent/task results, identity divergence warnings, secret exposure indicators, C4 mechanism blocked indicator (separate infrastructure issue — must be visible but must not dominate workspace) | Must be clearly distinguishable from blue/pink; must be used only for actual errors/blockages; not for decorative effect |
| Success / Completed | Green / cyan (`#00ffaa` or similar) | Completed task indicators, verified test results, completed milestone indicators, successful agent execution | Must not dominate workspace; must be visible but not distracting |
| Dream / Mystery / Occult | Deep purple / indigo (`#6600aa` or similar) | Dream Studio state indicators, Dream event lifecycle stages (not error), mysterious/arcane design elements (if used — must not obscure readability) | Must not dominate workspace; must serve state observation; decorative use must be minimal |

---

## Typography (PROPOSED — framework roles; specific font families may be refined during implementation)

- Primary font: A clean, highly legible monospace or sans-serif font for workspace text (verified: terminal-informed workspace design requires readability; monospace supports technical density). Must be available locally (not dependent on remote font loading for offline/offline-first operation).
- Secondary / label font: A distinct but readable font for labels, status indicators, navigation items (must distinguish from primary content without creating visual chaos).
- Typography roles:
  - Workspace content (primary): large, readable, high line-height (must support long reading sessions for task descriptions, event details, architecture references).
  - Navigation (secondary): medium, clear, distinct from content (must allow quick identification of workspace surfaces).
  - Status / metadata (tertiary): small, muted color (`#8a8a9a` token), must remain readable but subordinate.
  - Command input (primary or secondary depending on workspace design): must support rapid typing; must have clear focus state.
- Font loading: Must not block workspace initialization; must have local fallback (workspace must be usable offline; font dependencies must not create blocking conditions).

---

## Spacing / Grid / Layout (PROPOSED — framework; exact measurements refined during implementation)

Based on workspace framework (`docs/design/COMMAND_CENTER_V1.md`) and verified current web layer (`FastAPI` + `React/Vite` skeleton in `src/web/frontend/`):

- Workspace framework uses a responsive grid with persistent navigation (left or top — framework allows either; specific placement deferred to component implementation). The framework must support collapsed navigation (icon-only rail) and expanded navigation (full labels) without restructuring workspace surfaces.
- Workspace surfaces must be modular (panel/card/component-based) so future surfaces (`Memory`, `Agents`, `Dream Studio`, `Projects`) can be added without restructuring layout.
- Main workspace region must support dynamic content (workspace surface, active task, agent observation, event observation, artifact observation) without fixed dimensions that would prevent future workspace expansions.
- Live state region (`Live State / Context`) must remain visible but subordinate — must not dominate workspace; must provide quick status reference (`current_pose`, `current_state_indicator`, `current_text` — derived from `Expression` adapter / projection layer, not arbitrary brain internals).
- Event/activity rail (`Global Event / Activity Rail`) must be persistent (visible at bottom or side — framework allows either; specific placement deferred) but must not block workspace interaction. Must show structured events (not arbitrary message parsing) backed by `EventManager.subscribe()` / replay.
- Workspace surfaces must have defined empty/loading/error/success states (design framework; specific component states deferred to milestone implementation).

---

## Component System (PROPOSED — framework; specific component implementations deferred to milestone-based work)

The workspace framework requires the following component categories (framework roles; specific components implemented incrementally per `docs/tasks/V1_TASK_GRAPH.md`):

- **Workspace Shell Components** (framework): Navigation container, workspace region container, live state region container, event/activity rail container, workspace module container (for future module surfaces), workspace persistence mechanism (framework design — not full database; file-based workspace state mechanism must be added without restructuring framework).
- **Workspace Surface Components** (framework): Workspace surface framework (must support Overview, Workspace, Memory, Dream Studio, Agents, Skills, MCP, Artifacts, Activity surfaces — framework allows future surfaces without restructuring); workspace module framework (modular content regions within workspace surface); workspace interaction framework (command input framework, task interaction framework, agent interaction framework — framework only; specific interaction components deferred).
- **Workspace State Components** (framework): Workspace state observation (derived from `docs/operations/LOOP_STATE.md`, `docs/tasks/V1_TASK_GRAPH.md`, `docs/operations/SESSION_HANDOFF.md` — framework for displaying loop/task/session state, not a separate state database); workspace task display (observed from task framework, not brain internals); workspace agent display (observed from agent/task framework); workspace event display (`EventManager.subscribe()` / replay framework — already verified by tests); workspace Dream display (`DreamStateProjection` framework — verified by `/dream/projection` endpoint and `projection.py` tests).
- **Workspace Interaction Components** (framework): Command input framework (framework for future command palette or direct workspace command input; must route mutation through explicit application interfaces; must not create arbitrary brain mutation); workspace navigation framework (navigation selection framework — selection changes visible surface without brain mutation); workspace task framework (task visibility framework — must observe task/task framework state; must not create arbitrary brain mutation through task interaction).
- **Workspace Persistence Components** (framework): Workspace/project/session reference framework (must persist workspace reference — file-based mechanism must be added without restructuring workspace framework); workspace state persistence framework (must persist workspace state — must not conflict with brain/consciousness state; workspace persistence is presentation/workspace state, not identity/cognition state).
- **Embodiment Components** (verified framework; full Live2D/3D implementation deferred): Embodiment stage framework (`docs/design/SHURA_EMBODIMENT.md` contract — verified design file); embodiment presentation-state adapter (maps `DreamStateProjection` fields + brain/consciousness event states to visual states — framework design verified; full adapter implementation deferred but must follow contract); embodiment reference mechanism (current `avatar_map` / PNG; future Live2D/3D reference mechanism must allow reference change without restructuring workspace framework).
- **Visual Token Components** (framework): Color token framework (verified token roles in this document); typography framework (verified roles); spacing/layout framework (verified framework); animation framework (minimal decorative animation framework; must not block interaction or event observation; must not obscure readability; must be subordinate to workspace content).

---

## Animation / Motion Rules (PROPOSED — must be preserved for accessibility and usability)

- No animation must block workspace interaction. Workspace surfaces must respond immediately to navigation selection, task observation, event updates.
- No animation must obscure event feed or event details. Event feed must remain fully readable at all times.
- Animation must be minimal and purposeful. Heavy decorative animation must not dominate workspace; must serve state observation (e.g., subtle active indicator animation for working state; brief celebration for completed state; error indicator animation for blocked/failed state).
- Embodiment animation (current PNG pose switching; future Live2D/3D animation) must not create a direct mutation path from visual state to brain/consciousness. Visual states must be derived from projection/projection-state mapping; brain/consciousness must not import embodiment components.
- Workspace animations must be testable (if workspace framework includes animation, animation behavior must be observable through projection/state interface, not hidden in visual layer internals).
- Workspace framework must include accessible focus/hover/active states (visible in design framework; must be preserved in component implementation).

---

## Accessibility / Readability Constraints (PROPOSED — must be preserved)

- Workspace surfaces must maintain readability under all workspace conditions (high density, long text, event stream active, agent/task observation active, Dream Studio active).
- Workspace framework must allow collapsed navigation (icon-only rail) and expanded navigation (full labels) without restructuring workspace surfaces.
- Workspace framework must support responsive behavior (framework design must allow responsive component behavior; full responsive implementation deferred but framework must not prevent it).
- Workspace surfaces must define empty/loading/error/success states (design framework verified; component states deferred).
- Workspace event feed must remain readable (structured events, not arbitrary message parsing; structured payload display; no hidden event details that require manual message parsing).
- Workspace framework must support keyboard interaction framework (future command palette, workspace navigation through keyboard — framework allows extension; full keyboard interaction deferred but must not prevent future addition).

---

## Design System Integrity Rules (PROPOSED — must be preserved by all future workspace/component implementations)

1. Workspace surfaces observe ProjectSHURA state through projection/event interfaces (`docs/design/ARCHITECTURE_MAP.md`; `projection.py` verified; `/events` endpoint verified). Workspace surfaces must never import brain/consciousness/skill/domain internals directly for mutation logic.
2. Workspace surfaces observe Dream state through projection (`/dream/projection`). Workspace surfaces must never access `DreamRun` internals directly except through projection interface (`build_projection()` or endpoint response).
3. Workspace surfaces observe agent/task state through task framework (`docs/tasks/V1_TASK_GRAPH.md`; `docs/operations/AUTONOMOUS_LOOP.md`; future agent/task framework — framework only for V1; full framework deferred). Workspace surfaces must never create arbitrary brain/consciousness mutation through agent/task interaction.
4. Workspace surfaces observe memory through projection (`DreamSnapshot` fields from `projection.py`; event replay for memory-related events). Workspace surfaces must not directly access `MemoryStorage` or `MemorySkill` internals for mutation (mutation must use `MemorySkill` interfaces — `docs/design/THREE_SYSTEMS.md`; future full memory workspace surfaces deferred).
5. Workspace framework allows future workspace surfaces (`Memory` full surface, `Agents` full surface, `Projects`, `Artifacts`, `Settings`, future workspace surfaces) without restructuring navigation or workspace model.
6. Workspace framework allows future workspace persistence mechanism (workspace/project/session reference + workspace state persistence) without restructuring workspace surfaces or navigation.
7. Workspace framework allows future embodiment upgrade (`Shura_01` PNG/sprite → `Shura_02` Live2D/3D) without restructuring workspace surfaces or workspace framework (`docs/design/SHURA_EMBODIMENT.md` contract verified; presentation-state mapping framework verified).
8. Workspace framework must preserve event contract (`docs/EVENT_CONTRACT.md`) — no new event taxonomy created independently; any workspace-specific events must use existing taxonomy (new event types must follow taxonomy rules: explicit `event_type`, `subsystem`, structured `payload`, `visibility` set, no secrets, `run_id` consistent).
9. Workspace framework must preserve autonomous loop (`docs/operations/AUTONOMOUS_LOOP.md`) — workspace interaction must not interfere with loop execution; loop state must remain readable by workspace surface (`docs/operations/LOOP_STATE.md` framework); workspace surfaces must not create hidden loop state that conflicts with durable loop state.
10. Workspace framework must preserve harness interoperability (`docs/operations/HARNESS_INTEROPERABILITY.md`) — workspace surfaces must observe harness-independent durable context (`docs/operations/LOOP_STATE.md`, `docs/tasks/V1_TASK_GRAPH.md`, `docs/vision/SHURA_V1_VISION.md`, `docs/design/ARCHITECTURE_MAP.md`) rather than harness-specific transient context.
