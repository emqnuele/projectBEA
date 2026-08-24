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
    │   ├── StreamPlanPage.jsx Today's objectives for the stream
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
| `plan` | `StreamPlanPage` | The owner's objectives for this stream |
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

### `StreamPlanPage`
Where the owner writes what Bea has to get done today: a headline directive and
an ordered list of objectives. Reads and writes `/plan`, and re-reads it every
five seconds — Bea closes objectives herself while the stream runs, so the page
has to follow her.

---

### `BrainActivityPage`
A live event console. It subscribes to `GET /events/stream` (server-sent events)
through the `useEvents` hook, falling back to a one-off `GET /events` fetch when
the stream cannot be opened. Events are colour-coded by category:

Each line gets a four-letter tag:

| Tag | When | Colour |
|---|---|---|
| `INPT` | category `input` | blue |
| `OUTP` | category `output` | emerald |
| `THGT` | category `thought` — what she thought without saying | purple |
| `EXEC` | category `skill` | amber |
| `ERR ` | category `error` | rose |
| `COST` | source `cost` — calls, tokens and ms for that turn | amber |
| `WAKE` / `NOTE` / `SKIP` | source `attention` — the gate's verdict, with its score and reason | indigo / grey |
| `INFO` | anything else | zinc |

`WAKE`/`NOTE`/`SKIP` and `COST` are the two things worth watching while tuning:
one shows what got through the gate and why, the other what it cost.

The page also carries the sleep/wake control (`POST /dream/run`,
`POST /dream/wake`).

---

### `ConfigPage`
A configuration editor split into the categories listed in the sidebar: Model,
Speech to Text, Voice, Stream (OBS), Typing, Avatar, General, Minecraft and
Discord.

Changes go to `POST /config` and are hot-reloaded. Secrets come back from
`GET /config` masked as `********`; posting the mask back is ignored, so editing
an unrelated field cannot overwrite a real token.

---

### `SkillsPage`
Every toggleable skill with a switch, its per-skill config fields, and its live
state: `enabled` (configured to run) against `active` (actually running). The
toggle calls `POST /skills/{name}/toggle?enable=true|false`, which arms or
disarms the capability in the running brain.

It also hosts the Minecraft console, a direct WebSocket view of the mod.

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

The dev server runs on port 5173 and calls the backend directly — there is no
proxy in `vite.config.js`. Every request goes through `API_BASE`
(`src/web/frontend/src/api.js`), which resolves to `http://localhost:8000` in dev and to the
page's own origin in a build. Set `VITE_API_BASE` to point it elsewhere.

Port 5173 is already in the backend's CORS allowlist; any other origin needs
`BEA_ALLOWED_ORIGINS` on the brain.

## Production Build

```bash
npm run build
```

Output goes to `src/web/frontend/dist/`. The FastAPI server automatically serves this folder when `--web` is used.
