# Frontend — Web Dashboard

← [Web API](api.md) | [Back to README](../../README.md)

---

## Overview

The web dashboard is a React + Vite + Tailwind CSS single-page application. It communicates with the FastAPI backend at `http://localhost:8000`. The dashboard is the primary user interface for interacting with Bea without using the terminal.

---

## File Structure

```
src/web/frontend/
├── index.html
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
├── package.json
└── src/
    ├── main.jsx               React entry point
    ├── App.jsx                Router setup (Landing / Dashboard)
    ├── App.css
    ├── ChatPanel.jsx          Legacy standalone chat+VAD panel (predates the pages/layouts structure; not rendered by the main dashboard)
    ├── ConfigPanel.jsx        Legacy standalone config panel (predates the pages/layouts structure; not rendered by the main dashboard)
    ├── index.css              Global styles + Tailwind directives
    ├── assets/                Static assets (fonts, icons)
    ├── pages/
    │   ├── LandingPage.jsx    Welcome / launch screen
    │   ├── ChatPage.jsx       Conversation interface
    │   ├── ConfigPage.jsx     Configuration editor
    │   ├── SkillsPage.jsx     Skill toggle panel
    │   └── BrainActivityPage.jsx  Real-time event feed
    ├── layouts/
    │   └── DashboardLayout.jsx    Sidebar + content area wrapper
    ├── components/
    │   ├── Sidebar.jsx            Left navigation bar
    │   ├── VoiceVisualizer.jsx    Audio waveform for VAD
    │   ├── config/                Config sub-components
    │   ├── console/               Event feed sub-components
    │   └── ui/                    Reusable UI primitives
    ├── context/
    │   └── DialogContext.jsx      Global modal/dialog state
    ├── hooks/
    │   └── useVAD.js              Web audio Voice Activity Detection
    └── App.css
```

---

## Routes

| Path | Component | Description |
|---|---|---|
| `/` | `LandingPage` | Welcome screen with launch button |
| `/dashboard` | `DashboardLayout` | Main dashboard shell |

The dashboard uses **view state** (not URL sub-routes) to switch between panels, managed in `DashboardLayout`:

| View State | Page | Description |
|---|---|---|
| `chat` | `ChatPage` | Conversation with session management |
| `activity` | `BrainActivityPage` | Brain event log |
| `config` | `ConfigPage` | Settings editor |
| `skills` | `SkillsPage` | Enable/disable skills at runtime |

---

## Pages

### `LandingPage`
Animated welcome screen. Clicking "Launch" navigates to `/dashboard` with a Framer Motion transition.

---

### `ChatPage`
The main chat interface:
- **Chat panel** — message history with mood indicators
- **Voice input** — VAD-based audio recording via `useVAD.js`; audio is sent to `POST /audio`
- **Text input** — standard text field sending to `POST /chat`
- **Interrupt button** — calls `POST /interrupt`
- **Session management** — list, switch, and create sessions via `/sessions`

---

### `BrainActivityPage`
A real-time event console that polls `GET /events` periodically. Events are color-coded by category:

| Category | Color |
|---|---|
| `input` | Blue |
| `output` | Green |
| `thought` | Purple |
| `skill` | Orange |
| `error` | Red |
| `system` | Gray |

---

### `ConfigPage`
A full configuration editor organized into categories (tabs):
- **LLM** — provider selection, model, API keys
- **TTS** — provider, voice, pitch, rate, volume
- **OBS** — source names, connection settings
- **Avatar** — avatar map file paths
- **Text** — typing animation parameters
- **Skills** — per-skill config fields

Changes are sent to `POST /config` and hot-reloaded without restart.

---

### `SkillsPage`
A list of all registered skills with toggle switches. Calls `POST /skills/{name}/toggle?enable=true|false` to enable/disable. Shows each skill's `active` state (running) vs `enabled` (configured to run).

---

## Voice Activity Detection (`useVAD.js`)

The `useVAD` hook uses the Web Audio API to detect when the user starts and stops speaking:

1. `getUserMedia` captures the microphone.
2. An `AudioWorkletProcessor` computes RMS volume continuously.
3. When volume exceeds a threshold → speech start → recording begins.
4. When volume drops below threshold for a hold period → speech end → audio blob sent.

The threshold and hold duration are configurable. The `VoiceVisualizer` component renders a live waveform while VAD is active.

---

## Animations

Pages and view transitions use **Framer Motion**:
- Page enter/exit: `opacity 0→1`, `y 10→0` (200ms ease-out)
- Dashboard mount: `opacity + scale 0.98→1` (300ms ease-out)

---

## Development

```bash
cd src/web/frontend
npm install
npm run dev      # Vite dev server at http://localhost:5173
```

During development, the Vite dev server runs on port 5173 and connects directly to the FastAPI backend on port 8000. The frontend uses full `http://localhost:8000` URLs for API calls (no proxy configured in `vite.config.js`).

## Production Build

```bash
npm run build
```

Output goes to `src/web/frontend/dist/`. The FastAPI server automatically serves this folder when `--web` is used.
