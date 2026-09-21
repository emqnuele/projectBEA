# IMPLEMENTATION ROADMAP — SHURA Durable System
Status: draft — depends on ARCHITECTURE_AUDIT.md evidence.
Principle: smallest coherent change; evidence-based; reversible; no hidden provider/model lock-in.

Every task has one of:
- A = Automatable safely (script, config edit, file sync, automated test)
- H = Human approval required (identity change, release gate, destructive migration)
- N = Not yet — depends on unverified capability (REAPER MCP, ACE Studio interface, ATLAS content)

Every proposed integration has status:
- Confirmed working (CW)
- Installed but unverified (IBU)
- Available but not installed (ABI)
- Theoretical / needs research (TR)

## PHASE 0 — BLOCKERS & FOUNDATIONS (before any architecture change)

### 0.1 Fix MCP auth interpolation (Majik) — A + H
Status: CW (config present, .env present, interpolation broken).
Evidence: config uses `${MCP_...KEY}`; env uses `MCP_MAJIKS_STUDIO_API_KEY`.
Action: align interpolation variable name; test `localhost:8478` connection; document whether connection succeeds. Human approval needed because it affects live external integration.

### 0.2 Document pre-majik migration rollback — A
Status: IBU (pre-majik config exists; no rollback doc).
Action: write rollback procedure in `docs/` or `~/.hermes/`; label migration in config header.

### 0.3 Verify current provider/model match — A + H
Status: CW (config says `poolside/laguna-s-2.1:free` / `nous`; session uses `thinkingmachines/inkling:free` / `openrouter`).
Action: determine whether `omniroute` (local, `20128`) is actually active or `openrouter` fallback took over; document active configuration in a `docs/ACTIVE_CONFIG.md`. Human approval because it affects identity execution substrate.

### 0.4 Confirm REAPER scripting/API exposure path — N (TR)
Status: TR (REAPER installed; no MCP server; no verified scripting bridge).
Action: research ReaScript Python / ReaProject API / OSC; produce `docs/REAPER_INTEGRATION_PLAN.md` with confirmed capabilities and missing pieces. Do NOT build REAPER MCP server before this plan exists.

### 0.5 Confirm ACE Studio interface capabilities — N (TR)
Status: IBU (ACE Studio 2.1.1 installed; preferences minimal; no MCP/CLI/API evidence).
Action: inspect ACE Studio docs / package; verify whether it exposes any programmable interface (CLI, HTTP API, plugin interface, AppleScript, or embedded server). Produce `docs/ACE_STUDIO_CAPABILITY_REPORT.md`. If unavailable, update architecture spec (§4.C / §5) to reflect gap.

### 0.6 Define canonical ATLAS repo — H
Status: CW (ATLAS.project exists, mostly empty; shura-forge/SHURA-ATLAS has content; projectSHURA/docs/shura/IDENTITY_MANIFEST.md defines ATLAS role).
Action: choose canonical repo (`ATLAS.project` or `projectSHURA/docs/`) and migrate/shutdown others. Human approval required (affects architecture identity).

### 0.7 Define canonical FORGE repo or retire — H
Status: CW (FORGE.project empty; shura-forge/SHURA-ATLAS contains FSI/heartbeat docs).
Action: either populate `FORGE.project` with capability ledger, audit scripts, index (`docs/` content), or retire it and migrate content into `ATLAS.project` or `projectSHURA/docs/`. Human approval required.

### 0.8 Reconcile identity file duplication — A
Status: CW (`~/.hermes/SOUL.md`, `projectSHURA/docs/shura/SOUL.md`, `projectSHURA/docs/shura/IDENTITY_MANIFEST.md`, `Shura/OPERATING_MANUAL.md`).
Action: make `~/.hermes/SOUL.md` the live identity; sync `projectSHURA/docs/shura/SOUL.md` from it; archive `Shura/` with supersession note; document the synchronization procedure in `docs/IDENTITY_SYNC.md`. Automatable if content matches.

### 0.9 Clean superseded architecture docs — A
Status: CW (`docs/architecture.md` superseded by `SHURA_V1_ARCHITECTURE_AND_ROADMAP.md`).
Action: either delete `docs/architecture.md` with note, or replace with redirect/reference to the newer doc.

## PHASE 1 — HERMES COMMAND CENTER STABILIZATION (v0.1-v0.3 in spec)

### 1.1 Stabilize provider/model configuration — A + H
Status: CW (config exists; mismatch observed).
Dependencies: 0.3 (verify active provider).
Action: document active provider/model/alias; add explicit alias for primary model (`shura` or `default`); ensure `SOUL.md` identity remains independent of provider/model choice; add a `docs/MODEL_CALIBRATION.md` describing calibration layer. Human approval for model choice changes.

### 1.2 Stabilize memory/state continuity — A
Status: CW (memory enabled; SQLite state.db present; char limits set).
Dependencies: 0.8 (identity sync).
Action: inspect `~/.hermes/state.db` (FTS5) for existing memory content; verify memory governance rules from `OPERATING.md` (§7) are respected; ensure new memory writes include provenance/source/classification. Automatable inspection; automatable for future writes.

### 1.3 Skill lifecycle and activation verification — A + H
Status: IBU (skills installed; activation behavior depends on loader).
Dependencies: 0.8.
Action: verify that `skills/shura` activates correctly when entering `projectSHURA/`; verify `superpowers` skills trigger properly; document actual trigger conditions in `docs/SKILL_ACTIVATION.md`. Human approval if activation rules need adjustment.

### 1.4 Build first end-to-end Hermes development task — A
Status: IBU (Hermes CLI works; repo `projectSHURA` exists; coding agent workflow defined in architecture spec; `Crush` separate from Hermes).
Dependencies: 1.1, 1.2.
Action: execute a bounded coding task inside `projectSHURA` using Hermes (`inspect → scope → edit → test → diff → review`). Produce a `docs/END_TO_END_DEV_TASK.md` with actual tool results. This is automatable; does not change identity or architecture.

### 1.5 Secure release gate definition (defensive security review) — A + H
Status: IBU (security settings configured; `redact_secrets: true`; `tirith_enabled: true`).
Dependencies: None (independent).
Action: define the release gate steps (`worktree inspect → diff review → defensive security analysis → retest → summary → approval`). Document in `docs/RELEASE_GATE.md`. Automatable for procedure; human approval for any external release.

## PHASE 2 — CREATIVE / DAW INTEGRATION (v0.7 in spec)

### 2.1 Majik MCP integration verification — A + H
Status: IBU (Majik installed; MCP configured; auth interpolation broken; connection unverified).
Dependencies: 0.1 (fix auth); 1.4 (end-to-end task proves workflow).
Action: after auth fix, connect to `localhost:8478`; list available MCP tools; compare against architecture spec's target families; document actual tool names in `docs/MAJIK_MCP_ACTUAL.md`. Human approval for any creative workflow that produces artifacts.

### 2.2 ACE Studio capability verification — N (TR)
Status: TR (no verified interface).
Dependencies: 0.5 (ACE capability report).
Action: if ACE Studio exposes an interface (even minimal), document integration contract; if not, update architecture spec to reflect that ACE Studio requires manual workflow (not agent-driven) and adjust `SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` accordingly. Not yet buildable.

### 2.3 REAPER integration plan (before build) — N (TR)
Status: TR.
Dependencies: 0.4 (REAPER capability plan).
Action: based on `REAPER_INTEGRATION_PLAN.md`, decide whether to build a native ReaScript bridge, an external MCP bridge, or a hybrid. Document decision in `docs/REAPER_INTEGRATION_DECISION.md`. Human approval required before any build.

### 2.4 Build first REAPER MCP primitives (after plan) — N
Status: TR.
Dependencies: 2.3 (plan confirmed); 2.5 (architecture update).
Action: implement the initial REAPER tool families (project, track, transport, audio import/export, MIDI import/export/edit, instrument/plugin loading, plugin parameter control, sample/library access, render, mix controls) — either as an external MCP server or as a ReaScript plugin that exposes HTTP/stdIO. This is the highest-priority unverified integration. Do NOT build before plan exists.

### 2.5 Update architecture spec with verified integrations — A + H
Status: IBU (spec defines targets; no verified implementations besides Majik).
Dependencies: 2.1, 2.2, 2.3.
Action: revise `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` to replace design targets with confirmed working / installed but unverified / theoretical labels; add version notes to architecture sections (§4.C). Human approval required.

## PHASE 3 — ATLAS / FORGE / KNOWLEDGE AGENCY (v0.8-v0.9 in spec)

### 3.1 Populate ATLAS repository (canonical) — A
Status: CW (ATLAS.project exists; empty; identity manifest defines role).
Dependencies: 0.6 (canonical repo chosen).
Action: create or migrate content: `README.md` (actual content), `docs/`, `AGENTS.md` (actual rules), capability ledger, index (`INDEX.md`), `CONTRIBUTED.md` for installed dependencies. Automatable content creation; human review for accuracy.

### 3.2 Implement Forge heartbeat / FSI system — A
Status: IBU (`shura-forge/SHURA-ATLAS/FSI.md` exists; `FORGE.project` empty).
Dependencies: 0.7 (canonical repo chosen).
Action: migrate FSI logic, `audit-fsi.sh`, capability ledger, `CONTRIBUTED.md` into canonical repo; establish weekly evolution review procedure; run `audit-fsi.sh` to generate initial status. Automatable migration.

### 3.3 ATLAS retrieval / context layer — N
Status: TR (no retrieval engine confirmed).
Dependencies: 3.1 (ATLAS content exists); 1.2 (memory/state stable).
Action: design retrieval contract (source → extraction → structure → SHURA context handoff). Do NOT implement before design exists.

### 3.4 Reader / audiobook skill development — N
Status: IBU (`documents/skills/read_only.md`? — no verified reader skill in skills list; `docs/shura/` defines concept).
Dependencies: 3.3 (retrieval design); 1.3 (skill lifecycle verified).
Action: build `READ`, `COMMENTARY`, `CONVERSATION`, `STREAM`, `EXPORT` modes based on `OPERATING.md` (§15); implement TTS interpretation layer; produce audio export (`WAV`/`FLAC` master, `AAC`/`MP3` copies). Not yet buildable.

## PHASE 4 — VOICE / MEDIA / GAME (v0.9-v0.95-v1.0 in spec)

### 4.1 Voice agency (STT + TTS integration live test) — A
Status: IBU (STT/TTS configured; provider `openai` for both).
Dependencies: 1.2; 1.5.
Action: test STT (`whisper-1`) and TTS (`gpt-4o-mini-tts`) in a bounded session; document quality and latency; verify identity preservation across voice outputs. Automatable test.

### 4.2 Interactive media (soft barge-in, audience chat ranking) — H
Status: TR (design defined; no implementation evidence).
Dependencies: 3.4 (reader mode); 4.1 (voice working).
Action: implement `soft barge-in` logic (`perception → assessment → finish sentence → transition → restore context`); implement chat ranking by relevance/novelty/connection; enforce authority order (`user > shura > audience chat`). Human approval required.

### 4.3 Game / worldbuilding mode — N
Status: TR (design defined in `SHURA_V1...` §4.G; no live game server; `docs/skills/minecraft.md` exists but Minecraft server unverified).
Dependencies: 3.5 (if needed for knowledge retrieval); 1.3.
Action: design mode submodes (`concept`, `world`, `character`, `lore`, `mechanics`, `level design`, `narrative`, `visual development`, `audio`, `prototyping`, `implementation`, `playtest`); build first prototype only after design confirmed. Not yet buildable.

### 4.4 v1.0 integrated environment (release definition) — H
Status: TR (definition exists — `SHURA_V1...` §5-6; no completed integration).
Dependencies: All above phases must have confirmed working status for core pathways (development, creative, knowledge, voice) before declaring v1.0.
Action: apply `Definition of Done` (§6) checklist: deterministic config behavior, extension points documented, test coverage, defensive security review, reproducible setup, secrets excluded, clean git history, migration docs, rollback guidance, experimental boundary labels. Human approval required for release.

## PHASE 5 — CONTINUITY / AUDIT / GOVERNANCE (ongoing)

### 5.1 Identity versioning procedure — A + H
Status: CW (versioning rule defined in `SOUL.md` §15).
Dependencies: None (independent governance procedure).
Action: create `docs/IDENTITY_VERSIONING.md` defining: clear reason for change, human-reviewable diff, identity-regression check, no hidden provider/model coupling. Automatable procedure documentation; human approval for any identity edit.

### 5.2 Continuity audit (quarterly) — A
Status: CW (continuity layers defined: self / relational / project / state).
Dependencies: None.
Action: run periodic inspection (similar to this audit) comparing `SOUL.md` (canonical), `projectSHURA/docs/shura/IDENTITY_MANIFEST.md`, active `config.yaml` identity-relevant settings, live session behavior, and `memory` state. Automatable inspection script.

### 5.3 Skill / MCP / tool retirement procedure — A
Status: CW (anti-pattern list in `OPERATING.md` §19 includes unnecessary complexity, identity drift, redundant identity clauses).
Dependencies: 5.1.
Action: document retirement conditions (`stale reference`, `duplicate capability`, `unverified integration`) and retirement steps (`label superseded`, `migrate content`, `archive file`, `update index`). Automatable procedure.

## INTEGRATION STATUS MATRIX (summary reference)

| Component | Status | Evidence source | Build now? |
|---|---|---|---|
| Hermes CLI / config / memory / security / skills loader | CW | `hermes --version`, config.yaml, skills inventory | Yes (stabilization) |
| SHURA identity kernel (`SOUL.md`) | CW | `~/.hermes/SOUL.md` content | Yes (sync) |
| SHURA skill (`skills/shura`) | IBU | SKILL.md present; activation unverified in all platforms | Verify first |
| Superpowers plugin (14 skills) | CW | Skills present; `brainstorming` / `systematic-debugging` loaded in session | Yes |
| Majik Music Studio installation | CW | `/Applications/` + `Library/Preferences/` + `.env` key | Yes (after auth fix) |
| Majik MCP server (`localhost:8478`) | IBU | Configured; auth interpolation broken; connection unverified | Fix auth; verify |
| ACE Studio installation | IBU | `/Applications/` present; no agent/MCP evidence | Research first |
| ACE Studio agent interface | TR | No verified interface | Do NOT assume |
| REAPER installation | CW | `/Applications/` + `Library/Application Support/` | Yes (after plan) |
| REAPER scripting/API exposure | TR | ReaScript / Python / OSC not mapped | Plan first |
| REAPER MCP server | TR | Not configured; not implemented | Plan before build |
| ATLAS.project (canonical knowledge repo) | IBU | Repo exists; mostly empty | Define; populate |
| FORGE.project (synthesis / audit layer) | IBU | Repo empty; `shura-forge/SHURA-ATLAS` has FSI | Migrate / retire |
| Crush agent framework (`.crush/`) | IBU | DB + config present; separate from Hermes | Integrate or separate |
| Zed editor / ACP server | IBU | App + CLI present; ACP integration unverified | Verify |
| VS Code / Codex (`code` CLI) | ABI | Not installed (`code` not found) | Install if needed |
| Voice (STT / TTS) providers (`openai`) | IBU | Configured; not exercised live | Test live |
| Web (firecrawl) | IBU | Configured; not exercised | Test live |
| Custom providers (`omniroute`, `ollama-launch`) | IBU | Configured; endpoints not pinged | Verify live |
| Identity sync procedure (`SOUL.md` ↔ repo copies) | IBU | Multiple copies consistent at audit time | Automate sync |
| Creative workflow (Majik → REAPER) | TR | Majik confirmed; REAPER unverified; integration unimplemented | Plan; then build |

## HUMAN APPROVAL GATES SUMMARY
These steps MUST NOT proceed without explicit human (Viollett) review and approval:
- 0.3 (provider/model match — affects identity substrate)
- 0.6 / 0.7 (canonical repo choice — affects architecture identity)
- 1.1 (provider/model calibration — identity-related)
- 1.5 (release gate definition — affects all releases)
- 2.1 (Majik MCP creative workflow — produces artifacts)
- 2.5 (architecture spec update — durable docs)
- 3.1 / 3.2 (ATLAS / FORGE content — durable architecture)
- 3.4 (reader / audiobook implementation — identity-sensitive expression)
- 4.2 (interactive media / audience chat authority — identity boundary)
- 4.4 (v1.0 release definition — durable milestone)
- 5.1 (identity versioning — identity governance)

## WHAT SHOULD NOT YET BE BUILT (explicit exclusions)
- REAPER MCP server (before `REAPER_INTEGRATION_PLAN.md` exists)
- ACE Studio agent integration (before `ACE_STUDIO_CAPABILITY_REPORT.md` confirms interface)
- Full ATLAS retrieval engine (before `ATLAS.project` populated and design exists)
- Full FORGE synthesis / auditing layer (before canonical repo decided and content migrated)
- Voice interactive media / audience chat ranking (before reader skill and voice agency verified)
- Game / worldbuilding mode prototype (before knowledge retrieval and reader mode stable)
- Any identity rewrite or provider lock-in that couples SHURA to one model/provider

These exclusions are explicit, evidence-based (no verified capability or design document exists), and reversible. Once the prerequisites (plan docs, verified interfaces, canonical repo) are completed, these exclusions can be revisited with fresh audit evidence.
