# INTEGRATION MATRIX — SHURA Creative / Technical Ecosystem
Status: v1 audit matrix — 2026-09-12 · All claims tied to evidence sources.

Every entry has:
- Component name
- Status (CW / IBU / ABI / TR) — Confirmed Working / Installed But Unverified / Available But Not Installed / Theoretical (needs research)
- Evidence source (path / command output / file content reference)
- Integration contract type (Identity / Memory / Skill / MCP / Editor / DAW / Voice / Security / Architecture)
- Dependency chain (prerequisite phases from IMPLEMENTATION_ROADMAP.md)
- Human approval required? (Y/N)
- Notes / risks / conflicts

---

## 1. HERMES (Agent / Command Center)

### 1.1 Hermes Agent runtime
Status: CW · Source: `hermes --version` (v0.21.1), `/Users/ultraviollett/.local/bin/hermes`, `/Users/ultraviollett/.hermes/hermes-agent` · Type: Runtime / Identity substrate · Deps: None · Approval: Y (provider/model changes) · Note: 418 commits behind upstream; `hermes update` not executed.

### 1.2 Hermes config (`config.yaml`)
Status: CW · Source: `read_file` (4,057 lines, version 41) · Type: Identity / Memory / Skill / MCP / Security · Deps: 0.1, 0.3 · Approval: Y (model/provider/memory/auth changes) · Note: `mcp_servers` block present (Majik auth interpolation broken); `display.personality: uwu` cosmetic; `model.default` (poolside/laguna) does not match active session model (`inkling` / openrouter).

### 1.3 Hermes memory / state (`state.db`)
Status: CW (configured) / IBU (content) · Source: `config.yaml` (`memory_enabled: true`); SQLite file `~/.hermes/state.db` (not inspected) · Type: Memory · Deps: 0.8, 1.2 · Approval: N (inspection) / Y (governance change) · Note: Memory governance rules (`OPERATING.md` §7) require provenance/classification.

### 1.4 Hermes skills loader / activation
Status: IBU · Source: `skills/` inventory; `skills/shura/SKILL.md`; `plugins/superpowers/` (14 skills loaded) · Type: Skill · Deps: 0.8, 1.3 · Approval: Y (activation rules) · Note: Activation behavior for `skills/shura` depends on loader; `brainstorming` / `systematic-debugging` triggered in session.

### 1.5 Hermes CLI (`hermes-cli` toolset)
Status: CW · Source: `config.yaml` (`toolsets: hermes-cli, web`) · Type: Skill / Execution · Deps: None · Approval: N · Note: `terminal` backend local; `code_execution` mode `project`.

---

## 2. SHURA IDENTITY / CONTEXT LAYER

### 2.1 SHURA identity kernel (`SOUL.md`)
Status: CW · Source: `~/.hermes/SOUL.md` (225 lines, v1) · Type: Identity · Deps: 0.8 · Approval: Y (identity edit required by versioning rule §15) · Note: Canonical live identity; consistent with `projectSHURA/docs/shura/SOUL.md`.

### 2.2 SHURA identity manifest (`IDENTITY_MANIFEST.md`)
Status: CW · Source: `projectSHURA/docs/shura/IDENTITY_MANIFEST.md` (122 lines) · Type: Architecture / Identity · Deps: 0.8 · Approval: Y (layer definition change) · Note: Defines protected vs mutable fields; requires synchronization with `SOUL.md`.

### 2.3 SHURA operating manual (`OPERATING.md`)
Status: CW · Source: `projectSHURA/docs/shura/OPERATING.md` (276 lines) · Type: Behavior / Memory governance / Tool selection / Anti-patterns · Deps: 0.8 · Approval: N (operational behavior) / Y (principle change) · Note: Defines `think → identify leverage → propose/act → verify → reflect` loop; includes anti-sycophancy, memory editorial rules, release gate.

### 2.4 SHURA Hermes skill (`skills/shura`)
Status: IBU · Source: `SKILL.md` (4,499 chars); `.shura-preflight-...` backup · Type: Skill / Routing · Deps: 0.8, 1.3 · Approval: N · Note: Routing layer (not identity replacement); defines creative workflow (`Majik/ACE → REAPER`) and coding workflow (`inspect → edit → test → review`).

### 2.5 SHURA project agent constitution (`AGENTS.md`)
Status: CW · Source: `projectSHURA/AGENTS.md` · Type: Project rules / Governance · Deps: 1.4 · Approval: N · Note: Hard rules: never commit secrets; prefer reversible; preserve mood system; keep identity separate from implementation.

---

## 3. SKILLS (Custom / Installed)

### 3.1 `shura` skill
Status: IBU (activation unverified in all surfaces) · Source: `~/.hermes/skills/shura/SKILL.md` · Type: Skill / Routing · Deps: 0.8, 1.3 · Approval: Y (behavior profile change) · Note: Defines `understand → identify leverage → propose/act → verify → reflect` pattern; no identity override.

### 3.2 `superpowers` plugin skills (14 skills)
Status: CW · Source: `plugins/superpowers/skills/` directory listing · Type: Skill / Process / Execution · Deps: None · Approval: N · Note: `brainstorming`, `systematic-debugging`, `verification-before-completion`, `writing-plans`, `writing-skills`, `dispatching-parallel-agents` loaded and used in this audit.

### 3.3 Creative skills (20 categories under `skills/creative/`)
Status: IBU · Source: `skills/creative/` directory listing (`ascii-art`, `comfyui`, `manim-video`, `p5js`, `songwriting-and-ai-music`) · Type: Skill · Deps: 2.1 (if creative workflow verified) · Approval: N · Note: Installed; not executed in audit.

### 3.4 MCP skill package (`skills/mcp/`)
Status: IBU · Source: `skills/mcp/` directory; `references/native-mcp.md` · Type: Skill / Integration · Deps: 0.1 (auth), 2.1 (Majik verification) · Approval: N · Note: References native MCP client; `mcporter` separate.

---

## 4. MCP SERVERS / EXTERNAL INTEGRATIONS

### 4.1 `hugging_face` MCP (`https://huggingface.co/mcp`)
Status: CW (configured) / IBU (connection unverified) · Source: `config.yaml` (`mcp_servers.hugging_face`); `auth.json` exists but content unverified · Type: MCP / External service · Deps: 0.1 (if needed for identity-independent retrieval) · Approval: N · Note: OAuth auth; no session-level verification.

### 4.2 `amplitude` MCP (`https://mcp.amplitude.com/mcp`)
Status: CW (configured) / IBU (connection unverified) · Source: `config.yaml` (`mcp_servers.amplitude`) · Type: MCP / External service · Deps: None · Approval: N · Note: OAuth auth; no session-level verification.

### 4.3 `majiks-studio` MCP (`localhost:8478`)
Status: IBU (installed) / TR (connection unverified; auth interpolation broken) · Source: `config.yaml` (`mcp_servers.majiks-studio`); `.env` (`MCP_MAJIKS_STUDIO_API_KEY`); `Library/Preferences/com.magicunicorn.majiksmusicstudio.plist` (`majiks_studio_mcp_enabled: true`, `port: 8478`, `ace_step_path: /Users/ultraviollett/ACE-Step-1.5`) · Type: MCP / DAW (Majik) · Deps: 0.1 (auth fix), 2.1 (verification) · Approval: Y (creative workflow produces artifacts) · Note: **CRITICAL RISK**: `Authorization: Bearer ${MCP_...KEY}` does not match `.env` variable `MCP_MAJIKS_STUDIO_API_KEY`. Interpolation likely broken. Majik preferences confirm integration intended (MCP enabled + ACE Step path configured).

### 4.4 ACE Step integration (via Majik)
Status: IBU · Source: Majik preferences (`majik_ace_step_path`) · Type: DAW / Generative (vocal/performance) · Deps: 2.2 (ACE Studio capability verification) · Approval: Y · Note: ACE Studio 2.1.1 installed; no verified agent interface; Majik's `ACE Step` integration is a separate component (`ACE-Step-1.5` directory referenced) — its capabilities unverified.

---

## 5. CREATIVE / PRODUCTION TOOLS (DAW / MUSIC / AUDIO)

### 5.1 Majik Music Studio (DAW / generative music)
Status: CW (installed) / IBU (MCP connection) · Source: `/Applications/Majiks Music Studio.app`; preferences (`mcp_enabled`, `mcp_port`, `ace_step_path`); `.env` key present · Type: DAW / MCP endpoint · Deps: 0.1 (auth fix), 2.1 (MCP verification) · Approval: Y (creative output) · Note: Design target (§4.C architecture spec): granular, composable MCP actions (project, track, transport, audio/MIDI import/export/edit, instrument/plugin, parameter control, sample/library, render, mix). No verified tool family list yet.

### 5.2 ACE Studio (vocal / performance environment — design target)
Status: IBU (installed) / TR (agent interface unverified) · Source: `/Applications/ACE Studio.app`; preferences minimal (`AppleLanguages`) · Type: DAW / Voice · Deps: 0.5 (capability report) · Approval: Y · Note: Architecture spec (§4.C / §5) assumes ACE Studio as alternative/specialized vocal/performance environment. If interface unavailable, architecture assumption must be updated.

### 5.3 REAPER (production environment — arrangement / editing / mixing / mastering)
Status: CW (installed) / TR (agent interface unverified) · Source: `/Applications/REAPER.app`; `Library/Application Support/REAPER/` (scripts/plugins/config) · Type: DAW / Production · Deps: 0.4 (scripting/API exposure plan), 2.3 (REAPER integration decision), 2.4 (MCP primitives) · Approval: Y (production output) · Note: Architecture spec (§4.C) defines granular REAPER tool families; no REAPER MCP server configured; no verified scripting bridge (ReaScript Python / LUA / OSC). **Highest-priority unverified creative integration.**

---

## 6. EDITOR / DEVELOPMENT INTEGRATION

### 6.1 Zed (editor / ACP server target)
Status: IBU · Source: `/Applications/Zed.app`; `/usr/local/bin/zed` · Type: Editor / Agent server · Deps: 1.4 (end-to-end dev task) · Approval: N (editor integration) / Y (if changes identity layer) · Note: Architecture spec (§4.A) designates Hermes + Zed as primary cockpit. ACP server (`agent-server`) integration not verified.

### 6.2 VS Code / Codex (`code` CLI)
Status: ABI · Source: `code` CLI not found (`which code` returned `not found`) · Type: Editor / Agent · Deps: 1.4 (if needed) · Approval: N · Note: Not installed; can be installed if needed for additional agent routing.

### 6.3 Crush agent framework (`.crush/`)
Status: IBU · Source: `projectSHURA/.crush/` (DB `crush.db`, `crush.log`, `.crushrc`) · Type: Agent framework (separate) · Deps: 1.4 (end-to-end dev task — clarify integration) · Approval: Y (affects agent orchestration architecture) · Note: Separate agent framework; not integrated with Hermes; must either be integrated (via delegation, MCP, or custom toolset) or clearly documented as separate experiment.

---

## 7. ARCHITECTURE / KNOWLEDGE / GOVERNANCE REPOS

### 7.1 `ATLAS.project` (canonical knowledge / architecture layer — design)
Status: CW (repo exists) / IBU (mostly empty) · Source: `/Users/ultraviollett/ATLAS.project/` (`.git`, `README.md` 8 bytes, `AGENTS.md` empty, `docs/` empty) · Type: Architecture / Knowledge corpus · Deps: 0.6 (canonical choice), 3.1 (content) · Approval: Y (canonical definition affects architecture identity) · Note: Identity manifest (`IDENTITY_MANIFEST.md`) defines ATLAS role; repo content missing.

### 7.2 `FORGE.project` (synthesis / audit / evaluation — design)
Status: IBU (repo exists, empty) / CW (content in `shura-forge/SHURA-ATLAS/`) · Source: `/Users/ultraviollett/FORGE.project/` (empty); `Projects/shura-forge/SHURA-ATLAS/FSI.md`, `Vol.I/`, `Vol.II/` · Type: Synthesis / Conflict resolution / Canonization · Deps: 0.7 (canonical choice), 3.2 (content) · Approval: Y · Note: `FSI.md` (heartbeat) exists in `shura-forge`; repository needs either content migration or retirement.

### 7.3 `projectSHURA` (runtime / identity implementation — confirmed)
Status: CW · Source: `/Users/ultraviollett/projectSHURA/` (git repo, `.env`, `.gitignore`, `README.md`, `Makefile`, `.crush/`, `docs/`, `src/core/`, `.venv`) · Type: Runtime / Identity / Creative / Technical hub · Deps: None · Approval: Y (any identity or architecture change) · Note: Primary repository for SHURA development. Contains both architecture docs (`docs/SHURA_V1...`) and source (`src/core/`). `.crush/` separate framework coexists.

---

## 8. VOICE / MEDIA / INTERACTIVE

### 8.1 Voice (STT) — `openai` (`whisper-1`)
Status: IBU · Source: `config.yaml` (`stt.provider: openai`, `model: whisper-1`) · Type: Voice / Input · Deps: 4.1 (live test) · Approval: N · Note: Configured; not exercised.

### 8.2 Voice (TTS) — `openai` (`gpt-4o-mini-tts`, `alloy`)
Status: IBU · Source: `config.yaml` (`tts.provider: openai`, `model: gpt-4o-mini-tts`, `voice: alloy`) · Type: Voice / Output · Deps: 4.1 · Approval: N · Note: Configured; identity preservation across TTS outputs unverified.

### 8.3 Voice gateway (`use_gateway: true` for STT and TTS)
Status: IBU · Source: `config.yaml` (`stt.use_gateway: true`, `tts.use_gateway: true`) · Type: Integration / Routing · Deps: 0.1, 1.1 · Approval: N · Note: Gateway routing unverified.

---

## 9. SECURITY / PRIVACY / GOVERNANCE

### 9.1 Secret redaction (`redact_secrets: true`)
Status: CW (configured) / IBU (behavior unverified) · Source: `config.yaml` (`security.redact_secrets: true`) · Type: Security · Deps: None · Approval: N · Note: `.env` secrets present (`MCP_MAJIKS_STUDIO_API_KEY`); config does not contain secrets (verified by inspection). Redaction behavior in actual tool outputs unverified.

### 9.2 Tirith (`tirith_enabled: true`)
Status: IBU · Source: `config.yaml` (`security.tirith_enabled: true`, `tirith_path: tirith`, `timeout: 5`, `fail_open: true`) · Type: Security / Approval · Deps: None · Approval: Y (if approval mode changes) · Note: `fail_open: true` — security gate opens on failure. Should be verified whether this is intended behavior.

### 9.3 Approvals (`mode: manual`, `timeout: 60`)
Status: CW · Source: `config.yaml` (`approvals.mode: manual`) · Type: Governance / Security · Deps: 1.5 (release gate) · Approval: Y (approval mode change) · Note: Manual approval required for destructive/external actions; automated tasks allowed within boundaries.

---

## 10. DUPLICATE / CONFLICT / RETIREMENT REFERENCES

| Component | Conflict / Retirement action | Evidence source | Resolution dependency |
|---|---|---|---|
| `MCP_...KEY` interpolation (Majik auth) | Fix interpolation; verify connection | Config + `.env` mismatch | 0.1 |
| `pre-majik` config backup (no rollback doc) | Document rollback; label migration | Backup file present; no rollback doc | 0.2 |
| `Shura/` (older directory) | Archive; retire from active use | `Shura/OPERATING_MANUAL.md` vs `projectSHURA/docs/shura/OPERATING.md` | 0.8 |
| `projectSHURA/docs/architecture.md` (superseded) | Update / delete | `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` supersedes | 0.9 |
| `ATLAS.project` (scaffold) + `FORGE.project` (scaffold) + `shura-forge/SHURA-ATLAS` (content) | Designate canonical; migrate or archive others | Repo structures + content inspection | 0.6, 0.7 |
| `Crush` (`.crush/`) + Hermes (`hermes-agent`) | Integrate or clearly separate | `.crush/` DB + Hermes source | 1.4 |
| Model/provider drift (`omniroute` default vs active `inkling`) | Document active config; stabilize | `config.yaml` vs session evidence | 0.3, 1.1 |
| REAPER agent interface (design target; no verified implementation) | Research scripting; plan bridge; build only after plan | `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` §4.C; REAPER installation evidence | 0.4, 2.3, 2.4 |
| ACE Studio agent interface (assumed; unverified) | Verify interface existence; update architecture if unavailable | ACE Studio preferences; app presence | 0.5, 2.2 |
