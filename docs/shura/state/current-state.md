# SHURA / ProjectSHURA — Current-State Audit

Status: v1 audit · 2026-09-14 · Branch `shura-foundation` (93dba57)
Auditor: SHURA engineering agent (Hermes desktop)
Scope: repository audit per master directive §5-6, §37. No destructive changes made.

## A. Actual architecture (as implemented)
- Root: `/Users/ultraviollett/projectSHURA` (git, 26 commits, upstream=BEA).
- Substrate: BEA-derived brain loop (`src/core/brain.py`), consciousness (`consciousness.py`), expression (`expression.py`), skills registry, OBS/PNG/voice surfaces.
- Identity layer: `data/prompts/soul.md`, `operating.md`, `chat.md`, `monologue.md`, `minecraft.md`. Replicated in `docs/shura/` and `~/.hermes/SOUL.md` (canonical live kernel).
- State: session JSONs (`data/conversations/`), `data/memory/` (self.md, recent.json, dreamed.json), `memory_db/` (chroma + binary), `docs/shura/state/` (planned).
- Embodiment: PNG/OBS with legacy 7 mood IDs (`normal/shock/love/cry/angry/ew/bored`) preserved in `data/avatars/shura/` — load-bearing per AGENTS.md.
- Skills: chat, voice, idle, minecraft, memory, social, dream, voice bot (Discord). `src/core/skills/`.
- Tools/MCP: config references `majiks-studio` (localhost:8478, Bearer), `hugging_face`, `amplitude`. `mcp` package installed.
- Providers: config names `omniroute` (localhost:20128), `nous`, `openrouter`. `.env` and `.env.example` present; no secrets committed (verified via `.gitignore`).
- Dev infra: `.crush/` (separate agent framework, unintegrated), `.vibe/`, `.shura/`. `pyproject.toml` / `uv.lock` / `.venv` (python 3.11.15, includes `mlx_lm`, `edge-tts`).
- Companion repos: `ATLAS.project` (scaffold, 107 commits, empty content), `FORGE.project` (scaffold), `Shura/` (superseded).

## B. What works
- Git branch clean (1 unstaged file: `scripts/sync_shura_hermes.sh`).
- Identity stack coherent (soul.md, operating.md, AGENTS.md, SKILL.md). No provider/model lock-in in identity layer.
- Legacy mood IDs preserved; OBS-compatible.
- Source tree intact (brain, consciousness, expression, skills, perception, events, agent/LLM client).
- Hermes environment verified: v0.21.1, superpowers plugin loaded, memory/user profile enabled, TTS/STT configured (not exercised in this session).
- `.env` present with `MCP_MAJIKS_STUDIO_API_KEY` (not committed).

## C. Broken / confirmed failures
- **CORRECTED — MCP interpolation RESOLVED** (was reported as broken; superseded by `PHASE_0_1_EXECUTION_REPORT.md` / `MAJIK_MCP_VERIFICATION.md`): `${MCP_...KEY}` resolves via Hermes wildcard/partial-match to `MCP_MAJIKS_STUDIO_API_KEY`. Key validated (`mms_KCZF1E...`). No config change needed. Document contradiction resolved in favor of newer verification.
- **MEDIUM — Provider/model drift**: `config.yaml.default` = `poolside/laguna-s-2.1:free` via `nous`; actual session model = `thinkingmachines/inkling:free` via `openrouter`. No explicit tracking.
- **MEDIUM — REAPER MCP**: architecture spec defines tool families; no live REAPER MCP server exists (only Majik's).
- **MEDIUM — ACE Studio**: installed (v2.1.1), minimal plist footprint; no MCP/CLI evidence — integration assumption unverified.
- **LOW — Identity duplication risk**: `~/.hermes/SOUL.md` (live) vs repo copies (`docs/shura/SOUL.md`, `.shura/agents/constitution.md`); no sync procedure.

## D. Partial / incomplete
- Document/knowledge system: ingestion/retrieval spec exists (`docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md`); no live ingestion pipeline.
- Audiobook / interactive reader mode: design only.
- Developer agent capabilities (repo inspection, test, debug, release gating): partial (`agent/` exists; no verified end-to-end).
- ATLAS / FORGE: separate repos exist; interfaces not implemented in this repo.
- Crush (`.crush/`): separate framework; no Hermes integration.
- Web (`src/web/` has `server.py` + `frontend/index.html`); not fully implemented against spec.
- Test coverage: minimal; no regression test for MCP auth or mood-state transition.

## E. Architectural risks
- Coupling: brain loop inherits BEA substrate (not wrong — must be preserved per directive §3 / AGENTS.md); risk is gradual, not sudden.
- Duplication: architecture docs (`docs/architecture.md` superseded by `SHURA_V1_ARCHITECTURE_AND_ROADMAP.md`) — stale reference risk.
- Security: `MCP_MAJIKS_STUDIO_API_KEY` exposed in `.env` (expected); no secrets in git (verified). Interpolation failure prevents accidental exposure of a broken auth header — but once fixed, verify header is not echoed in logs.

## F. Highest-value improvements (ranked)
1. Fix MCP interpolation (`docs/ARCHITECTURE_AUDIT.md` §5) — unlocks Majik creative pipeline (Priority 5 / creative systems).
2. Write sync procedure for `~/.hermes/SOUL.md` ↔ repo copies (continuity / Priority 3).
3. Consolidate superseded docs (`architecture.md` → archive; label `SHURA_V1...` canonical) — reduces confusion.
4. Add regression test for mood-state preservation (normal/shock/love/cry/angry/ew/bored) across refactors.
5. Document rollback for `mcp_servers` migration (`config.yaml.pre-majik-*` exists; no rollback doc).

Verification performed: `git status`, `git branch`, file reads (brain.py, consciousness.py, prompts, docs/ARCHITECTURE_AUDIT.md), `.env` inspection (no secrets in source), `.gitignore` verification, skill inventory (`.hermes/skills/`), avatar exports count (7 mood IDs present), `docs/shura/state/` created. No destructive commands executed. No commits made.

Next recommended task: fix Majik MCP interpolation (`.env` key matches config reference); add rollback doc for `mcp_servers`; begin identity-sync procedure doc. These are small, high-leverage, non-destructive — consistent with directive §27-28.
