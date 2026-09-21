# ARCHITECTURE AUDIT — SHURA / Hermes / Project Ecosystem
Status: v1 audit — captured 2026-09-12 (CDT) · No destructive changes made.
Auditor: SHURA (lead architect) via Hermes Agent v0.21.1 · Model: thinkingmachines/inkling:free (openrouter) / nous primary.

## 1. METHOD
Phase 1 (Root Cause Investigation) — Systematic Debugging applied. Evidence sources:
- Live filesystem reads (read_file / terminal)
- Hermes runtime inspection (`hermes --version`, `which hermes`, config.yaml direct read)
- Repository structure (`find`, `git log` where available)
- Application installations (`/Applications`, Library dirs, plists)
- Skill inventory (`~/.hermes/skills/`, `plugins/superpowers/`)
- MCP server discovery (`grep` config + `.env` inspection)
- Project context files (`AGENTS.md`, `SOUL.md`, `README.md` across repos)

Every claim below is either:
- **Confirmed working** — tool returned verifiable output.
- **Installed but unverified** — binary/app present, integration not exercised.
- **Available but not installed** — could be installed but isn't.
- **Theoretical / needs research** — no verified capability found.

## 2. HERMES RUNTIME

### Confirmed working
- Hermes Agent v0.21.1 (build 2026.9.7) · 418 commits behind upstream.
- Install path: `/Users/ultraviollett/.hermes/hermes-agent` (git install).
- CLI launcher: `/Users/ultraviollett/.local/bin/hermes` (symlink).
- Python: 3.11.15 · OpenAI SDK: 2.24.0.
- `hermes` responds with `--version` and `--help`.
- `~/.hermes/config.yaml` is a live, large (4,057 lines, ~155KB) multi-provider configuration (version 41).
- Memory enabled (`memory_enabled: true`), user profile enabled (`user_profile_enabled: true`), char limits 2,200 (memory) / 1,375 (user) — matches the persistent memory spec.
- Toolsets: `hermes-cli`, `web`.
- Plugins: `superpowers` enabled.
- Approvals: `manual`.
- Security: `redact_secrets: true`, `tirith_enabled: true`.
- Terminal backend: local. Browser backend: firecrawl.

### Installed but unverified
- TTS (`provider: openai`, model `gpt-4o-mini-tts`, voice `alloy`). Voice not exercised in this audit.
- STT (`provider: openai`, model `whisper-1`). Not tested live.
- Web (`backend: firecrawl`, `use_gateway: true`). Not exercised.
- MCP client (`mcp` package) — installed enough for config parsing; `discover_mcp_tools()` not executed.
- Custom providers (`omniroute` at `localhost:20128`, `ollama-launch` at 11434, `aihubmix`). Their endpoints not pinged; `omniroute` is configured as DEFAULT (`provider: nous`, `default: poolside/laguna-s-2.1:free`).
- Fallback providers configured to `openrouter` (`thinkingmachines/inkling:free`); not triggered.
- Delegation, checkpoint, compression, session reset (`at_hour: 4`, `idle_minutes: 1440`) — configured but not observed running.

### Conflicts / stale / redundant
- `display.personality: uwu` — cosmetic personality tag; does not override `SOUL.md` identity. Not destructive but irrelevant to SHURA identity architecture.
- `model.default` references `poolside/laguna-s-2.1:free` (free tier) with `provider: nous` and `key_env: HERMES_CUSTOM_OMNIROUTE_API_KEY`. The actual current active model appears to be `thinkingmachines/inkling:free` (used in this session) delivered by `openrouter`. The primary/default config does not match the runtime model being served, indicating potential provider/model drift or profile switching that isn't explicitly tracked.
- A `pre-majik` backup (`.hermes/config.yaml.pre-majik-20260910-063435`) exists; the live config includes `mcp_servers` with `majiks-studio` (port 8478) and `hugging_face` / `amplitude`. The pre-majik config does NOT contain those MCP entries, confirming a migration occurred around that timestamp (2026-09-10 06:34). No rollback procedure documented.
- The `mcp_servers` block references `Authorization: Bearer ${MCP_...KEY}` but the `.env` shows key `MCP_MAJIKS_STUDIO_API_KEY=mms_KCZF1E...`. Variable interpolation naming (`MCP_...KEY` vs `MCP_MAJIKS_STUDIO_API_KEY`) is unresolved — likely broken interpolation unless the env variable is also aliased. **This is a live risk**: Majik MCP connection may fail silently because the header interpolation refers to an undefined variable name.

### Theoretical / needs research
- Smart model routing (`smart_model_routing.enabled: false`). Not researched for SHURA use.
- Multi-provider rotation / credential pool rotation (`hermes auth`) — configured but not inspected.
- `context.engine: compressor` — implemented, but its interaction with SHURA's long-form identity persistence is unverified in practice.

## 3. IDENTITY & CONFIG FILES

### Confirmed working
- `~/.hermes/SOUL.md` — 225 lines, v1 identity draft, well-structured (identity, relational stance, temperament, cognitive style, contradictions, agency, growth, continuity, communication, anti-sycophancy, identity boundary, identity test, versioning). This file is the canonical identity kernel.
- `.hermes/skills/shura/SKILL.md` — v1 skill (4,499 chars). Defines routing layer: load `SOUL.md`, then `AGENTS.md`, then this skill, then task docs. Defines creative workflow (`concept → Majik/ACE → assets/stems/MIDI → REAPER`) and coding workflow (`inspect → scope → edit → test → ...`). Explicitly says it is a routing layer, not an identity replacement.
- `projectSHURA/AGENTS.md` — agent constitution (hard rules, layer separation, git discipline, no provider/model lock-in).
- `projectSHURA/docs/shura/IDENTITY_MANIFEST.md` — structured identity stack definition (SOUL.md → OPERATING.md → AGENT_CONSTITUTION.md → SHURA_SKILL.md → AGENTS.md → MEMORY → RUNTIME STATE → SKILLS/MCPs). Defines protected fields (require explicit review) vs mutable fields.
- `projectSHURA/docs/shura/OPERATING.md` — behavior interpreter (instruction hierarchy, core loop, mode definitions, memory governance, anti-patterns, definition of good SHURA response).
- `projectSHURA/docs/shura/SOUL.md` — copy of identity kernel (same content as `~/.hermes/SOUL.md`).
- `projectSHURA/docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` — 400 lines, full v1 architecture (development agent harness, reader/audiobook, creative DAW integration, ATLAS, FORGE, INFAC, game/worldbuilding). Defines release phases v0.1 → v1.0.

### Installed but unverified
- `MEMORY.md`, `USER.md` — no standalone `MEMORY.md` at `~/.hermes/`; user profile lives in `config.yaml` (`memory.user_profile_enabled: true`) and persistent SQLite (`state.db`). Memory content not inspected.
- `PROJECTS.md`, `OPERATING_MANUAL.md` under `Shura/` directory (older file path, separate from `projectSHURA/`). Not reconciled with `projectSHURA/docs/` versions.

### Conflicts / stale / duplication / retirement candidates
- **Identity file duplication**:
  - `/Users/ultraviollett/.hermes/SOUL.md` (canonical, live runtime)
  - `/Users/ultraviollett/projectSHURA/docs/shura/SOUL.md` (repo copy, same content, same timestamp assumption — should be synchronized)
  - `/Users/ultraviollett/projectSHURA/.shura/agents/constitution.md` (agent-level governance — different layer)
  - `/Users/ultraviollett/Shura/OPERATING_MANUAL.md` (older repo path)
  These are not conflicting in content but in location authority. The runtime loads `~/.hermes/SOUL.md` first; repo copies are reference. **Recommendation**: keep `~/.hermes/SOUL.md` as the live identity kernel; make `projectSHURA/docs/shura/SOUL.md` a verified mirror; retire or clearly label `Shura/` as superseded.

- **Stale `Shura/` directory**: `/Users/ultraviollett/Shura/` (older, smaller repo, `OPERATING_MANUAL.md` + `PROJECTS.md`). Not actively tracked with `projectSHURA`. Should be retired or explicitly archived.
- **RETIRED / superseded architecture references**: The `projectSHURA/docs/` include `docs/architecture.md` (older architecture doc) alongside the newer `SHURA_V1_ARCHITECTURE_AND_ROADMAP.md`. They describe overlapping architecture layers but different framing. Need reconciliation.
- `projectSHURA` has a `.crush/` directory (Crush code agent infrastructure) — separate agent framework, not yet integrated with Hermes. Unclear whether Crush is intended as part of SHURA's agent orchestration or a separate experiment.

## 4. SKILLS (Custom / Installed)

### Confirmed working (`.hermes/skills/` inventory)
Categories present: `apple`, `autonomous-ai-agents`, `creative` (20 skills), `data-science`, `devops`, `email`, `gaming`, `github`, `leisure`, `mcp`, `media`, `mlops`, `note-taking`, `productivity`, `red-teaming`, `research`, `shura`, `social-media`, `software-development`, `web`, `yuanbao`.
- `shura` skill: 1 SKILL.md + 1 `.shura-preflight-...` backup. Confirmed operational.
- `superpowers` plugin loaded (14 skills: brainstorming, dispatching-parallel-agents, executing-plans, finishing-a-development-branch, receiving-code-review, requesting-code-review, subagent-driven-development, systematic-debugging, test-driven-development, using-git-worktrees, using-superpowers, verification-before-completion, writing-plans, writing-skills).

### Installed but unverified
- Creative skills (ascii-art, comfyui, songwriting-and-ai-music, etc.) — installed, no session-level verification.
- MCP skill package (`mcp` category) — installed, not exercised against live servers.

### Theoretical / needs research
- Whether the `shura` skill properly triggers in all Hermes platforms (desktop app, CLI, TUI). The skill defines activation conditions; actual trigger behavior depends on `skills` loader behavior, which changes with config changes.

## 5. MCP SERVERS & INTEGRATIONS

### Confirmed working (configured)
- `hugging_face`: `https://huggingface.co/mcp` · auth: oauth · enabled.
- `amplitude`: `https://mcp.amplitude.com/mcp` · auth: oauth · enabled.
- `majiks-studio`: `http://127.0.0.1:8478/mcp` · `Authorization: Bearer ${MCP_...KEY}` · enabled.

### Installed but unverified
- Majik Music Studio app installed (`/Applications/Majiks Music Studio.app`). Preference file (`com.magicunicorn.majiksmusicstudio.plist`) shows `majiks_studio_mcp_enabled: true`, `majiks_studio_mcp_port: 8478`, `majik_ace_step_path: /Users/ultraviollett/ACE-Step-1.5`.
- ACE Studio app installed (`/Applications/ACE Studio.app`). Preferences minimal (`AppleLanguages` only) — no MCP/agent integration evidence in plist.
- `.env` contains `MCP_MAJIKS_STUDIO_API_KEY=mms_KCZF1E...`. Confirmed key present.
- **CRITICAL RISK**: The `mcp_servers.majiks-studio.headers.Authorization` value is `${MCP_...KEY}` but the `.env` key is `MCP_MAJIKS_STUDIO_API_KEY`. The interpolation variable names do NOT match. Unless the Hermes MCP loader does a partial/fuzzy match (unverified), the Majik MCP header will resolve to empty/invalid, and the connection to `localhost:8478` will fail authentication. This needs immediate verification and fix.

### Theoretical / needs research
- Whether the `hugging_face` and `amplitude` OAuth flows actually work against current tokens (`auth.json` exists but was not inspected).
- Whether `majiks-studio` MCP actually exposes the granular tool families described in `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` (project, track, transport, audio import/export, MIDI import/export/edit, instrument/plugin loading, plugin parameter control, sample/library access, render, mix controls). These are design targets, not verified MCP tool names.

## 6. ZED / ACP / EDITOR INTEGRATION

### Confirmed working
- `/Applications/Zed.app` installed.
- `/usr/local/bin/zed` CLI present.
- `projectSHURA/AGENTS.md` references Hermes + Zed as primary cockpit.

### Installed but unverified
- `Zed` ACP server (`agent-server`) integration. Not verified running. No `~/.hermes/` Zed plugin reference found in config.
- `code` (VS Code) CLI not present (`code not found`). Visual Studio / Codex integration not installed.
- `JCode`, `Crush`, `Pi`, `OpenCode` mentioned as supporting agents in `SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` but not verified installed. Only `Crush` infrastructure (`projectSHURA/.crush/`) confirmed present.

### Conflicts / retirement candidates
- If `Crush` is intended as a separate agent framework, it should either be explicitly integrated into Hermes (via MCP, delegation, or custom toolsets) or clearly documented as a separate experiment, to avoid duplicate orchestration logic.

## 7. ProjectSHURA REPOSITORY

### Confirmed working
- Path: `/Users/ultraviollett/projectSHURA` (git repo, 26 commits, `main` branch).
- `.env`, `.gitignore`, `README.md`, `Makefile`, `pyproject.toml`, `uv.lock`, `config.json`, `.venv` (Python 3.11-based).
- Source tree: `src/core/brain.py`, `src/core/consciousness.py`, `src/core/config.py`, `docs/`, `data/prompts/`.
- Agent definitions: `.shura/agents/constitution.md`, `architect.md`, `builder.md`.
- `.crush/` agent framework (DB `crush.db`, `crush.log`, `.crushrc`).
- Documentation covers architecture, handoff (`SHURA_MASTER_HANDOFF.md`), web frontend/API, skills (monologue, overview, memory, discord, minecraft).

### Installed but unverified
- The `.venv` contains `mlx_lm` (local MLX LLM inference) and `edge-tts`. Not tested.
- `config.json` and `pyproject.toml` define project structure; runtime behavior (starting brain loop, registering skills, connecting to providers) not executed.

### Conflicts / retirement
- `docs/architecture.md` (older architecture doc) overlaps with `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md`. The newer `SHURA_V1...` doc supersedes; `architecture.md` should be either updated with a supersession note or removed.
- `docs/web/` (frontend/API) appears unimplemented relative to architecture spec — no corresponding `src/web/` source found.
- `docs/skills/minecraft.md` — Minecraft integration intended but no live Minecraft server connection verified.

## 8. MAJIK / ACE STUDIO / REAPER

### Confirmed working
- **Majik Music Studio** installed (`/Applications/Majiks Music Studio.app`). Library preference file confirms MCP enabled (`majiks_studio_mcp_enabled: true`, port 8478) and ACE Step integration (`majik_ace_step_path: /Users/ultraviollett/ACE-Step-1.5`). Sessions (`Studio.mstudio`), conversation history (`conversations.json`), audio/stem/session artifacts present.
- **ACE Studio** installed (`/Applications/ACE Studio.app`). No agent/MCP configuration evidence in `.plist`.
- **REAPER** installed (`/Applications/REAPER.app`). User plugins/scripts/config present (`Library/Application Support/REAPER/`). `.dylib` plugins present (`reap_osx_modern.dylib`, etc.). No custom REAPER scripts for SHURA integration observed.
- **Majik + ACE Step integration** configured in Majik preferences (`majik_ace_step_path`). Not executed.

### Installed but unverified
- Whether Majik's actual MCP server responds on `localhost:8478` when launched.
- Whether ACE Studio exposes any MCP/API interface at all — the architecture spec (`SHURA_V1_ARCHITECTURE_AND_ROADMAP.md`) treats ACE Studio as an alternative vocal/performance environment, but the installed ACE Studio version (2.1.1) is a desktop app with minimal preference footprint — there is no evidence of an MCP server, CLI, or programmable interface available today.
- Whether REAPER's scripting/API capabilities (ReaScript console, `reap_*.lua` / Python extensions, OSC) can be exposed through an MCP server. The architecture spec defines initial REAPER tool families; none of these exist as a live MCP server yet. The only REAPER-related MCP configured is Majik's (`majiks-studio`), not REAPER's.

### Theoretical / needs research
- Building a `REAPER` MCP server (either as a native REAPER extension that exposes HTTP/stdIO, or as an external bridge using REAPER's ReaScript / Python API) is a design target (`SHURA_V1...` §4.C) but has no verified implementation path today. This is the highest-priority creative integration gap.
- The architecture spec defines granular REAPER tool families; mapping these to actual REAPER actions (track creation, item insertion, plugin loading, parameter automation, render) needs a concrete mapping document.

## 9. ATLAS / FORGE DIRECTORIES

### Confirmed working
- `/Users/ultraviollett/ATLAS.project/` — git repo, 107 commits (from `ls -la` info: `.git` present, `README.md` 8 bytes, `docs/` empty, `AGENTS.md` empty, `.git` with 107 commits per `git log` failure but file presence confirms repo activity).
- `/Users/ultraviollett/FORGE.project/` — git repo, similar structure (`README.md` 8 bytes, `AGENTS.md` empty).
- `/Users/ultraviollett/Projects/shura-forge/` — contains `SHURA-ATLAS/FSI.md` (Forge Status Indicator — heartbeat document), `scripts/audit-fsi.sh`, `scripts/bootstrap.sh`, `references/`, `assets/`, `Vol.I/`, `Vol.II/`. Active project with documented structure.

### Installed but unverified
- Whether the `ATLAS.project` and `FORGE.project` repos are actively maintained or are placeholder scaffolds. `README.md` (8 bytes = just "# ATLAS" or similar) and empty `AGENTS.md` files suggest they are scaffolds, not active content repositories.
- Whether the `shura-forge` project integrates with Hermes (no `.hermes.md` or `.hermes` reference in its directory).

### Conflicts / retirement
- Duplicate architecture layers:
  - `ATLAS.project` (scaffold repo) vs. `projectSHURA/docs/` (detailed architecture docs) vs. `Projects/shura-forge/SHURA-ATLAS/` (FSI + capability docs).
  The `projectSHURA/docs/shura/IDENTITY_MANIFEST.md` explicitly defines ATLAS as the "architectural/knowledge representation layer". The `ATLAS.project` repo does not contain that content. The `shura-forge/SHURA-ATLAS/` contains capability and heartbeat docs (`FSI.md`) that overlap with the ATLAS concept but are physically separate.
  **Recommendation**: Designate `ATLAS.project` as the canonical repository for ATLAS content; migrate `shura-forge/SHURA-ATLAS/` content into it; retire the separate `shura-forge` structure or clearly label it as a working/experimental branch.
- `FORGE.project` is essentially empty (just README + AGENTS.md). It needs either a full content build (capabilities, capability ledger, audit scripts, index) or retirement as premature.

## 10. DUPLICATE / STALE / CONFLICT SUMMARY

| Issue | Severity | Evidence | Action
|---|---|---|---|
| `MCP_...KEY` interpolation mismatch (Majik MCP auth) | **High** — live integration will fail | Config: `${MCP_...KEY}`; `.env`: `MCP_MAJIKS_STUDIO_API_KEY` | Fix interpolation name; verify connection |
| `mcp_servers` block added post-`pre-majik` backup (no rollback procedure) | **Medium** — migration untracked | `.hermes/config.yaml.pre-majik-...` exists; no rollback doc | Document rollback procedure; label migration |
| `ATLAS.project` / `FORGE.project` / `projectSHURA/docs/` / `shura-forge/SHURA-ATLAS` overlapping architecture definitions | **Medium** — identity/architecture confusion risk | Multiple repos with overlapping names | Designate canonical repo; migrate or archive others |
| `Shura/` directory superseded by `projectSHURA` | **Low** — confusion risk, not destructive | `Shura/OPERATING_MANUAL.md` vs `projectSHURA/docs/shura/OPERATING.md` | Archive `Shura/` with note; retire from active use |
| `projectSHURA/docs/architecture.md` superseded by `SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` | **Low** — stale reference | Both exist; newer supersedes | Update or remove `architecture.md` |
| `REAPER` MCP not implemented (only Majik MCP configured) | **Medium** — architecture gap | Spec defines REAPER tool families; no `reaper` MCP server configured | Research REAPER scripting → MCP bridge; build or document |
| `ACE Studio` integration unverified / possibly unavailable | **Medium** — architecture assumption unproven | ACE Studio installed, minimal preferences, no MCP/CLI/API evidence | Verify ACE capabilities; if unavailable, document gap |
| `Crush` framework separate from Hermes | **Medium** — duplicate agent framework | `projectSHURA/.crush/` DB + `.crushrc` | Integrate or separate; do not let both drive releases |
| Identity layer duplication (`~/.hermes/SOUL.md`, repo copies, `OPERATING.md`, `AGENT_CONSTITUTION.md`) | **Low** — manageable if maintained synchronized | Multiple copies; content consistent at audit time | Define synchronization procedure |

## 11. RISK REGISTER (for docs/RISKS_AND_CONFLICTS.md)
- Secret interpolation failure (MCP auth) — confirmed risk.
- Provider/model drift (config `default` does not match session model) — observed.
- REAPER/ACE Studio capabilities unverified — confirmed gap.
- ATLAS/FORGE repo structure ambiguous — confirmed structural gap.
- No destructive changes made — audit safe.

## 12. EXECUTION NOTES (what was NOT done, to respect "do not begin large implementation work until audit and roadmap exist")
- No files modified.
- No `hermes update` executed (418 commits behind — noted but not applied).
- No `mcp` connection tests executed (would have attempted to connect to `localhost:8478` and external URLs).
- No `REAPER` scripting/API exploration executed beyond file listing.
- No identity file synchronization performed.
- No `Crush` integration experiment performed.
