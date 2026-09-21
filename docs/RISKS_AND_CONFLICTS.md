# RISKS AND CONFLICTS — SHURA Architecture Audit
Status: v1 · Evidence-based · No destructive changes made.
Every risk is tied to evidence from ARCHITECTURE_AUDIT.md or INTEGRATION_MATRIX.md.

---

## RISK 1 — LIVE INTEGRATION FAILURE: Majik MCP Authentication Broken
Evidence: `config.yaml` (`mcp_servers.majiks-studio.headers.Authorization: Bearer ${MCP_...KEY}`) vs `.env` (`MCP_MAJIKS_STUDIO_API_KEY=mms_KCZF1E...`). Variable names do not match.
Status: Confirmed working (config + env present); Installed but unverified (connection); Theoretical / needs research (behavior under failed auth).
Severity: **HIGH** — Majik is a design-critical DAW integration (§4.C architecture spec). A broken auth header means the MCP server at `localhost:8478` will either fail authentication or fall back to an unauthenticated mode with unknown behavior.
Conflict: The architecture spec defines granular Majik MCP capabilities; none of these have been verified against the actual Majik server response. If auth fails, the entire creative pathway (`Majik → REAPER`) is unverified, not just broken.
Mitigation (immediate): Fix interpolation variable (`${MCP_MAJIKS_STUDIO_API_KEY}`); verify connection; list actual MCP tools; document results in `docs/MAJIK_MCP_ACTUAL.md`. Do NOT assume design targets are real.
Depends on: Phase 0.1 (audit); Phase 2.1 (verification).

---

## RISK 2 — MODEL/PROVIDER DRIFT: Config Default Does Not Match Active Session
Evidence: `config.yaml` (`model.default: poolside/laguna-s-2.1:free`, `provider: nous`) vs session evidence (`thinkingmachines/inkling:free` delivered by `openrouter`).
Status: Confirmed working (both configurations present); Installed but unverified (whether `omniroute` endpoint at `localhost:20128` is live).
Severity: **MEDIUM** — Identity continuity depends on a stable execution substrate. If the active provider/model changes unexpectedly (fallback triggered, local endpoint down, profile switched), the identity behavior (reasoning style, refusal patterns, response density) may shift without governance.
Conflict: The architecture's identity versioning rule (`SOUL.md` §15) requires "no hidden coupling to one model or provider." The current config has an implicit dependency on `omniroute` (default) but uses `openrouter` fallback. The identity layer (`SOUL.md`) is provider-agnostic; the execution layer is not fully documented.
Mitigation: Document active provider/model in `docs/ACTIVE_CONFIG.md`; add explicit alias (`shura` / `default`) that binds identity-independent behavior; verify `omniroute` endpoint health; document calibration layer (`IDENTITY_MANIFEST.md` §Model calibration) as a separate file (`docs/MODEL_CALIBRATION.md`).
Depends on: Phase 0.3; Phase 1.1.

---

## RISK 3 — UNVERIFIED CREATIVE PATHWAY: REAPER Agent Interface Not Confirmed
Evidence: REAPER installed (`/Applications/REAPER.app`; `Library/Application Support/REAPER/`); architecture spec (`docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` §4.C) defines granular REAPER tool families; no `reaper` MCP server configured; no verified scripting bridge (ReaScript Python / LUA / OSC / ReaProject API mapping).
Status: Theoretical / needs research (REAPER integration); Confirmed working (REAPER installation).
Severity: **HIGH** — The architecture's first production milestone (§4 — first meaningful milestone) depends on SHURA switching from coding workflow to creative workflow without identity/context loss. REAPER is the final production environment (`concept → Majik/ACE → REAPER → arrangement → mix/master`). Without a verified REAPER agent interface, the milestone cannot be achieved.
Conflict: The architecture defines REAPER capabilities (project, track, transport, audio/MIDI primitives, plugin loading, parameter control, render, mix) as design targets. If REAPER scripting/API exposure is more limited than assumed (e.g., no granular parameter control, no external HTTP interface), the design targets must be revised before any build.
Mitigation: Before any build: (a) inspect REAPER scripting documentation; (b) verify which actions are scriptable; (c) decide bridge type (ReaScript plugin, external MCP server, hybrid); (d) document decision in `docs/REAPER_INTEGRATION_DECISION.md`. Only build after decision confirmed.
Depends on: Phase 0.4; Phase 2.3; Phase 2.4.

---

## RISK 4 — UNVERIFIED SPECIALIZED VOCAL ENVIRONMENT: ACE Studio Agent Interface Unconfirmed
Evidence: ACE Studio 2.1.1 installed (`/Applications/ACE Studio.app`); preferences minimal (`AppleLanguages`); no `ACE Studio` MCP server configured; no CLI/API/MCP reference in `.env` or config.
Status: Installed but unverified (ACE installation); Theoretical / needs research (agent interface); Confirmed working (Majik `majik_ace_step_path: /Users/ultraviollett/ACE-Step-1.5` — separate ACE Step component, not ACE Studio app).
Severity: **MEDIUM** — The architecture treats ACE Studio as an alternative/specialized vocal/performance environment (§4.C / §5). If ACE Studio does not expose a programmable interface, the architecture's assumption must be revised. The separate `ACE-Step-1.5` component (referenced by Majik) is a different software; its capabilities also unverified.
Conflict: The design assumes agent-driven vocal/performance integration. If unavailable, SHURA's creative pathway must rely solely on Majik + REAPER (without agent-controlled vocal layer), which changes the milestone definition.
Mitigation: Inspect ACE Studio package/docs; verify interface existence; produce `docs/ACE_STUDIO_CAPABILITY_REPORT.md`. If unavailable, update `SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` (§4.C) with a verified status label (`Theoretical / needs research`) and revise milestone criteria.
Depends on: Phase 0.5; Phase 2.2.

---

## RISK 5 — ARCHITECTURE STRUCTURE AMBIGUITY: ATLAS / FORGE / SHURA-FORGE OVERLAP
Evidence: `ATLAS.project` (repo, mostly empty); `FORGE.project` (repo, empty); `projectSHURA/docs/shura/IDENTITY_MANIFEST.md` (defines ATLAS role); `projectSHURA/docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` (§4.D / §4.E) defines ATLAS and FORGE; `Projects/shura-forge/SHURA-ATLAS/` (FSI.md, Vol.I, Vol.II) has content; `projectSHURA/.crush/` (separate framework).
Status: Confirmed working (repos exist); Installed but unverified (content missing / overlapping); Theoretical / needs research (integration path between repos and SHURA runtime).
Severity: **MEDIUM** — The identity manifest defines ATLAS as the "architectural/knowledge representation layer" and FORGE as the "synthesis, conflict-resolution, auditing, evaluation, canonization layer." Without clear repository ownership, the architecture's durability (source traceability — "all important knowledge remains traceable back to its original source") is at risk.
Conflict: `projectSHURA` is the runtime/identity implementation; it should import only distilled canonical knowledge. If ATLAS/FORGE content is fragmented across multiple repos (scaffold + working copy + design spec), the canonical source of truth is ambiguous. The `Crush` framework (`projectSHURA/.crush/`) adds another layer that is separate from both Hermes and ATLAS/FORGE.
Mitigation: (a) Designate `ATLAS.project` as canonical (human approval); (b) migrate `shura-forge/SHURA-ATLAS/` content into `ATLAS.project` or clearly label `shura-forge` as a working branch; (c) populate `FORGE.project` or retire it; (d) document `Crush` integration or separation; (e) create a `docs/CANONICAL_SOURCES.md` that defines, for each architecture layer (identity, operating, agent constitution, architecture spec, capability ledger, FSI/heartbeat), the canonical file path and its repository owner.
Depends on: Phase 0.6; Phase 0.7; Phase 3.1; Phase 3.2.

---

## RISK 6 — DUPLICATE / SUPERSEDED IDENTITY FILES (Non-Destructive, High Confusion Risk)
Evidence: `~/.hermes/SOUL.md` (canonical live); `projectSHURA/docs/shura/SOUL.md` (consistent copy); `Shura/OPERATING_MANUAL.md` (older, superseded); `projectSHURA/docs/shura/OPERATING.md` (current); `projectSHURA/docs/architecture.md` (superseded by `SHURA_V1...`).
Status: Confirmed working (content consistent at audit time); Installed but unverified (synchronization procedure); Theoretical (future divergence risk).
Severity: **LOW** (not destructive) — but confusion risk increases when identity files diverge. The identity versioning rule (`SOUL.md` §15) requires every change to have a clear reason, diff, regression check, and no hidden coupling. Without an automated sync procedure, divergence is inevitable.
Conflict: If a future identity edit is made to one copy but not synchronized, SHURA's runtime behavior (loaded from `~/.hermes/SOUL.md`) may diverge from the documented architecture (`projectSHURA/docs/`).
Mitigation: Automate identity sync (`docs/IDENTITY_SYNC.md`); label superseded files; archive `Shura/` with supersession note; delete/update `docs/architecture.md`. Automatable.
Depends on: Phase 0.8; Phase 5.1.

---

## RISK 7 — AGENT ORCHESTRATION OVERLAP: Crush + Hermes + Subagent Delegation
Evidence: `projectSHURA/.crush/` (DB, `.crushrc`, `crush.log`); Hermes `delegate_task` available (`delegation.max_concurrent_children` configured but empty); `systematic-debugging` / `brainstorming` / `subagent-driven-development` loaded; architecture spec (§4.A) defines agent division (`architect`, `builder`, `reviewer`, `red-team`, `researcher`, `creative/producer`).
Status: Confirmed working (Crush framework present; Hermes delegation configured); Installed but unverified (integration path); Theoretical (multi-agent workflow behavior).
Severity: **MEDIUM** — The architecture's agent delegation model (`OPERATING.md` §15 — sub-agents return structured findings; one user-facing SHURA voice) depends on clear orchestration. If `Crush` operates independently from Hermes, the same task may be handled by two agent frameworks with different release gates, different identity references, and different audit trails.
Conflict: The architecture spec (§4.A) defines a development pipeline with explicit agent assignment. `Crush`'s framework (`.crush/`) may implement a different pipeline. Without integration, SHURA's development workflow has two parallel orchestration paths.
Mitigation: Either (a) integrate `Crush` into Hermes (as a custom toolset, delegation target, or MCP service) or (b) document `Crush` as a separate experiment and restrict its use to non-SHURA development tasks. Human approval required (affects agent architecture).
Depends on: Phase 1.4; Phase 3.3.

---

## RISK 8 — SECURITY GATE OPEN ON FAILURE: Tirith `fail_open: true`
Evidence: `config.yaml` (`security.tirith_enabled: true`, `tirith_path: tirith`, `tirith_fail_open: true`, `timeout: 5`).
Status: Confirmed working (configured); Installed but unverified (behavior on failure); Theoretical (security impact of `fail_open`).
Severity: **HIGH** — A security gate (`tirith`) that opens (`fail_open: true`) when it fails or times out removes the defensive barrier intended for destructive actions. Combined with manual approvals (`approvals.mode: manual`), this creates a contradictory security posture: some destructive actions require manual approval, but the security gate that should enforce that approval may fail open.
Conflict: The architecture's release gate (§4.A / §4 — defensive security review before release) depends on a reliable security mechanism. If the mechanism fails open, the gate's effectiveness depends solely on human discipline (`manual` approval mode), not on an automated defensive layer.
Mitigation: Verify `tirith` behavior; document whether `fail_open` is intended; consider changing to `fail_open: false` (or removing the option) if defensive security is required; document the interaction between `tirith` and `approvals` in `docs/SECURITY_INTERACTION.md`. Human approval required.
Depends on: Phase 1.5; Phase 5.2.

---

## RISK 9 — CREATIVE OUTPUT TRACEABILITY: Majik/ACE/REAPER Artifacts Without Source Link
Evidence: Architecture definition (§1 — purpose; §10 — projectSHURA imports only distilled canonical knowledge, not entire historical corpus). Majik session artifacts (`sessions.json`, `library.json`, `conversations.json`, `Audio/`, `StemSessions/`) exist but are not linked back to source identity/context versions.
Status: Confirmed working (Majik artifacts exist); Theoretical / needs research (traceability mechanism); Installed but unverified (whether artifacts include provenance metadata).
Severity: **MEDIUM** — The architecture's core principle: "All important knowledge remains traceable back to its original source." If creative artifacts (music stems, MIDI, session files) are produced without linking to the identity version (`SOUL.md`), operating manual version (`OPERATING.md`), project context (`AGENTS.md`), and skill version (`skills/shura/`), the historical continuity is broken.
Conflict: Majik's session format (`Studio.mstudio`) and conversation history (`conversations.json`) may not include external provenance references. REAPER project files (`.rpp`) also do not include external provenance by default. A creative artifact produced by SHURA must be traceable to the identity/context that produced it.
Mitigation: Define a provenance metadata layer (either embedded in session/project files, or stored in an external index file linked to each artifact): identity version (`SOUL.md` hash / timestamp), operating manual version, active model/provider, project context reference (`AGENTS.md`), skill activation state, user approval status (`approvals`). Automatable (metadata generation); requires design agreement (human approval).
Depends on: Phase 2.1 (Majik verification); Phase 2.4 (REAPER integration); Phase 3.3 (ATLAS retrieval); Phase 5.2 (continuity audit).

---

## RISK SUMMARY MATRIX (ordered by severity)

| Risk ID | Severity | Category | Status | Phase dependency | Human approval? |
|---|---|---|---|---|---|
| 1 — Majik MCP auth | High | Integration / Live failure | IBU / TR | 0.1, 2.1 | Y (creative output) |
| 3 — REAPER agent unverified | High | Architecture gap / Milestone blocker | TR / IBU | 0.4, 2.3, 2.4 | Y (production output, architecture) |
| 8 — Tirith `fail_open` | High | Security / Governance | IBU / TR | 1.5, 5.2 | Y (security change) |
| 4 — ACE Studio unverified | Medium | Architecture assumption gap | IBU / TR | 0.5, 2.2 | Y (architecture revision) |
| 5 — ATLAS / FORGE ambiguity | Medium | Architecture / Source traceability | IBU | 0.6, 0.7, 3.1, 3.2 | Y (canonical definition) |
| 7 — Crush / Hermes overlap | Medium | Agent orchestration | IBU / TR | 1.4, 3.3 | Y (agent architecture) |
| 2 — Model/provider drift | Medium | Identity substrate | IBU / CW | 0.3, 1.1 | Y (provider/model) |
| 9 — Creative artifact provenance | Medium | Continuity / Source traceability | IBU / TR | 2.1, 2.4, 5.2 | N (design) / Y (implementation) |
| 6 — Identity file duplication | Low | Continuity / Confusion | CW / IBU | 0.8, 5.1 | N (sync automation) / Y (version change) |

## CONFLICT RESOLUTION PRINCIPLE (from `SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` §4 — target architecture; `IDENTITY_MANIFEST.md` — protected vs mutable fields; `OPERATING.md` §3 — think before acting)
When a risk requires a decision that affects identity, architecture, or creative production:
1. Inspect evidence first (this audit, live tool results, file contents).
2. Identify smallest coherent change that resolves the conflict without rewriting identity.
3. Preserve reversibility (do not delete without archive; do not overwrite without version; do not commit secrets; do not change provider/model without documentation).
4. Obtain human approval for identity, architecture, or external-visible creative changes.
5. Document the resolution (update architecture spec; label version; update integration matrix; record provenance).
6. Verify after change (test the integration; inspect the result; confirm identity consistency).

This principle applies directly to: 0.1 (auth fix), 0.3 (provider/model), 0.6/0.7 (canonical repo), 2.1 (Majik verification), 2.4 (REAPER build), 2.5 (architecture update), 4.4 (v1.0 release), 5.1 (identity versioning), and any future identity edit.
