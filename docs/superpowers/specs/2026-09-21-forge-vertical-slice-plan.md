# Forge Vertical Slice — Implementation Plan

**Design doc:** `docs/superpowers/specs/2026-09-21-forge-vertical-slice-design.md`
**Step:** 3
**Branches:** `shura-foundation` (current)

---

## Pre-conditions

- [x] Step 2 complete — 164/164 tests passing
- [x] `/forge/state` endpoint operational (delegates to `brain.get_forge_state()`)
- [x] `/status` endpoint operational (returns `is_speaking`, `is_sleeping`)
- [x] `ForgeState` contract stable and tested
- [x] Frontend stack exists: React 19 + Vite + Tailwind + framer-motion + lucide-react
- [x] Existing pages: ChatPage, BrainActivityPage, SkillsPage, ConfigPage, LandingPage

---

## Step 3.1 — ForgeContext (React context + hook)

**File:** `src/web/frontend/src/context/ForgeContext.jsx` (new)

**What it does:**
- Creates `ForgeContext` + `useForgeState()` hook
- Polls `/forge/state` every 2000ms (configurable) — full semantic state
- Polls `/status` every 500ms — lightweight live signals (`is_speaking`, `is_sleeping`, `active_skills`)
- Merges both into a single state object
- Exposes `isLoading`, `lastUpdated`, `error`
- Provides a `refetch()` function for manual refresh
- Is read-only — never mutates backend state

**State shape exposed to consumers:**
```js
{
  // From /forge/state
  presence: { state, is_connected, emotion, motion, is_speaking, is_sleeping, is_dreaming },
  atlas: { active_project, recent_work_items, active_milestones, recent_decisions },
  dream: { dream_state },
  activity: { recent_events },
  // From /status (overlays /forge/state for live signals)
  is_speaking: boolean,   // from /status, faster update
  is_sleeping: boolean,   // from /status, faster update
  active_skills: string[],
  // UI state
  isLoading: boolean,
  lastUpdated: number | null,
  error: string | null,
  refetch: () => void,
}
```

**Implementation notes:**
- Uses `useState` + `useEffect` + `useCallback`
- Two independent intervals — don't block full-state polling on light-signal polling
- Cleanup intervals on unmount
- Handle 503 (brain not initialized) gracefully — show "runtime offline" state

---

## Step 3.2 — PresentationAdapter (semantic → visual)

**File:** `src/web/frontend/src/components/forge/PresentationAdapter.jsx` (new)

**What it does:**
- Pure function/component that maps semantic presence state → presentation props
- Supports two modes: `"orb"` (CSS/SVG) and `"3d"` (placeholder)
- Mode configurable via prop or context

**`mapPresentation(state, options)` pure function:**
```js
mapPresentation(state, { mode = 'orb', modelUrl = null }) {
  // Returns mode-specific presentation props
  // For "orb" mode:
  return {
    mode: 'orb',
    emotionColor: emotionToColor(state.emotion),     // e.g. 'emerald' for calm
    speakingGlow: state.is_speaking ? 'bright' : 'none',
    sleepingOpacity: state.is_sleeping ? 0.4 : 1.0,
    motionScale: state.motion ? 1.15 : 1.0,
    statusLabel: deriveStatusLabel(state),           // 'speaking', 'listening', etc.
    statusEmoji: deriveStatusEmoji(state),
  };
  // For "3d" mode:
  // Returns { mode: '3d', modelUrl, expressionHint, ... }
  // Placeholder — no renderer yet
}
```

**`emotionToColor(emotion)` mapping:**
- `calm` / `peaceful` → emerald/teal
- `focused` / `thinking` → blue
- `concerned` / `serious` → amber
- `excited` / `energetic` → violet/purple
- `sad` / `melancholy` → indigo/slate
- `default` / `none` → neutral gray

**Key invariant:** This file imports NOTHING from the backend. It is pure presentation logic. No API calls, no state management. Testable as a pure function.

---

## Step 3.3 — SHURAPresenceDisplay (visible presence)

**File:** `src/web/frontend/src/components/forge/SHURAPresenceDisplay.jsx` (new)

**What it does:**
- Renders the visible SHURA presence element
- Uses `PresentationAdapter` (orb mode) for the visual
- Shows text status line
- Shows emotion indicator
- Shows project context badge (from ATLAS, if active project exists)
- Is the element that proves "SHURA exists visually as a persistent presence"

**Layout (compact vertical):**
```
┌─────────────────────────┐
│     [SHURA Orb]         │  ← PresentationAdapter output
│                         │     (color + glow + opacity)
│                         │
│  SHURA                  │  ← Name label
│  ● speaking             │  ← Status with emoji
│  [calm]                 │  ← Emotion label
│                         │
│  📋 ProjectSHURA v1     │  ← ATLAS project badge (if active)
│                         │     or "no project" if none
└─────────────────────────┘
```

**Implementation notes:**
- Orb renders as a CSS circle with `box-shadow` glow (speaking) + `opacity` (sleeping) + `transform: scale()` (motion)
- Status label derives from: `is_speaking` → "speaking", `is_sleeping` → "sleeping", `dream_state.active` → "dreaming", else "idleing"/"connected"
- Emotion shows as a small label under the status
- Project badge shows active project name from `forgeState.atlas.active_project`
- All visual properties derive from `PresentationAdapter.mapPresentation()` — no inline magic numbers

---

## Step 3.4 — ATLASContextPanel (project context)

**File:** `src/web/frontend/src/components/forge/ATLASContextPanel.jsx` (new)

**What it does:**
- Renders compact "current work" panel from ATLAS data
- Shows active project name + status
- Shows current active work items (filtered to `in_progress`)
- Shows current milestone
- Shows recent decisions (last 2)

**Layout:**
```
┌─ Current Work ─────────────────────────┐
│                                         │
│  📋 ProjectSHURA v1                    │  ← active project
│  Status: active                        │
│                                         │
│  Active tasks:                          │
│  • Implement identity layer ... [in_progress] │
│  • Write tests ... [todo]              │
│                                         │
│  Milestone: M1 Foundation [active]     │  ← current milestone
│                                         │
│  Recent decisions:                      │
│  • Provider abstraction ... [finalized] │  ← recent decisions
│  • Persistence approach ... [proposed]  │
│                                         │
└─────────────────────────────────────────┘
```

**Implementation notes:**
- Empty state: "No project active" / "No active tasks" / "No milestones" — graceful, not broken
- Work items sorted by status priority (in_progress first, then todo, then backlog)
- If `active_project` is null, show "No project active" in the header area

---

## Step 3.5 — ActivityFeed (event visibility)

**File:** `src/web/frontend/src/components/forge/ActivityFeed.jsx` (new)

**What it does:**
- Renders recent events from `forgeState.activity.recent_events`
- Shows them as a compact timeline
- Differentiates by event type (speech, tool, dream, presence, system) with subtle color coding
- Limited to last 20 events (matches backend limit)

**Layout:**
```
┌─ Activity ──────────────────────────────┐
│                                         │
│  12:34:01  💬 speech.started           │  ← color-coded by type
│  12:34:00  🤖 tool.executed            │
│  12:33:58  🌙 dream.snapshot           │
│  12:33:55  🔌 presence.connected       │
│  12:33:50  ⚙️ system.config_updated    │
│                                         │
└─────────────────────────────────────────┘
```

**Implementation notes:**
- Event type → icon + color mapping (presentation only, not backend)
- Timestamp formatted as HH:MM:SS from event timestamp
- If no events, show "No recent activity"
- Highlights the most recent event

---

## Step 3.6 — ForgePage (new route)

**File:** `src/web/frontend/src/pages/ForgePage.jsx` (new)

**What it does:**
- Main Forge page — the vertical slice entry point
- Composes: SHURAPresenceDisplay + ATLASContextPanel + ActivityFeed
- Uses `useForgeState()` hook for data
- Shows loading state while first fetch completes
- Handles offline/error state gracefully

**Layout:**
```
┌─ Forge ───────────────────────────────────────────────────┐
│                                                            │
│  ┌──────────────────────┐  ┌───────────────────────────┐  │
│  │                      │  │  Current Work             │  │
│  │   SHURA Presence     │  │  (ATLASContextPanel)      │  │
│  │   (SHURAPresence     │  │                           │  │
│  │    Display)          │  │                           │  │
│  │                      │  │                           │  │
│  └──────────────────────┘  └───────────────────────────┘  │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  Activity Feed (ActivityFeed)                       │ │
│  │                                                      │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  [Compact chat input — optional for first slice]    │ │
│  │  or link to existing ChatPage                       │ │
│  └──────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

**Implementation notes:**
- Uses `react-router-dom` — add `<Route path="forge" element={<ForgePage />} />` to `App.jsx`
- `SHURAPresenceDisplay` takes the left column; `ATLASContextPanel` takes the right
- `ActivityFeed` spans full width below
- Chat input is a simple `<input>` + send button → POST `/chat` → clears input. Proves the interaction loop.

---

## Step 3.7 — Wire into App.jsx

**File:** `src/web/frontend/src/App.jsx` (modify)

**What it does:**
- Adds `<Route path="forge" element={<ForgePage />} />` to the router
- Adds a nav link to the Forge page in the sidebar or header

**Implementation notes:**
- Check existing `App.jsx` routing structure first — match the pattern
- Add a nav entry (likely in `Sidebar.jsx` or a header nav) pointing to `/forge`

---

## Step 3.8 — Tests and verification

**No new backend tests required** — the data contracts are already covered by existing `test_forge.py` and `test_atlas.py`.

**Frontend verification:**
- Build the frontend: `cd src/web/frontend && npm run build` — verify no TypeScript/JSX errors
- Start dev server: `cd src/web/frontend && npm run dev` — open in browser
- Verify: Forge page loads, presence orb responds to state, ATLAS panel shows data, activity feed populates
- Verify interaction loop: send a chat message from Forge page (or ChatPage), watch Forge presence react

**Backend tests (existing, must remain green):**
- `test_forge.py` — 32 tests for ForgeState, ForgeProjection, contract stability
- `test_atlas.py` — 32 tests for ATLAS domain/service
- Full suite: 164/164

---

## Step 3.9 — Update architecture docs

**Files to update:**
- `docs/architecture.md` — add FORGE section describing the new React components, PresentationAdapter, ForgeContext
- `docs/HERMES_HANDOFF_M2.md` — or create a Step 3 handoff note at the end

**What to document:**
- The new frontend file structure under `src/web/frontend/src/components/forge/` and `src/web/frontend/src/context/`
- The PresentationAdapter mode system (orb + 3d placeholder)
- The polling architecture (2s full state + 500ms light signals)
- The interaction loop
- What's still deferred: 3D model renderer, Live2D, desktop overlay, SSE transport

---

## Order of execution

1. Write `ForgeContext.jsx` — the data layer
2. Write `PresentationAdapter.jsx` — the pure presentation mapping
3. Write `SHURAPresenceDisplay.jsx` — the visible element
4. Write `ATLASContextPanel.jsx` — project context
5. Write `ActivityFeed.jsx` — event visibility
6. Write `ForgePage.jsx` — compose everything
7. Update `App.jsx` — add route + nav link
8. Build frontend, fix any errors
9. Run backend tests — confirm still green
10. Update architecture docs
11. Final verification

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Frontend build fails on new JSX files | Write files one at a time, build after each major addition |
| Tailwind classes not applied | Check `tailwind.config.js` content paths include `src/` |
| Polling conflicts with existing state | ForgeContext is isolated — doesn't touch other contexts |
| Chat input in ForgePage duplicates ChatPanel | Keep it minimal — a single input + button, not a full chat UI |
| 3D model mode confused with orb mode | `PresentationAdapter` explicitly branches on `mode` — orb is default, 3d is placeholder |

---

## Definition of Done for this plan

- [ ] All 6 new frontend files written and build-clean
- [ ] `App.jsx` updated with `/forge` route + nav
- [ ] Frontend builds without errors (`npm run build`)
- [ ] Backend full test suite green (164+ tests)
- [ ] Architecture docs updated
- [ ] Forge page visible in browser with: presence display, ATLAS context, activity feed
- [ ] Interaction loop demonstrable (send message → presence reacts)
- [ ] Handoff document updated
