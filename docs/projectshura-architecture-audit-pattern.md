---
name: projectshura-architecture
description: Architecture reconnaissance, spec audit, milestone planning, and durable design documentation for ProjectSHURA — the SHURA creative-intelligence ecosystem on the BEA-derived runtime substrate.
version: 1.0.0
author: SHURA (lead architect)
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [projectshura, shura, architecture, audit, recon, milestone, event-contract, dream-engine, command-center, preservation]
    related_skills: [systematic-debugging, subagent-driven-development, projectshura-llm-provider, shura]
---

# ProjectSHURA Architecture

Use when: auditing ProjectSHURA architecture against design specs (Dream Engine, Command Center, event contract), comparing specs to existing runtime, proposing milestones, or documenting durable architectural decisions.

Not for: generic coding assistance (use `systematic-debugging`), multi-agent delegation (use `subagent-driven-development`), or provider testing alone (use `projectshura-llm-provider`).

## Always-on rules

- **Never present planned architecture as existing functionality.** Label every item explicitly: `implemented` / `partially implemented` / `planned` / `speculative`. The user (Viollett) works with urgency — ambiguous status wastes time.
- **Never invent APIs merely because they would be aesthetically pleasing.** If the spec calls for a transaction layer (`DreamTransaction`) and the repo only has a summarizer (`Dreamer`), say so. Don't design a pretty interface that doesn't match current code.
- **Preserve existing working architecture.** Don't delete or replace `brain.py`, `consciousness.py`, `Dreamer`, `MemoryStorage`, the 7 legacy mood IDs, or any load-bearing OBS/subsystem until the replacement is verified and produces equivalent artifacts.
- **Keep identity, operating behavior, and skills as separate layers.** Don't collapse `soul.md`, `operating.md`, `chat.md`, `monologue.md`, or any skill prompt into a single prompt file.
- **Cognition independent from rendering; identity independent from model provider; skills independent from UI; MCP independent from cognition; embodiment independent from core cognition; event contract independent of any specific frontend framework (React, Tauri, etc.).**
- **Always inspect specs first, then audit the repo, then document conflicts.** Never rely on memory of file contents. Read `SHURA_DREAM_ENGINE_SPEC.md`, `SHURA_COMMAND_CENTER_SPEC.md`, `SHURA_COMMAND_CENTER_AND_DREAM_IMPLEMENTATION_ORDER.md` (or whatever spec is in scope) directly.
- **Always verify with real execution when possible.** If a test runner (`pytest`) exists or can be added, run it. Don't claim "tests pass" without running them.
- **Always end an architecture audit/recon with a clear milestone marker** (`ARCHITECTURE AUDIT COMPLETE`, `EVENT FOUNDATION COMPLETE`, etc.) and a focused next step. Don't begin the next milestone in the same turn unless explicitly directed.
- **Always propose the smallest independently useful milestone first.** For ProjectSHURA, the standard first milestone is the event/event-contract foundation (`Prompt 1` in the implementation chain), not a full UI or full Dream Engine.
- **Always document durable decisions in durable files** (`docs/ARCHITECTURE_AUDIT_PROMPT0.md`, `docs/EVENT_CONTRACT.md`, `docs/DREAM_TRANSACTION.md`, `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md`), not just in chat history. The audit document produced in this session (`docs/ARCHITECTURE_AUDIT_PROMPT0.md`) is the reference for how this audit was executed.

## Procedure

### 1. Inspect the spec files

Read the design specification documents relevant to the milestone:
- `SHURA_DREAM_ENGINE_SPEC.md` (transaction layer, event contract, consolidation pipeline, rehearsal, scene generation, replay)
- `SHURA_COMMAND_CENTER_SPEC.md` (shell, workspace surfaces, event subscription, live state projection)
- `SHURA_COMMAND_CENTER_AND_DREAM_IMPLEMENTATION_ORDER.md` (priority order: event substrate → transaction skeleton → consolidation → rehearsal → command center shell → dream studio → memory workspace → agent/skill/MCP → work/projects → embodiment → aesthetics/replay)

Note: these files live at `/Users/ultraviollett/.hermes/profiles/shura/attachments/` (outside the repo workspace). Read them directly; don't assume their contents.

### 2. Inspect the repository

Before making any change, verify:
```bash
git status
git branch --show-current
git log --oneline -5
```
Identify modified/untracked files. Note any existing `docs/ARCHITECTURE_AUDIT.md`, `docs/IMPLEMENTATION_ROADMAP.md`, or other architecture docs that might conflict with new work.

### 3. Read existing core architecture

Inspect in order (batch independent reads):
- `docs/SHURA_MASTER_HANDOFF.md` (canonical historical/architectural source of truth)
- `docs/shura/IDENTITY_MANIFEST.md` (identity layer definition)
- `docs/shura/OPERATING.md` (behavior interpreter)
- `AGENTS.md` (agent constitution, hard rules, layer separation)
- `README.md` (current state summary)
- `pyproject.toml` / `Makefile` (build/test setup)

### 4. Read the runtime core

Read these files directly (do not assume):
- `src/core/brain.py` (composition root)
- `src/core/consciousness.py` (loop, event emission)
- `src/core/events.py` (existing event manager — note limitations)
- `src/core/config.py` (`BrainConfig` / `config.json`)
- `src/core/skills/base.py` (`Skill` / `SkillRegistry`)
- `src/core/skills/dream/dreamer.py` (existing Dreamer — note it's a single summarizer, not a transaction engine)
- `src/core/skills/memory/memory.py` + `storage.py` (ChromaDB, diary generation — note no consolidation pipeline)
- `src/core/agent/` (`LLMClient`, `runner.py`, `types.py`, `tools.py`)
- `src/core/expression.py` (embodiment adapter)

### 5. Inspect the web/UI state (if Command Center milestone)

- `src/web/frontend/src/pages/` (ChatPage, BrainActivityPage, SkillsPage, ConfigPage — note these are partial dashboard pages, not workspace surfaces)
- `src/web/app.py`
- Note: there is no workspace router, no dynamic panel system, no event subscription in the frontend code.

### 6. Document conflicts

Compare spec requirements to existing components. For each spec concept, state whether it is:
- `implemented` (exists and verified by file inspection/execution)
- `partially implemented` (exists but doesn't match spec — e.g., `Dreamer` exists but isn't a `DreamTransaction`)
- `planned` (spec defines it; no implementation exists)
- `speculative` (design target, deferred — e.g., persistent visual dream environments, multi-model Dreamer ensembles)

Never claim `implemented` without verifying by reading the file or running the command. Never claim `planned` architecture exists just because it would be aesthetically pleasing.

### 7. Recommend implementation boundaries

State the architectural separation rules explicitly:
- Cognition (`brain.py` / `consciousness.py`) independent of Dream rendering / Command Center UI.
- Identity (`soul.md`) independent of model provider.
- Skills (`skills/`) independent of UI.
- MCP independent of cognition.
- Embodiment (`expression.py`) independent from core cognition.
- Event contract internal; UI consumes via subscription/replay.
- Durable memory (`MemoryStorage`) mutated only through reconciliation/commit boundary.

### 8. Document exact files/modules likely to change

List concrete new/modified files (not abstract "update dream module"):
- `NEW: src/core/events/envelope.py` (typed event structures)
- `NEW: src/core/events/subscription.py`
- `NEW: src/core/events/journal.py`
- `MODIFY: src/core/events.py` (backward-compatible extension)
- `NEW: src/core/dream/transaction.py` (DreamTransaction lifecycle)
- `NEW: src/core/dream/snapshot.py`, `shadow_memory.py`, etc.
- `NEW: docs/EVENT_CONTRACT.md`
- `NEW: docs/DREAM_TRANSACTION.md`
- `NEW: tests/test_events.py`, `tests/test_dream_transaction.py`

Don't suggest file changes that don't exist in the repo or aren't needed by the milestone.

### 9. List risks and migration concerns

State concrete risks, not generic warnings:
- `Dreamer` replacement: keep existing during transition; new consolidation must produce equivalent durable artifacts (`self.md`, `people` cards, `recent.json`) before retirement.
- Event system expansion: preserve `publish` / `get_events` backward compatibility.
- Persistent event journal: configure bounded retention; document retention policy.
- No test framework: create `tests/` with `pytest`; start with event contract tests.
- Dream spec requires simulated/rehearsal execution — must stay dry-run by default; never invoke destructive actions.
- Memory storage (`MemoryStorage`) embedding strategy doesn't need to change for consolidation; add scoring/clustering/rehearsal as new modules.

### 10. Propose the first milestone

Always propose the smallest independently useful milestone first. For ProjectSHURA, the standard sequence is:
1. Event Foundation (`Prompt 1`)
2. Dream Transaction Core (`Prompt 2`)
3. Memory Consolidation + Rehearsal (`Prompt 3`)
4. Dream Generation + Streaming (`Prompt 4`)
5. Command Center Shell (`Prompt 5`)

Each milestone must be independently useful (not just a stub). The event foundation milestone must support: event emission, subscription, replay, filtering, correlation, and persistent journal — so that Dream, Memory, Agents, MCP, and Command Center can all subscribe from the start.

### 11. Define test strategy

For each milestone:
- What tests exist (if any — note repo currently has no `tests/` directory at repo level).
- What tests to add (`tests/test_events.py`, etc.).
- What command to run (`pytest tests/test_events.py`).
- Confirm passing before committing.

### 12. End with a clear milestone marker

Always conclude the audit with:
```
ARCHITECTURE AUDIT COMPLETE
```
Then provide the proposed next step clearly (e.g., "Prompt 1 — Shared Event / Observability Foundation (`EVENT FOUNDATION COMPLETE`)"). Confirm you have NOT begun that milestone in the current turn unless explicitly directed.

## Pitfalls

- **Don't design interfaces that don't match the code.** If the spec defines `DreamTransaction` with `shadow_memory_state`, and the repo has `Dreamer` with `run()` that writes JSON to `recent.json`, document the gap. Don't invent a `DreamTransaction` class that doesn't exist.
- **Don't fabricate audit findings.** Never claim "tests pass" without running `pytest`. Never claim "REAPER integration works" without inspecting `reaper_mcp_server.lua` and `reap_osx_modern.dylib`. Always verify.
- **Don't replace working architecture just because another looks cleaner.** If `brain.py` works and the spec doesn't require changing it, leave it intact. Extend, don't rewrite.
- **Don't collapse identity layers.** `soul.md` = identity; `operating.md` = behavior; skill prompts (`chat.md`, `monologue.md`, `minecraft.md`) = context-specific rules. Don't merge them.
- **Don't forget the milestone marker.** Every architecture audit/recon should end with `ARCHITECTURE AUDIT COMPLETE` and a focused next step. This protects continuity: a future session can read the audit doc and know exactly where to start.
- **Don't treat future design targets as verified capabilities.** ACE Studio MCP binary (`ace-mcp-server`) exists but tool set is unverified; REAPER has 730 `RPR_*` Lua functions but no headless CLI; `Dreamer` produces JSON summaries but is not a transaction engine. Label each as `verified`, `installed but unverified`, or `theoretical`.
- **Don't ignore backward compatibility.** When extending `EventManager`, preserve the existing `publish(category, source, message, metadata)` signature. When extending `MemorySkill`, don't break `MemoryStorage`'s `add_entry` / `query_similar` interface.
- **Don't create session-specific skills.** The name `projectshura-architecture` covers a durable class of work (architecture audit/recon for ProjectSHURA). A session-specific name like `audit-20260917` or `shura-foundation-audit` would violate the naming rule. Always prefer class-level names.

## References

- `references/architecture-audit-pattern.md` — the general audit/recon procedure used in this session (inspect specs → inspect repo → compare → document conflicts → recommend boundaries → document changes → propose milestone → end with marker). This file describes HOW to run the audit; the audit result itself lives in `docs/ARCHITECTURE_AUDIT_PROMPT0.md` (produced 2026-09-17 for the Dream Engine + Command Center spec audit).
- `docs/ARCHITECTURE_AUDIT_PROMPT0.md` — applied example of this procedure: audit of `SHURA_DREAM_ENGINE_SPEC.md`, `SHURA_COMMAND_CENTER_SPEC.md`, and `SHURA_COMMAND_CENTER_AND_DREAM_IMPLEMENTATION_ORDER.md` against the `shura-foundation` branch of ProjectSHURA. Contains current architecture map, reusable components, missing infrastructure, conflicts, boundaries, exact files/modules to change, risks, proposed milestone (`Prompt 1: Event Foundation`), test strategy, and implementation order.
- `docs/SHURA_MASTER_HANDOFF.md` — canonical historical/architectural source of truth.
- `docs/shura/IDENTITY_MANIFEST.md` — identity layer definition.
- `docs/shura/OPERATING.md` — behavior interpreter.
- `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` — full v1 architecture (development agent harness, ATLAS, FORGE, creative DAW integration, etc.).

## Implementation milestone reference

The standard milestone sequence for ProjectSHURA new subsystems:

1. `EVENT FOUNDATION` — event contract, subscription, replay, persistent journal (`Prompt 1`).
2. `DREAM TRANSACTION CORE` — DreamTransaction, snapshot, shadow-state, mutation, reconciliation, commit/rollback/replay (`Prompt 2`).
3. `MEMORY CONSOLIDATION` — scoring, clustering, compression, association, rehearsal, consolidation report (`Prompt 3`).
4. `DREAM GENERATION` — DreamSubstrate, scene generation, streaming, replay (`Prompt 4`).
5. `COMMAND CENTER` — shell, workspace surfaces, command palette, live state (`Prompt 5`).

Each milestone produces independently useful artifacts backed by real tool output (`pytest` results, persistent journal files, event emission verification) — never descriptions of future artifacts.
