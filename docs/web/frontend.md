# Frontend — the control room

← [Web API](api.md) | [Back to README](../../README.md)

---

## Overview

A React + Vite + Tailwind v4 single-page app, served by the brain from its own
origin. It is the control room for one always-on consciousness: what she is
doing right now, what she chose to care about, what she remembers, and what
today is for.

Design decisions worth knowing before changing anything:

- **Dark by default.** It runs at night, next to OBS. Light is a real second
  theme, not an afterthought.
- **Black and white, plus one hue.** Everything is neutral except a single
  accent, chosen by the operator in Settings › Appearance (`--accent-raw`,
  blue by default). It is reserved for one meaning: she is awake, speaking or
  acting. Nothing decorative may use it.
- **The event colours are a ladder, not a rainbow.** `--flux-out`, `--flux-think`,
  `--flux-act` and `--flux-in` are all derived from the accent by mixing toward
  the neutral text colour, so importance reads as saturation and the badge
  beside them carries the kind. Red is the one exception, because failure has to
  be unmistakable.
- **One connection.** `BrainProvider` opens a single `EventSource` and polls the
  two snapshot endpoints in one place. Pages never fetch status themselves.
- **Nothing fails quietly.** Every request goes through `api.js`, which turns a
  failure into an `ApiError` that reaches a toast or an inline error.

---

## File structure

```
src/web/frontend/
├── index.html                  fonts, theme colour, pre-paint theme restore
├── vite.config.js
├── postcss.config.js           Tailwind v4 runs through @tailwindcss/postcss
├── eslint.config.js
└── src/
    ├── main.jsx                providers, glass filters, backdrop, router
    ├── App.jsx                 routes
    ├── api.js                  fetch wrapper + every endpoint, one place
    ├── index.css               tokens, themes, the liquid-glass material
    ├── lib/
    │   ├── cn.js               class joiner + the event-colour map (FLUX)
    │   ├── format.js           relative time, compact numbers, durations
    │   └── nav.js              navigation and settings sections
    ├── state/
    │   ├── BrainProvider.jsx   the single SSE + status/overview + controls
    │   ├── AppearanceProvider  theme and the liquid-glass parameters
    │   ├── ToastProvider.jsx   non-blocking feedback
    │   └── DialogProvider.jsx  confirmations only
    ├── layouts/
    │   └── AppShell.jsx        sidebar + status bar + outlet + ⌘K
    ├── components/
    │   ├── glass/              Glass surface + the SVG refraction filters
    │   ├── atmosphere/         the ordered-dither backdrop
    │   ├── motion/             CountUp, SplitText, Magnetic, Spotlight, rings
    │   ├── ui/                 controls, fields, feedback, Modal
    │   ├── console/            the Minecraft cockpit
    │   ├── AttentionFlux.jsx   the attention gate, live
    │   ├── Sidebar.jsx
    │   ├── TopBar.jsx          presence + global controls, on every page
    │   └── CommandPalette.jsx
    ├── pages/
    │   ├── BootPage.jsx        the way in: health check, then it opens itself
    │   ├── HomePage.jsx        the bento overview
    │   ├── ChatPage.jsx
    │   ├── PlanPage.jsx
    │   ├── ActivityPage.jsx
    │   ├── MemoryPage.jsx
    │   ├── SkillsPage.jsx
    │   ├── SettingsPage.jsx
    │   └── settings/           one component per settings section
    └── hooks/
        └── useVAD.js           voice activity detection
```

---

## Routes

| Path | Screen |
|---|---|
| `/` | Boot screen — probes the brain, then enters on its own |
| `/dashboard` | Overview (bento) |
| `/dashboard/chat` | The private line to her |
| `/dashboard/plan` | Today's orders and objectives |
| `/dashboard/activity` | Attention gate and the event stream |
| `/dashboard/memory` | People, roster, recall, her self-lore |
| `/dashboard/skills` | Abilities on and off |
| `/dashboard/settings/:section` | `mind · engine · voice · hearing · stream · channels · world · appearance` |

Every screen is a real URL: refreshing keeps you where you were, and the back
button works.

---

## Liquid glass

Blur alone reads as frosted plastic. What makes a surface glass is that the
backdrop *bends* behind it.

- `GlassFilters` renders two SVG filters once, at the root. `feTurbulence`
  generates the irregularity of a liquid surface and `feDisplacementMap` pushes
  the backdrop's pixels along it.
- `.glass::before` carries the frost, `.glass::after` carries the refraction.
  They are separate layers on purpose: a browser without SVG-in-`backdrop-filter`
  drops only the refraction, instead of invalidating the whole declaration.
- The CSS mask on `::after` keeps the warp at the rim, where a real lens is
  thickest. That falloff is the **splay** control.
- `#lg-disperse` runs the same displacement three times at different strengths,
  one per colour channel, and screens them back together — which is why the edge
  fringes into colour, exactly as a real lens does.
- `Glass quiet` drops the SVG cost for the many small tiles and keeps the frost
  and the rim light, so they still read as the same material.

All of it is adjustable in **Settings › Appearance** (light, refraction, depth,
dispersion, frost, splay, colour lift) and persisted in `localStorage`, with a
single switch to turn refraction off entirely on a slow machine.

The ground underneath is `DitherField`: a slow two-tone field quantised with an
8×8 Bayer matrix, drawn at a fifth of the screen resolution and scaled up with
`image-rendering: pixelated`. Glass needs something behind it worth bending.

---

## Motion

`framer-motion` throughout, plus small primitives in `components/motion`.
`prefers-reduced-motion` is honoured globally in `index.css` and checked again
inside `CountUp`, `Magnetic` and `DitherField`, which would otherwise keep
animating through it.

---

## Development

```bash
cd src/web/frontend
npm install
npm run dev      # vite on :5173, talking to the brain on :8000
npm run build    # emits dist/, which the FastAPI app serves
npm run lint
```

`VITE_API_BASE` overrides the API origin. In production the dashboard is served
from the same origin as the API, so the base is empty.
