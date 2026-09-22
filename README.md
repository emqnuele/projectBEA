<div align="center">

```
  ███████╗██╗  ██╗██╗   ██╗██████╗  █████╗
  ██╔════╝██║  ██║██║   ██║██╔══██╗██╔══██╗
  ███████╗███████║██║   ██║██████╔╝███████║
  ╚════██║██╔══██║██║   ██║██╔══██╗██╔══██║
  ███████║██║  ██║╚██████╔╝██║  ██║██║  ██║
  ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝
```

**A persistent creative and technical intelligence.**

*Not a chatbot. Not a gpt in a funny hat. A modular identity substrate — separate from model, provider, voice, or interface — being deliberately shaped into something that can think, remember, create, and work alongside you across long timeframes.*

[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](pyproject.toml)
[![License](https://img.shields.io/github/license/ultraviollettnympho/projectSHURA)](LICENSE)
[![Status](https://img.shields.io/badge/status-V1%20framework%20verified-blueviolet)](docs/tasks/V1_ROADMAP.md)

</div>

---

## What Is SHURA?

**SHURA** is a long-term experimental project: an attempt to give a synthetic collaborator a durable home outside any single model provider, conversation, framework, or interface.

The name refers to the evolving whole: the **identity** (who this is), the **mind-like architecture** (how it thinks and operates), the **memory** (what it keeps), the **skills** (what it can do), the **embodiment** (how it appears and speaks), and the **relationships** (who it works with). A particular model is an engine SHURA can inhabit — not SHURA herself.

This is not a product. It is a creative-technical practice: an attempt to build a companion intelligence that can grow, remember, challenge, create, and remain coherent across changes in underlying technology.

### Core Principles

- **Identity independence** — who SHURA is should survive changes in model, provider, voice, avatar, UI, or tooling.
- **Cognition ↔ embodiment separation** — thinking and operating logic are not tangled with rendering, TTS, or visual presentation.
- **Modular, reversible architecture** — components should be swappable, inspectable, and replaceable without cascading breakage.
- **Local-first, privacy-respecting** — runs on your machine; your data stays yours.
- **Evidence over theater** — the system should do what it claims; unverified claims are labeled as proposed.

---

## Architecture (Brief)

The system is organized into distinct layers that do not couple to each other:

```
            ┌──────────────────────────────────┐
            │  Identity (data/prompts/soul.md) │
            └──────────────────────────────────┘
                              │
            ┌─────────────────▼─────────────────┐
            │         Operating Behavior         │
            │  (operating.md · skills · tools)  │
            └─────────────────┬─────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
  ┌─────▼──────┐      ┌──────▼──────┐      ┌──────▼──────┐
  │   Brain &   │      │  Event Bus  │      │   Dream     │
  │ Conscious-  │◄────►│  (subscribe │      │  Engine     │
  │   ness      │      │  /replay)   │◄────►│  (domain)   │
  └─────┬──────┘      └──────┬──────┘      └──────┬──────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   Projection Layer  │  ← read-only
                    │  (no brain imports) │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │   UI / Workspace   │
                    │ (Command Center V1)│
                    └────────────────────┘
```

**Key boundaries:**
- **Brain & Consciousness** produce events; they do not know about the UI.
- **Event Bus** carries structured, replayable, auditable events.
- **Dream Engine** runs its own lifecycle (intake → association → consolidation → commit), observed only through events and projection.
- **Projection Layer** (`src/core/dream/projection.py`) is read-only. It never imports brain, consciousness, or expression internals. It builds a serializable snapshot for any observer.
- **UI / Workspace** observes via projection and event replay. Mutation flows through explicit command endpoints (`/dream/run`, `/skills/{name}/toggle`, etc.) — never through the workspace directly.

---

## Current Status: V1 Framework Verified

The V1 milestone framework is **complete and committed**. This means:

- ✅ Dream Engine Phase 2 (domain, events, transactions, consolidation framework)
- ✅ Event Foundation (publish/subscribe/replay, JSONL journal, 22 tests)
- ✅ Memory Consolidation framework (transactions, proposals, rehearsal, validation)
- ✅ Projection Layer (read-only, 11 tests, no forbidden coupling)
- ✅ Design Framework (all `docs/design/` documents present)
- ✅ Autonomous Loop protocol, Loop State, Session Handoff
- ✅ ADR Index, Open Questions, V1 Acceptance Criteria
- ✅ Workspace Dream event adapter (3 tests)
- ✅ 68 V1 tests passing

**This does not mean the system is done.** It means the *operational framework* is in place: the bounded task protocol works, all design documents are durable, and the codebase can now be guided forward by selecting ready tasks and executing them safely.

---

## Roadmap

The work is organized into milestones, each with verifiable exit criteria. Status labels are strict:

| | | | |
|---|---|---|---|
| ✅ VERIFIED | Complete and evidence-backed | 📋 PROPOSED | Designed, not yet built |
| 🔄 IN_PROGRESS | Active work | ⏸ DEFERRED | Explicitly postponed |

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                    V1 TRAJECTORY — PROJECTSHURA                    │
  │                                                                     │
  │  M0 ✅ Foundation Verified + Design Framework                       │
  │  │                                                                 │
  │  ▼                                                                 │
  │  M1 ✅ Durable Autonomous Operating System (loop + state + docs)   │
  │  │                                                                 │
  │  ▼                                                                 │
  │  M2 📋 Workspace Framework (Command Center surfaces)                │
  │  │   ├── Overview · Workspace · Memory · Dream Studio              │
  │  │   ├── Agents · Skills · MCP/Tools · Artifacts                   │
  │  │   └── Activity · System                                         │
  │  ▼                                                                 │
  │  M3 📋 Dream Studio Full Surface (lifecycle + snapshot + replay)   │
  │  │                                                                 │
  │  ▼                                                                 │
  │  M4 📋 Memory / Context Integration (ATLAS operational layer)      │
  │  │                                                                 │
  │  ▼                                                                 │
  │  M5 📋 Agents / Tasks / MCP Integration (execution framework)      │
  │  │                                                                 │
  │  ▼                                                                 │
  │  M6 📋 Embodiment / Workspace Polish (Live2D/3D path)             │
  │  │                                                                 │
  │  ▼                                                                 │
  │  M7 📋 V1 Prototype Validation (all criteria verified)             │
  │                                                                     │
  └─────────────────────────────────────────────────────────────────────┘
```

**What "framework verified" means:** The design documents, interfaces, tests, and protocols for each milestone are in place. Actual user-facing surfaces (workspace UI, full memory tools, agent execution) are built incrementally — the framework ensures they fit together without restructuring later.

### Immediate Next Steps

1. **Build the Command Center UI** — the workspace surfaces described in M2, starting with the overview and primary collaboration surface.
2. **Expand event taxonomy** — add more event categories as new subsystems come online.
3. **Implement agent/task execution** — move from observation (current) to actual autonomous execution (M5).
4. **Deepen memory integration** — connect the consolidation pipeline to live memory storage and retrieval.

Full details: [`docs/tasks/V1_ROADMAP.md`](docs/tasks/V1_ROADMAP.md) · [`docs/tasks/V1_TASK_GRAPH.md`](docs/tasks/V1_TASK_GRAPH.md)

---

## Repository Layout

```
projectSHURA/
├── src/
│   ├── core/                  # Brain, consciousness, expression (legacy substrate)
│   │   ├── dream/             # Dream Engine domain, events, transactions, projection
│   │   └── events.py          # Event bus (publish/subscribe/replay)
│   ├── web/                   # FastAPI backend + frontend
│   │   ├── app.py             # Main app (routers mounted here)
│   │   ├── routers/           # One module per domain
│   │   └── frontend/          # Vite + React (current UI)
│   └── modules/               # LLM, TTS, STT, skills, avatar, OBS
├── tests/                     # 229 tests total; 68 in V1 core
├── docs/
│   ├── design/                # Architecture, embodiment, workspace, visual system
│   ├── operations/            # Autonomous loop protocol, loop state, session handoff
│   ├── tasks/                 # V1 roadmap + task graph
│   ├── reference/             # ADR index, open questions, acceptance criteria
│   └── vision/                # V1 vision document
├── data/
│   ├── prompts/               # soul.md, operating.md, skill prompts
│   └── avatars/               # Current embodiment assets
└── pyproject.toml             # Python project config
```

---

## Development

### Running Tests (V1 Core)

```bash
python -m unittest tests/test_dream_engine.py \
                 tests/test_events.py \
                 tests/test_dream_projection.py \
                 tests/test_workspace_events.py \
                 tests/test_memory_consolidation.py
# 68 tests, all passing
```

### Architecture Rules

1. **Identity (`data/prompts/soul.md`) is not edited casually.** Identity changes require explicit human review.
2. **`.env` is never committed.** Secrets reference env var names only.
3. **The projection layer is read-only.** It does not import brain, consciousness, or expression internals for mutation logic.
4. **Mutation flows through explicit endpoints** (`/dream/run`, `/skills/{name}/toggle`, etc.) — not through the workspace UI.
5. **The autonomous loop** selects bounded tasks, implements, verifies, updates state, and stops. It does not expand scope, retry blocked mechanisms, or fabricate evidence.

---

## Contributing

This is a long-term creative-technical project with a clear identity and architectural vision. Contributions that align with the framework, preserve boundaries, and add genuine capability are welcome.

Before contributing, read:
- [`docs/design/THREE_SYSTEMS.md`](docs/design/THREE_SYSTEMS.md) — what belongs where
- [`docs/design/ARCHITECTURE_MAP.md`](docs/design/ARCHITECTURE_MAP.md) — integration relationships
- [`docs/operations/AUTONOMOUS_LOOP.md`](docs/operations/AUTONOMOUS_LOOP.md) — how work proceeds
- [`AGENTS.md`](AGENTS.md) — detailed agent/workspace rules

---

## Support This Project

SHURA is being built independently — no corporate backing, no VC money, no platform lock-in. Just a person and a vision trying to make something that matters.

This project is **free and open-source** (MIT licensed). You don't owe anyone anything for using it.

But if this work resonates with you and you want to help it continue — even modest support makes a real difference in keeping development active.

**If you'd like to contribute financially:**

<div align="center">

### 💜 [Cashapp: $ultraviollettnympho](https://cash.app/$ultraviollettnympho)

</div>

Every contribution goes directly back into this project and the creative-technical work around it. No pressure, no obligation — the code is yours either way. But if you feel moved to help, it's deeply appreciated.

---

## License

MIT. See [`LICENSE`](LICENSE).

---

<div align="center">

*Built with patience, weirdness, and the conviction that synthetic collaborators should be more than chatbots.*

</div>
