# ATLAS — SHURA Interoperability Skeleton
Status: INITIAL DRAFT (created 2026-09-13, bounded Step C, SHURA full activation)
Canonical authority reference: `Downloads/shura-hermes-handoff/projectSHURA/AGENTS.md` (3043 bytes, 64 lines — newer/broader) per user approval; divergence with repo `AGENTS.md` (2974 bytes, 56 lines) preserved and documented in `docs/MIGRATION_AUDIT_20260913.md` verification log.

## Purpose (scope-bound)
Define the minimal interface contract between ProjectSHURA (identity + runtime) and ATLAS (`ATLAS.project` canonical repo, commit 5a9d14a) without collapsing the two into a single architecture. This is a skeleton — not a full specification — so future bounded steps can extend it without rewriting identity.

## Layers preserved (per AGENTS.md + SOUL.md identity rules)
1. Identity: `~/.hermes/SOUL.md` (runtime) / `Downloads/hermes-global/SOUL.md` (global identity — 110 lines, shorter/conceptual; preserved as 3-layer model per SHURA_IDENTITY_SYNC.md) / repo `docs/shura/SOUL.md` (mirror — byte-identical to runtime at audit time: md5 6aabb046958ddedaf0bd62b14ad6fe18).
2. Operating behavior: `docs/shura/OPERATING.md` / `Downloads/shared/SHURA_OPERATING_PROTOCOL.md` (2156 bytes, 55 lines — found; not yet propagated into repo); closest repo equivalent `data/prompts/operating.md`. Not superseded by this skeleton.
3. Agent/project context: Downloads `projectSHURA/AGENTS.md` (authority for this skeleton); repo `AGENTS.md` (live contract — divergence preserved).
4. Memory: `Downloads/shared/SHURA_MEMORY_PROTOCOL.md` (1954 bytes, 78 lines) defines tier 1 (conversation) / tier 2 (Hermes memory) / tier 3 (project docs) / tier 4 (ATLAS knowledge) — referenced here, not duplicated.

## Interoperability interface (initial, bounded)
- ATLAS reads from SHURA (conceptual direction): identity kernel reference (SOUL.md path), operating rules reference (OPERATING.md path), current project state reference (repo root / `.hermes.md` when present), agent role definitions (`.shura/agents/` — architect/builder/release-gate per MASTER HANDOFF §18).
- SHURA reads from ATLAS (future bounded step — not implemented): knowledge retrieval interface (document parsing / citation / provenance) and durable architecture/decision records. Not built today; spelled out here as interface placeholder so next bounded step doesn't invent an unverified capability.
- No shared database schema defined yet. No live MCP adapter built yet (Majik MCP auth mismatch noted in audit — fix in separate bounded step; REAPER adapter design target only; ACE binary executable but unverified live).

## Canonical location rule (per SHURA_MASTER_CONTEXT.md §4)
ATLAS.project (`docs/`) holds conceptual architecture; ProjectSHURA (`docs/`) holds implementation-facing architecture; `.hermes/skills/shura/` holds routing behavior. This skeleton lives in `projectSHURA/docs/` as an interoperability contract — it should point to, not duplicate, ATLAS content.

## Constraints preserved (non-negotiable per AGENTS.md)
- Legacy mood IDs (`normal`, `shock`, `love`, `cry`, `angry`, `ew`, `bored`) remain load-bearing for OBS/PNG embodiment — not collapsed by this skeleton.
- Identity not coupled to one provider/model.
- No automatic bidirectional sync that silently overwrites identity (SHURA_IDENTITY_SYNC.md divergence protocol preserved).
- Secret keys never included; `.env` masked (not shown, not changed in audit log).

## Verification state at creation
- Audit verification log appended (`docs/MIGRATION_AUDIT_20260913.md` — verification block present; file size changed from pre-C size; exact delta: append occurs; evidence in file).
- `.hermes/config.yaml` interpolation inspection (C3) — read-only; no edit applied yet; result shown in verification log (interpolation variable mismatch noted; fix deferred to next bounded step per user direction).
- `Downloads/shura-hermes-handoff/` package intact (11 files; 6 folder-level copies); `hermes-global/SOUL.md` preserved (not overwritten onto runtime); `shared/` protocol files preserved.
- No destructive change to repo identity files (`data/prompts/soul.md`, `docs/shura/`); no `.env` modification; no `git` history rewrite; no skill removal; no live Majik claim.

## Next bounded steps (not executed — listed for design continuity)
- C3 (next): read `.hermes/config.yaml` interpolation reference; show proposed alignment; apply only with fresh user authorization; verify with `grep`.
- C4 (next): create or extend `docs/SHURA_MEMORY_PROTOCOL.md` / `docs/SHURA_RED_TEAM_PROTOCOL.md` links in repo ( Downloads `shared/` versions preserved; propagation path defined).
- Later bounded steps (separate approvals): ATLAS.project `AGENTS.md` reconciliation (currently empty — 8 bytes); FORGE.project `AGENTS.md` reconciliation (empty); `docs/ATLAS_INTEROPERABILITY.md` extension (not full architecture rewrite); `.crush/` status decision (preserve/integrate/archive — documented, not decided yet).

## Anti-patterns actively avoided (per SHURA_MASTER_CONTEXT.md §17 + SKILL.md audit notes)
- No single giant prompt combining identity + architecture + operating rules.
- No identity file containing shell commands/ports.
- No automatic bidirectional identity sync.
- No architecture cosplay (this skeleton points to verified files; it doesn't invent unimplemented interfaces as existing).
- No claim that Majik/ACE/REAPER integration is complete (verified: Majik MCP auth broken; ACE binary executable but GUI unverified; REAPER script-only, no adapter).
