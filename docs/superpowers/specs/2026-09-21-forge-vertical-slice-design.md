# Forge Vertical Slice — Design Doc

**Date:** 2026-09-21
**Step:** 3 — First usable Forge-facing vertical slice
**Status:** Approved

---

## 1. Goal

Prove that the running ProjectSHURA system can expose SHURA's semantic presence through a real user-facing Forge experience — not just a backend dashboard.

The slice must demonstrate simultaneously:
1. SHURA exists visually as a persistent presence.
2. Forge can display semantic SHURA state.
3. Forge can display relevant ATLAS/project context.
4. Forge can react to presence/event state.
5. The visual layer remains an adapter (replaceable).
6. The backend remains authoritative.

---

## 2. Architecture (existing + new)

```
SHURA identity (data/prompts/soul.md)
    ↓
cognition / runtime (brain, consciousness, expression, skills)
    ↓
EventManager (semantic events, JSONL journal)
    ↓
PresenceRuntime + Dream Engine
    ↓
ATLAS (domain + service + persistence)
    ↓
ForgeProjection (builds ForgeState from core interfaces)
    ↓
brain.get_forge_state() — owns projection construction
    ↓
FORGE (new in this step)
    ├── ForgeContext (React) — polls /forge/state, owns live state
    ├── PresentationAdapter (React) — semantic state → visual presentation
    │     modes: "orb" (CSS/SVG), "3d" (placeholder for SHURA model)
    ├── SHURAPresenceDisplay (React) — the visible vertical slice
    ├── ATLASContextPanel (React) — compact project/work context
    └── EventReactivity (React) — responds to state changes
    ↓
future: desktop overlay, Live2D, always-on-top
```

**Dependency rule (preserved):** Backend is authoritative. Frontend is an adapter. No renderer details in `ForgeState`, `PresenceRuntime`, ATLAS events, or brain state.

---

## 3. Components

### 3.1 Backend changes (minimal)

**No new backend modules required.** The existing `/forge/state` endpoint (delegates to `brain.get_forge_state()`) and `/status` endpoint (returns `is_speaking`, `is_sleeping`, `active_skills`) are sufficient.

If a transport upgrade is needed later (SSE, WebSocket), it can be added without changing this slice's architecture.

### 3.2 ForgeContext (React) — `src/web/frontend/src/context/ForgeContext.jsx`

A React context + hook that:
- Polls `/forge/state` at a configurable interval (default 2s) — full semantic state
- Polls `/status` at a faster interval (default 500ms) — lightweight live signals (`is_speaking`, `is_sleeping`)
- Merges the two into a single `useForgeState()` hook return
- Exposes `isLoading`, `lastUpdated`, `error` for UI feedback
- Is read-only — never mutates backend state

```
forgeState = {
  presence: { state, is_connected, emotion, motion, is_speaking, is_sleeping, is_dreaming },
  atlas: { active_project, recent_work_items, active_milestones, recent_decisions },
  dream: { dream_state },
  activity: { recent_events },
  runtime: { is_speaking, is_sleeping },
}
```

### 3.3 PresentationAdapter (React) — `src/web/frontend/src/components/forge/PresentationAdapter.jsx`

The replaceable boundary between semantic state and visual presentation.

**Interface (conceptual):**
```jsx
// Input: forge presence state (semantic, renderer-free)
// Output: presentation instructions (mode-specific)
const presentation = PresentationAdapter.map(state, { mode: "orb" });
// → { emotion_color, is_speaking_glow, is_sleeping_opacity, motion_intensity, ... }
```

**Modes:**
- `"orb"` — CSS/SVG presence indicator. Color tracks emotion, glow tracks speaking,
  opacity tracks sleeping, size/intensity tracks motion. Extensible.
- `"3d"` — reserved for the SHURA 3D model. When `mode: "3d"` is active and a model
  URL is configured, the adapter emits model-ready props (position, rotation, expression
  hint). Implementation deferred until the 3D model is viable (may require Blender MCP).

The adapter never imports Live2D, Three.js, or any renderer directly. It emits abstract
presentation props. The actual rendering component interprets them.

### 3.4 SHURAPresenceDisplay (React) — `src/web/frontend/src/components/forge/SHURAPresenceDisplay.jsx`

The visible vertical slice. Combines:
- **Avatar area:** PresentationAdapter output (orb mode initially) + optional 3D model slot
- **Presence state:** text status line (connected, speaking, listening, idleing, sleeping, dreaming)
- **Emotion indicator:** emoji or label from `emotion` field
- **Project context badge:** active project name from ATLAS (or "no project")

This is the element that proves "SHURA exists visually as a persistent presence."

### 3.5 ATLASContextPanel (React) — `src/web/frontend/src/components/forge/ATLASContextPanel.jsx`

Compact "current work" panel. Shows:
- Active project name + status badge
- Current active work items (from `recent_work_items`, filtered to `in_progress`)
- Current milestone (from `active_milestones`, first one)
- Recent decisions (last 2, from `recent_decisions`)

This answers: "What project am I working on?" and "What's happening right now?"

Not a full project browser — that's a later step.

### 3.6 ForgePage (React) — `src/web/frontend/src/pages/ForgePage.jsx`

New route `/forge`. Layout:
```
┌─────────────────────────────────────────────────────┐
│  Forge Page                                        │
│                                                     │
│  ┌──────────────┐  ┌────────────────────────────┐ │
│  │ SHURA        │  │  Current Work (ATLAS)      │ │
│  │ Presence     │  │  - Active project          │ │
│  │ Display      │  │  - Active work items       │ │
│  │              │  │  - Current milestone       │ │
│  │ [avatar]     │  │  - Recent decisions        │ │
│  │ [status]     │  │                            │ │
│  │ [emotion]    │  │                            │ │
│  └──────────────┘  └────────────────────────────┘ │
│                                                     │
│  ┌──────────────────────────────────────────────┐ │
│  │  Activity Feed (recent events)               │ │
│  │  - event 1                                   │ │
│  │  - event 2                                   │ │
│  │  ...                                         │ │
│  └──────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 3.7 Interaction loop

**Loop:** ForgePage includes a compact chat input (or links to the existing ChatPage).
User types a message → POST `/chat` → SHURA processes → `is_speaking` becomes true →
ForgeContext polls → SHURAPresenceDisplay shows "speaking" state →
SHURA finishes → `is_speaking` false → Forge shows "idleing".

The chat input in ForgePage is optional for the first slice — the loop can also be
demonstrated by using the existing ChatPage alongside ForgePage open. The key proof
is: **state changes in the backend are visible in Forge within polling interval.**

---

## 4. What this slice does NOT do

- Does NOT implement a 3D model renderer (mode "3d" is a placeholder)
- Does NOT implement Live2D integration
- Does NOT implement desktop overlay / always-on-top
- Does NOT build a full ATLAS project browser
- Does NOT add new backend endpoints (reuses `/forge/state` + `/status`)
- Does NOT put renderer details into backend state
- Does NOT make the frontend the source of truth for any state

---

## 5. File additions (frontend only)

```
src/web/frontend/src/context/ForgeContext.jsx         — React context + hook
src/web/frontend/src/components/forge/PresentationAdapter.jsx — adapter
src/web/frontend/src/components/forge/SHURAPresenceDisplay.jsx — presence display
src/web/frontend/src/components/forge/ATLASContextPanel.jsx — ATLAS context
src/web/frontend/src/pages/ForgePage.jsx              — new route
src/web/frontend/src/App.jsx                          — add /forge route
```

No backend files added. No changes to `forge/contract.py`, `brain.py`, `app.py`.

---

## 6. Testing approach

Test the React components conceptually through:
- Manual verification in browser (the visual slice is hard to unit-test meaningfully)
- Backend contract stability: existing tests for `ForgeState`, `ForgeProjection`, `brain.get_forge_state()` already cover the data layer
- Contract stability: `/forge/state` endpoint tests (existing `test_forge.py`) cover the API

The React components are viewed as the adapter/UI layer — their correctness is proven by the loop working in the browser, not by unit tests.

---

## 7. 3D model pathway (deferred)

The user has a SHURA 3D model render. Incorporation plan:

1. Complete the CSS/SVG orb slice first (this step).
2. User works on the 3D model (may use Blender MCP — check available tools).
3. When the model is viable (file format, size, rigging?), add a `"3d"` mode to
   `PresentationAdapter` that loads and displays the model.
4. The adapter interface stays identical — only the rendering implementation changes.

The adapter's mode system is designed for exactly this transition.
