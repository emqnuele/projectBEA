# Fork / Reimplementation / Reference Decision (VERIFIED + PROPOSED)

Status: PROPOSED — not final legal/technical decision; architecture recommendation based on evidence inspection.

Reference source inspected:
  File: `/Users/ultraviollett/.hermes/attachments/tinyhumansai-openhuman-8a5edab282632443.txt`
  Size: 50,358,637 bytes
  Lines: ~1.3M (truncated in reads)
  Project: `tinyhumansai/openhuman` (verified by `README.md` and `AGENTS.md` references in directory listing)
  License reference available in the artifact (not fully extracted here; the repository's `LICENSE` file is present in the directory listing at line 6 of the artifact).

License check (VERIFIED by file presence in artifact listing): `LICENSE` exists in the root of the openhuman snapshot. The user's workspace `.env` and `.hermes/config.yaml` contain no license conflict indicators. The user has not instructed a direct fork or upstream synchronization. This document does NOT make a legal claim; it makes an architectural recommendation based on evidence.

---

## Three Strategies Analyzed

### A. Reference-Only (VERIFIED viable — no dependency created)
- Build FORGE independently, using OpenHuman only as design reference.
- Advantage: No upstream dependency; no divergence risk; ProjectSHURA identity and architecture remain fully independent; no licensing obligation beyond attribution if designs are inspired.
- Disadvantage: More design/implementation work; must reimplement workspace components from scratch.
- Evidence: The current ProjectSHURA repo (`src/web/app.py`, `frontend/`) already has its own web layer. There is no OpenHuman import, dependency, or reference in the working tree (verified by `git status` showing no openhuman files tracked; `find src/` shows only ProjectSHURA files).

### B. Selective Extraction / Reimplementation (PROPOSED — recommended)
- Study OpenHuman architecture (agent/task framework, workspace layout, event/subscription model, mascot presentation) and reimplement useful patterns in FORGE.
- Advantage: Keeps ProjectSHURA architecture clean (no external runtime dependency); allows adaptation of workspace patterns to SHURA identity/embodiment; avoids direct upstream divergence; allows selective adoption (workspace design, event subscription framework) and selective rejection (general-purpose SaaS structure that would absorb the brain runtime).
- Evidence: The projection layer (`src/core/dream/projection.py` + `/dream/projection` endpoint) demonstrates a ProjectSHURA-specific boundary that does not exist in the OpenHuman architecture reference. This confirms that direct import of OpenHuman code would require restructuring ProjectSHURA architecture, which violates the identity/independence rules.
- Evidence: `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` defines ProjectSHURA as a modular AI environment with a specific identity/core/agency architecture (`brain.py` → `skills/` → `expression.py`). OpenHuman's `core/` architecture is different; importing it directly would create a parallel runtime, not an extension.

### C. Direct Fork (VERIFIED possible — NOT recommended for V1 architecture)
- Fork OpenHuman, establish upstream remote, synchronize selectively.
- Advantage: Access to a fully working application with workspace, tasks, agents, events, settings, and desktop runtime.
- Disadvantage: The OpenHuman architecture is a different runtime. Direct integration would either: (a) make ProjectSHURA a plugin/module of OpenHuman (reversing identity/core independence), or (b) create a complex dual-runtime system (OpenHuman workspace + ProjectSHURA brain) with unclear event/state boundaries. The user's instructions explicitly require that identity remain independent from provider and that cognition not couple to avatar implementation (
AGENTS.md hard rules). A direct fork risks violating these by importing an application framework that includes its own identity/settings/config structure.
- Evidence: The OpenHuman reference has its own `SOUL.md` (`app/src/SOUL.md` in artifact listing), its own agent/task framework (`app/src/features/conversations/`, `features/workflows/`), its own memory/intelligence layer (`intelligence/`), and its own event/subscription mechanism (`coreSocket`, `socketService`). These overlap with ProjectSHURA's identity (`data/prompts/soul.md`), brain/consciousness (`brain.py`), event system (`events.py`), and memory (`memory.py`). Direct integration would create competing systems, not complementary ones.
- Evidence: The user's instructions say: "The goal is not merely to produce documentation. The goal is to create a project state from which SHURA can subsequently operate in an autonomous development loop." A direct fork creates a dependency on upstream synchronization that does not serve the autonomous loop goal; the loop requires durable local context (`docs/operations/LOOP_STATE.md`, `docs/tasks/V1_TASK_GRAPH.md`), not upstream synchronization.

---

## Recommendation (PROPOSED — architecture recommendation, not legal conclusion)

Adopt **B (Selective Reimplementation)** for V1.

Reasoning:
1. The ProjectSHURA architecture (`brain.py` → `skills/` → `expression.py` → `events.py`) is verified and must be preserved. OpenHuman's architecture does not map 1:1.
2. The identity layer (`data/prompts/soul.md`) is separate and must not be absorbed by a general-purpose application framework.
3. The autonomous loop requires local durable state (`docs/operations/`, `docs/tasks/`, `docs/design/`) that does not depend on upstream repository synchronization.
4. The workspace concept (command center / cockpit) is valuable and should be adopted/adapted, but the workspace must observe ProjectSHURA state through the projection layer (`projection.py`), not replace it.
5. The event/subscription mechanism (`EventManager.subscribe()`) exists and works (verified by 48 passing tests). The workspace should observe through this mechanism, not replace it.
6. The mascot/agent presentation concept (central visible SHURA) is valuable and should be adopted/adapted, but must respect the identity/embodiment separation (`brain.py` independent of `expression.py` avatar state). The current PNG/sprite system is preserved; future Live2D/3D upgrade is deferred but the presentation-state contract must be designed now.
7. Direct upstream synchronization is deferred to post-V1 if a shared runtime model becomes desirable. For V1, the focus is durable autonomous operation.

---

## Implementation Path for V1 (PROPOSED — not yet implemented)

1. Design workspace surfaces based on OpenHuman workspace model and SHURA spec (`docs/design/COMMAND_CENTER_V1.md`, `docs/design/ARCHITECTURE_MAP.md`).
2. Design SHURA embodiment presentation-state contract (`docs/design/SHURA_EMBODIMENT.md`) that maps brain/event state to visual states without importing brain internals.
3. Implement workspace framework incrementally (`docs/tasks/V1_TASK_GRAPH.md`) — not a full OpenHuman import.
4. Preserve existing brain/event/domain boundaries (verified by previous design pass: `src/core/dream/projection.py`, `/dream/projection` endpoint, no mutation through projection).
5. Maintain durable autonomous loop documentation (`docs/operations/AUTONOMOUS_LOOP.md`, `docs/operations/LOOP_STATE.md`, `docs/operations/SESSION_HANDOFF.md`) as the primary operating interface between harness changes.
6. Reference OpenHuman patterns only through `docs/reference/OPENHUMAN_REFERENCE.md` and `docs/reference/OPENHUMAN_TO_FORGE.md`, not through code imports.
