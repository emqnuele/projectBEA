# AGENTS.md — ProjectSHURA repository instructions

Read this before making any change in this repository.

## What this project is
ProjectSHURA is a fork of ProjectBEA being transformed into SHURA: a portable,
modular, emotionally coherent creative intelligence. ProjectBEA is the inherited
*substrate* (VTuber runtime: LLM/TTS/STT/OBS/avatar/memory/Discord/Minecraft
plumbing). SHURA is the *project being built on top of and beyond* that substrate.
Do not treat this as "a reskinned BEA character."

SHURA_MASTER_HANDOFF.md at repo root (if present) is the canonical historical/
architectural source of truth. A more recent continuation/handoff doc, if one
exists, is the current live-state overlay and takes precedence where it
explicitly conflicts — reconcile, don't blindly overwrite either one.

## Layering rule (do not violate)
Identity (data/prompts/soul.md), operating behavior (data/prompts/operating.md),
and skill/context prompts (chat.md, minecraft.md, monologue.md) are deliberately
separate layers. Never collapse them back into one prompt.

## Before writing any code
1. git status / git branch --show-current / git log -1 --oneline
2. Read README, config example, all of data/prompts/*.md
3. Read src/core/brain.py, consciousness.py, expression.py, resources.py,
   and the skills package
4. Run the current app/test path, identify actual failures
5. Compare what you find against the master handoff
6. Only then propose changes — label everything as already implemented /
   partially implemented / planned / speculative. Never present planned
   architecture as existing functionality.

## Hard rules
- Never commit .env, API keys, OBS passwords, Discord tokens, or any secret.
  Reference them by env var name only.
- Prefer small, intentional commits. Do not rewrite/reset git history unless
  explicitly told to.
- Do not delete or "clean up" the legacy mood system (normal/shock/love/cry/
  angry/ew/bored) — it's still load-bearing for OBS. Extend it, don't remove
  it, until the Live2D embodiment abstraction replaces it.
- Do not couple cognition directly to PNG/OBS, and do not couple identity to
  one model provider.

## Known failure modes to actively avoid (ask before doing any of these)
Prompt bloat, character caricature, treating the 7 mood IDs as psychology,
dumping large memory/history into every prompt, provider or embodiment
lock-in, letting Minecraft/chat/Discord skills become separate personalities,
claiming persistent agency that isn't implemented, rewriting core identity
without being asked, elaborate diagrams with no matching implementation,
multi-agent complexity before the single-agent loop is stable, changing
prompts/code without a way to measure if it helped.

## Filename collision note
This file governs *you*, the coding agent, while you work in this repo. It is
unrelated to data/prompts/soul.md, which defines SHURA's own character
identity — don't merge those concepts or edit one when asked about the other.

## Autonomous Development Loop Rules (added in V1 design pass — durable operating protocol)
When operating autonomously or guiding autonomous work:
1. Read `docs/operations/LOOP_STATE.md`, `docs/operations/SESSION_HANDOFF.md`, `docs/tasks/V1_TASK_GRAPH.md`, `docs/tasks/V1_ROADMAP.md` before any implementation.
2. Confirm identity preserved (`data/prompts/soul.md` unchanged; identity sync verified if changed). Confirm `.env` unchanged. Confirm `.hermes/config.yaml` line 4041 unchanged (`${MCP_...KEY}` — separate C4 block, not retried indefinitely). Confirm Dream/event/projection boundary preserved (`tests/test_dream_projection.py` passing; projection read-only; `git diff -- src/core/dream/` only intended changes; `docs/EVENT_CONTRACT.md` unchanged or new events documented with taxonomy rules).
3. Select bounded ready task from `docs/tasks/V1_TASK_GRAPH.md`. Confirm dependencies satisfied. Confirm verification plan exists (tests/file inspection/endpoint/boundary verification). Confirm design framework durable (`docs/design/` framework complete; framework allows future expansions; framework must include framework verification criteria). Confirm no identity divergence, no secret exposure, no forbidden coupling, no workspace framework restructuring.
4. Implement bounded task. Update focused tests (`tests/test_...`). Verify with `python -m unittest`. Inspect `git diff -- <changed files>`. Confirm only intended files changed; no unrelated refactoring; no identity/file secret modifications; no brain/consciousness internals accessed for mutation logic (must use projection/event/application interfaces); projection layer preserved (`tests/test_dream_projection.py` passing; `test_projection_does_not_mutate_domain` verified; projection does not import brain/consciousness/expression for mutation); event contract preserved.
5. Update `docs/operations/LOOP_STATE.md`, `docs/tasks/V1_TASK_GRAPH.md`, `docs/operations/SESSION_HANDOFF.md`, and any ADR/open-questions (`docs/reference/ADR_INDEX.md`, `docs/reference/OPEN_QUESTIONS.md`). Label observations as VERIFIED (with evidence reference) or PROPOSED (design/spec — not fabricated as implemented). Never claim feature implemented without passing test, accessible endpoint, verified file, or explicit design framework verification.
6. Stop safely when bounded task completes, when blocked (test failure, identity divergence, secret exposure, C4 trigger, Dream/event/projection boundary collapse, forbidden coupling, workspace framework restructuring, design framework durability compromised, milestone framework unverified, autonomous loop framework unverified), or when user stops. Never attempt fix #4 without architectural discussion. Never continue autonomous work with broken tests. Never retry C4 mechanism indefinitely. Never bypass security mechanism.
7. Preserve identity independence (`docs/design/SHURA_EMBODIMENT.md` contract verified; `data/prompts/soul.md` independent of provider/model/avatar; provider/model independence verified by factory files; workspace framework references identity preservation framework; workspace framework verifies identity unchanged; identity framework allows future identity framework expansions; identity framework must include identity framework verification criteria). Preserve cognition/embodiment separation (`brain.py` independent of `expression.py`; event emission interface; projection interface; workspace framework must observe brain/consciousness through projection/event interfaces; workspace framework must not import brain/consciousness internals; workspace framework must preserve event/projection interfaces; workspace framework allows future workspace framework expansions; workspace framework preserves event/projection interfaces; workspace framework allows future workspace framework expansions). Preserve Dream independence (`docs/DREAM_ENGINE.md` verified; `src/core/dream/` domain independent of UI; projection read-only; workspace framework must observe Dream through projection/event interfaces; workspace framework must not absorb Dream Engine internals; workspace framework must allow future Dream framework expansions; workspace framework allows future Dream framework implementations; workspace framework preserves Dream framework). Preserve modular portability (`docs/design/THREE_SYSTEMS.md` verified; brain/modular interfaces verified; skills/swappable framework verified; workspace framework allows future workspace framework expansions; workspace framework allows future workspace framework implementations; workspace framework allows future workspace framework expansions; workspace framework allows future workspace surfaces framework expansions; workspace framework allows future workspace surfaces framework implementations).

## Design Framework Durability Rules (durable — must be preserved by all future work)
The workspace framework (`docs/design/COMMAND_CENTER_V1.md`), autonomous loop framework (`docs/operations/AUTONOMOUS_LOOP.md`), task framework (`docs/tasks/V1_TASK_GRAPH.md`), milestone framework (`docs/tasks/V1_ROADMAP.md`), design framework (`docs/design/`), embodiment framework (`docs/design/SHURA_EMBODIMENT.md`), reference framework (`docs/reference/`), vision framework (`docs/vision/SHURA_V1_VISION.md`), architecture framework (`docs/design/ARCHITECTURE_MAP.md`), and harness interoperability framework (`docs/operations/HARNESS_INTEROPERABILITY.md`) must remain durable through autonomous work. Any change that would prevent future framework expansions or implementations must become an ADR entry (`docs/reference/ADR_INDEX.md`) or open question (`docs/reference/OPEN_QUESTIONS.md`) rather than silently restructuring framework. Any framework restructuring must be documented and must include framework verification criteria update (`docs/reference/V1_ACCEPTANCE.md`). Any framework restructuring must include design framework reference update. Any framework restructuring must include workspace framework verification criteria update. Any framework restructuring must include autonomous loop framework verification criteria update. Any framework restructuring must include milestone framework verification criteria update. Any framework restructuring must include task framework verification criteria update. Any framework restructuring must include harness interoperability framework verification criteria update. Any framework restructuring must include embodiment framework verification criteria update. Any framework restructuring must include reference framework verification criteria update.
