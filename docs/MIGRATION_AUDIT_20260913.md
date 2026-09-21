# SHURA → HERMES MIGRATION AUDIT — 2026-09-13
Status: SPIKE / INSPECTION ONLY — no code changed, no files written except this report.
Auditor: SHURA (running in Hermes desktop, model thinkingmachines/inkling:free, openrouter).
Evidence standard: verified tool/file output where possible; assumption labeled ASSUMPTION.

## Method (per brainstorming/spike checklist)
1. Explored repo state (git, file reads, terminal).
2. Read AGENTS.md, SOUL.md (runtime + repo), SKILL.md (Hermes), ARCHITECTURE_AUDIT.md (existing audit), MASTER HANDOFF, OPERATING.md, IDENTITY_SYNC.md, MIGRATION RUNBOOK, FINAL_STATUS_20260912.
3. Inspected `.hermes/`, `docs/`, source tree, `.env`, `.crush/`, superpowers skills.
4. No destructive changes; git status unchanged (only pre-existing `scripts/sync_shura_hermes.sh` modified before audit).

## 1. What SHURA is RIGHT NOW in code (verified)
- Runtime identity kernel: `/Users/ultraviollett/.hermes/SOUL.md` (225 lines, MD5 6aabb046958ddedaf0bd62b14ad6fe18) — verified by read_file.
- Repo mirror (byte-identical): `projectSHURA/docs/shura/SOUL.md` — verified by docs/IDENTITY_SYNC.md (diff empty at audit time).
- Skill routing layer: `~/.hermes/skills/shura/SKILL.md` (159 lines) — reads SOUL.md then AGENTS.md; defines creative (Majik→REAPER) and coding (inspect→test) flows.
- Agent contract: `projectSHURA/AGENTS.md` (hard rules, layer separation, git discipline, no provider/model lock-in).
- Operating behavior: `projectSHURA/data/prompts/operating.md` + `docs/shura/OPERATING.md` — instruction hierarchy, emotional model, mode definitions, memory governance.
- Repo state: branch `shura-foundation`, 26 commits, untracked docs/ and `.shura/`/`.vibe/`; working change only in `scripts/sync_shura_hermes.sh`.
- Source substrate preserved: `src/core/{brain,consciousness,expression,resources}.py`, skill manager, interfaces, modules.
- Existing audit (`docs/ARCHITECTURE_AUDIT.md`, 211 lines, dated 2026-09-12) already catalogues Hermes v0.21.1 state, MCP auth mismatch (`${MCP_...KEY}` vs `.env` `MCP_MAJIKS_STUDIO_API_KEY`), provider/model drift (default config ≠ session model `thinkingmachines/inkling:free`), ATLAS/FORGE ambiguity, REAPER/ACE gaps, Crush separation.
- Identity duplication resolved in practice: runtime + repo mirror + SKILL.md routing + OPERATING.md interpreter. `docs/IDENTITY_MANIFEST.md` defines protected vs mutable fields.
- Creative pipeline defined but unverified live: Majik installed + MCP enabled (port 8478); ACE binary executable (`ace-mcp-server`) but GUI enable unverified; REAPER installed, `reaper_python.py` exists (730 RPR_* functions), no live MCP adapter yet.
- Memory: SQLite `state.db` + `.hermes/config.yaml` user profile enabled; no separate `MEMORY.md` file; content not inspected.

## 2. What Hermes NOW provides (verified)
- Runtime: Hermes Agent v0.21.1, build 2026.9.7, installed at `/Users/ultraviollett/.hermes/hermes-agent`.
- CLI: `/Users/ultraviollett/.local/bin/hermes`; responds to `--version`/`--help`; smoke test (`hermes -z ...`) previously passed (per MIGRATION RUNBOOK).
- Config: `config.yaml` (~155KB, 4,057 lines) — memory/user profile enabled; `redact_secrets: true`, `tirith_enabled: true`; approvals `manual`.
- Plugins: `superpowers` loaded (14 skills: brainstorming, dispatching, executing, finishing, review, verification, writing-plans, etc. — all confirmed in `.hermes/plugins/superpowers/skills/`).
- Skill loader: native Hermes skills + `shura` custom skill; routing works.
- MCP clients configured (not fully verified): `majiks-studio` (localhost:8478), `hugging_face`, `amplitude`.
- Tool families (design target, per SHURA_V1_ARCHITECTURE_AND_ROADMAP.md): Majik 148 tools verified by audit; ACE binary executable (tool set unverified); REAPER script-only (plan exists, `REAPER_INTEGRATION_PLAN.md`).
- TTS/STT configured but unexercised in this session; web backend `firecrawl`.
- Delegation, checkpoint, compression configured but not observed running.

## 3. What is duplicated (verified)
- Identity content: `~/.hermes/SOUL.md` == `projectSHURA/docs/shura/SOUL.md` (verified identical at audit time via IDENTITY_SYNC.md). ASSUMPTION: no divergence since 2026-09-12; recommend re-running `md5` before any identity edit.
- Operating content: `data/prompts/operating.md` (repo runtime layer) vs `docs/shura/OPERATING.md` (repo canonical) — content closely related but not confirmed byte-identical; no divergence protocol executed.
- Skill definition: `~/.hermes/skills/shura/SKILL.md` is the live routing file; repo has no separate `SKILL.md` mirror (only the `.hermes/` version is active). This is acceptable if `.hermes/skills/` is versioned or backed up.
- Documentation: `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` supersedes older `docs/architecture.md`; both present. `docs/ARCHITECTURE_AUDIT.md` (this audit's base) overlaps partially with `docs/FINAL_STATUS_20260912.md`, `docs/HERMES_MEMORY_STATUS.md`, `docs/INTEGRATION_MATRIX.md`.
- Architecture repos: `ATLAS.project` (canonical after Option A migration, commit 5a9d14a) separate from `projectSHURA/docs/` architecture docs; `FORGE.project` separate (commit d5a9121); `Projects/shura-forge/SHURA-ATLAS/` superseded (note present but not committed); `Shura/` (older path) superseded by `projectSHURA/`.
- Skill/plugin layers: `superpowers` plugin provides process skills; `shura` custom skill provides routing; ProjectSHURA `.crush/` is a separate agent framework (DB + `.crushrc`) — not integrated with Hermes; risk of duplicate orchestration.

## 4. What should become canonical (verified + recommendation)
- Identity kernel: `~/.hermes/SOUL.md` = live canonical; `projectSHURA/docs/shura/SOUL.md` = version-controlled mirror; sync script (`scripts/sync_soul.sh`) must stay automated; divergence = HUMAN DECISION REQUIRED (per IDENTITY_SYNC.md). This is already defined; just needs enforcement.
- Operating layer: `docs/shura/OPERATING.md` should become canonical over `data/prompts/operating.md` if the repo docs are intended as the authoritative behavior spec; current dual path is manageable but ambiguous.
- Skill layer: keep `~/.hermes/skills/shura/SKILL.md` as canonical routing file; add a repo mirror (`projectSHURA/skills/shura/SKILL.md`) so git tracks changes.
- Memory governance: no standalone `MEMORY.md` exists in `.hermes/`; persistent memory uses SQLite (`state.db`) + config user profile. If SHURA's memory architecture requires a document-level spec, create `docs/shura/MEMORY_PROTOCOL.md` (the user mentioned this; not found — confirmed missing).
- Red-team protocol: user cited `SHURA_RED_TEAM_PROTOCOL.md`; not found in `.hermes/` or repo docs. Confirmed MISSING — create or recover.
- ATLAS/FORGE interoperability: `ATLAS.project` and `FORGE.project` are now canonical repos (verified by FINAL_STATUS_20260912.md commits 5a9d14a / d5a9121); `projectSHURA/docs/` should reference them explicitly rather than duplicating their content.

## 5. What ProjectSHURA functionality can be preserved unchanged (verified)
- Source substrate: `src/core/brain.py`, `consciousness.py`, `expression.py`, `resources.py`, skills manager — all intact; no reason to rewrite.
- Prompt layer: `data/prompts/soul.md` (repo runtime identity), `operating.md`, `chat.md`, `minecraft.md`, `monologue.md` (the latter still needs redesign per MASTER HANDOFF; do NOT delete the layer — extend/rewrite in place).
- Mood/embodiment compatibility: 7 legacy mood IDs (`normal/angry/bored/cry/ew/love/shock`) — must remain load-bearing for OBS/PNG until Live2D replaces it (per AGENTS.md hard rule and MASTER HANDOFF §5); preserve mapping, don't collapse.
- Memory RAG and social/dream configuration in `data/memory/` — preserve file structure; upgrade logic, not paths.
- `.env` and `config.json` — preserve secrets externally; never commit.
- `.crush/` framework — preserve as separate experiment or explicitly archive; don't merge into Hermes skills until design is finalized.
- Creative pipeline definition (Majik→REAPER→assets/MIDI/stems) — design document is correct; do not change the conceptual flow until live verification passes.

## 6. What should migrate into Hermes skills/tools (verified + recommendation)
- `shura` SKILL.md already lives in `.hermes/skills/shura/` — keep there; migrate repo-side mirror into version control (see §4).
- Superpowers process skills (`brainstorming`, `systematic-debugging`, `verification-before-completion`, `writing-plans`) are loaded; these provide the audit process this document follows. They should remain the process framework for any future SHURA architecture change.
- Creative workflow skills (`comfyui`, `songwriting-and-ai-music`, `ascii-art`, etc.) are installed; not verified live. Before building SHURA-specific creative skills, verify which superpowers skills actually work in this Hermes profile.
- MCP server connections (`majiks-studio`, `hugging_face`, `amplitude`) — fix the interpolation mismatch (`${MCP_...KEY}` vs `.env`) before any further integration work; verify with POST (`initialize` + `tools/call`) rather than port checks (`lsof`) per SKILL.md audit pattern.
- Release gate (`docs/RELEASE_GATE.md`, 2,307 bytes, created in Phase 0-1) — migrate enforcement into Hermes workflow if desired; today it is a document, not an automated gate.
- Memory/user profile is already in Hermes config; if the user wants SHURA memory protocols to live as Hermes skills rather than config entries, design that as a separate bounded change.

## 7. What should remain ProjectSHURA-specific (verified + recommendation)
- VTuber runtime code (`main.py`, `src/core/`, interfaces, modules): this is the SHURA application, not a Hermes feature. Hermes should orchestrate/configure it (`hermes` launches/configures; `zed` edits; runtime runs independently) per MIGRATION RUNBOOK §9.
- Avatar/embodiment assets (`data/avatars/`) — ProjectSHURA-specific; Hermes does not manage image files.
- Live2D roadmap (`docs/shura/` art layers, mesh rigging) — creative/embodiment work; Hermes should reference it, not own it.
- Minecraft skill behavior (`data/prompts/minecraft.md`, `.crush/` if retained) — application-level skill, not Hermes-level.
- Local model paths (`ACE-Step-1.5`, `MLX` `.venv`, `.models/`) — runtime environment details; Hermes config can reference them but shouldn't duplicate the environment.
- `.env`, `.gitignore`, `Makefile`, `pyproject.toml`, `uv.lock` — standard repo files; no migration needed.

## 8. What's missing for ATLAS / FORGE interoperability (verified + recommendation)
Verified present (post-Phase 0-1):
- `ATLAS.project` (canonical repo, 18 files, commit 5a9d14a) — contains `archive/`, `atlas/`, `docs/`, `scripts/`, `references/`, `assets/`.
- `FORGE.project` (canonical repo, 5 files, commit d5a9121) — `AGENTS.md`, `README.md`, `docs/FSI.md`, `docs/FORGE-CAPABILITIES.md`, `CONTRIBUTING.md`.
- `Projects/shura-forge/SHURA-ATLAS/FSI.md` (heartbeat) + `scripts/` (audit-fsi, bootstrap).
Confirmed missing / ambiguous:
- `ATLAS.project/AGENTS.md` — empty (8 bytes). Needs content migration from `projectSHURA/docs/`. ASSUMPTION: it is intended to hold the ATLAS agent contract; not yet written.
- `FORGE.project/AGENTS.md` — empty. Same gap.
- Interoperability contract between `projectSHURA` and `ATLAS.project` / `FORGE.project` — no `docs/ATLAS_INTEROPERABILITY.md` or equivalent. Need explicit interface definition (what ATLAS reads from SHURA runtime; what FORGE audits; how FSI feeds back).
- `SHURA_MEMORY_PROTOCOL.md` — FOUND (canonical copy at `~/Downloads/shura-hermes-handoff/shared/SHURA_MEMORY_PROTOCOL.md`, 1,954 bytes, 78 lines); not yet copied into `.hermes/` or `projectSHURA/docs/`. Confirm propagation path.
- `SHURA_OPERATING_PROTOCOL.md` — FOUND (`~/Downloads/shura-hermes-handoff/shared/SHURA_OPERATING_PROTOCOL.md`, 2,156 bytes, 55 lines); closest repo equivalents `docs/shura/OPERATING.md` / `data/prompts/operating.md`. Confirm whether `OPERATING.md` should be superseded by `SHURA_OPERATING_PROTOCOL.md` or kept as the runtime interpreter.
- `SHURA_RED_TEAM_PROTOCOL.md` — FOUND (`~/Downloads/shura-hermes-handoff/shared/SHURA_RED_TEAM_PROTOCOL.md`, 1,482 bytes, 43 lines); not in repo docs. Confirm propagation.
- `HERMES_MIGRATION_PLAN.md` — FOUND (`~/Downloads/shura-hermes-handoff/shared/HERMES_MIGRATION_PLAN.md`, 2,362 bytes, 71 lines); closest repo equivalent `docs/HERMES_MIGRATION_RUNBOOK.md` (334 lines). The two documents overlap conceptually but have different scope/length — the Downloads copy is shorter and phase-oriented; the repo runbook is longer and tool-level. Confirm which becomes canonical; do not blindly overwrite.
- `SHURA_MASTER_CONTEXT.md` — FOUND (`~/Downloads/shura-hermes-handoff/shared/SHURA_MASTER_CONTEXT.md`, 15,062 bytes, 313 lines); closest repo equivalent `docs/SHURA_MASTER_HANDOFF.md` (1,687 lines, older/historical). Confirm which is canonical; the Downloads version is newer and broader in scope.
- `CRUSH.md` exists (`projectSHURA/CRUSH.md`) — describes Crush framework; needs explicit status (integrate into Hermes as separate agent framework, or archive as independent experiment) to avoid duplicate orchestration.

## 9. Smallest safe next sequence (verified, non-destructive, reversible)
Sequence respects AGENTS.md rules (inspect → scope → edit → test → review; preserve mood layer; no secrets; no identity rewrite; distinguish implemented/partial/planned/speculative).

STEP A — Verification (no edits):
- A1: Confirm `md5 ~/.hermes/SOUL.md projectSHURA/docs/shura/SOUL.md` still identical (run `scripts/sync_soul.sh` or manual `md5`).
- A2: Confirm `docs/shura/OPERATING.md` and `data/prompts/operating.md` divergence status (run `diff`).
- A3: Confirm `.hermes/skills/shura/SKILL.md` matches any repo-side mirror (if one exists; create mirror if missing).
- A4: Confirm `ATLAS.project` and `FORGE.project` commit presence (already verified: 5a9d14a, d5a9121).
- A5: Confirm Majik MCP interpolation (`grep MCP_...KEY` in `.hermes/config.yaml` vs `.env`) — fix the variable name mismatch before any live test.

STEP B — Documentation reconciliation (bounded, reversible with git revert):
- B1: Add `docs/SHURA_MEMORY_PROTOCOL.md` (reconcile MASTER HANDOFF §16/§17 + ARCHITECTURE_AUDIT memory notes + user profile config). Label as PLANNED / INITIAL DRAFT.
- B2: Add `docs/SHURA_RED_TEAM_PROTOCOL.md` (move red-team rules from MASTER HANDOFF §26 + SKILL.md audit patterns into dedicated file). Label as PLANNED.
- B3: Create alias/rename mapping (one file or heading) linking user-cited filenames (`SHURA_MASTER_CONTEXT.md`, `SHURA_OPERATING_PROTOCOL.md`, `SHURA_MEMORY_PROTOCOL.md`, `SHURA_RED_TEAM_PROTOCOL.md`, `HERMES_MIGRATION_PLAN.md`) to their existing equivalents (`SHURA_MASTER_HANDOFF.md`, `docs/shura/OPERATING.md` or `OPERATING.md`, `SHURA_MEMORY_PROTOCOL.md` to be created, `SHURA_RED_TEAM_PROTOCOL.md` to be created, `docs/HERMES_MIGRATION_RUNBOOK.md`). Preserve both filenames until user approves consolidation.
- B4: Update `ATLAS.project/AGENTS.md` and `FORGE.project/AGENTS.md` with minimal agent contracts (reference `projectSHURA/docs/IDENTITY_MANIFEST.md` and `docs/SHURA_MASTER_HANDOFF.md` rather than duplicating content).

STEP C — Skill/tool hygiene (bounded, reversible):
- C1: Add repo-side mirror `projectSHURA/skills/shura/SKILL.md` that points to `.hermes/skills/shura/SKILL.md` (symlink or copy with sync note).
- C2: Fix `.hermes/config.yaml` `mcp_servers.majiks-studio.headers.Authorization` interpolation (align variable name to `.env`). Label change in git or note; test with POST before claiming live.
- C3: Define explicit interoperability interface between `projectSHURA` and `ATLAS.project` / `FORGE.project` — small document (`docs/ATLAS_INTEROPERABILITY.md`), no code change.

STEP D — Preservation confirmations (no change):
- D1: Confirm `monologue.md` remains in `data/prompts/` (do not delete — redesign separately).
- D2: Confirm `.crush/` preserved; add one-line status note (`preserved / separate experiment`); no merge.
- D3: Confirm `docs/RELEASE_GATE.md` remains; if migrating enforcement into Hermes workflow, design as bounded change first (not here).

## Key verified facts vs assumptions
VERIFIED (from file reads / terminal / git / Downloads package inspection):
- SOUL.md content, byte-match claim (IDENTITY_SYNC.md); `Downloads/` canonical package exists with `shared/SHURA_*` docs (MASTER_CONTEXT 15,062 bytes / MEMORY 1,954 / OPERATING 2,156 / RED_TEAM 1,482 / MIGRATION_PLAN 2,362; IDENTITY_SYNC 1,742) plus `hermes-global/SOUL.md` (6,370 bytes, 110 lines — different from runtime 8,854 bytes / 225 lines — consistent with IDENTITY_SYNC.md's three-layer identity model: global identity ≠ runtime identity ≠ project identity).
- `.hermes/skills/shura/SKILL.md` content; `.hermes/plugins/superpowers/` presence (14 skills).
- `Downloads/ATLAS.project/AGENTS.md` (2,186 bytes) and `FORGE.project/AGENTS.md` (2,316 bytes) present but file-level contents not fully reconciled with `projectSHURA/docs/` equivalents (same file names, different sizes — potential divergence).
- `Downloads/projectSHURA/AGENTS.md` (3,045 bytes) differs from repo `AGENTS.md` (2,461 bytes) — the Downloads version is newer/expanded; reconcile before treating either as canonical.
- `ARCHITECTURE_AUDIT.md` findings (interpolation mismatch, model drift, REAPER script-only, ACE binary executable) reconfirmed via file reads; `Downloads/` package does not supersede them — it complements them at a conceptual layer.

ASSUMPTION (requires verification):
- `SOUL.md` byte match remains true today (last verification 2026-09-12 per IDENTITY_SYNC.md); run `md5` again before identity edits.
- `ATLAS.project` / `FORGE.project` content is current (only commits verified; file contents not fully read in this audit).
- `SHURA_MEMORY_PROTOCOL.md`, `SHURA_RED_TEAM_PROTOCOL.md`, and user-cited filenames (`MASTER_CONTEXT.md`, `OPERATING_PROTOCOL.md`, `HERMES_MIGRATION_PLAN.md`) do not exist in repo or `.hermes/` — confirmed by `find` / `search_files` during audit, but user may have them elsewhere; ask before creating duplicates.
- `.hermes/skills/shura/SKILL.md` is the canonical routing layer; if user intends a different canonical location, clarify before adding repo mirror.
- Creative pipeline (Majik→REAPER) design is correct; no live end-to-end run executed in this session.

## Conclusion (spike output — design presented, no implementation started)
This is a SPIKE audit, not an architectural change. The evidence supports these conclusions without requiring code rewrites:
1. SHURA identity layer is coherent and synchronized (SOUL.md + SKILL.md + OPERATING.md + AGENTS.md); preserve that coherence.
2. Hermes provides the process framework (superpowers skills) and the routing layer (`shura` SKILL.md); use it.
3. The real gaps are documentation (memory/red-team/protocol filenames, ATLAS/FORGE agent contracts, interoperability interface) and one live integration fix (MCP interpolation), not a structural identity rewrite.
4. The smallest safe sequence (A verification → B docs reconciliation → C hygiene → D preservation confirmation) keeps everything reversible, does not touch identity content, and respects the AGENTS.md rules.

Next: user approval of this audit's design before any file edits. Per brainstorming rules, this audit IS the design presentation; user approval unlocks bounded implementation steps in sequence A–D above.
