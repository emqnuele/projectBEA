# REAPER ENVIRONMENT AUDIT — AETHERWOUND / ProjectSHURA

Audit date: 2026-09-15
Audited by: SHURA (automated inspection + manual verification)
Environment: macOS 26.6.1, REAPER 7.79.0 (build 06dd787u)

---

## 1. WHAT EXISTS

### REAPER Installation
- Path: `/Applications/REAPER.app`
- Version: 7.79.0 (confirmed via `reaper-install-rev.txt`)
- User config dir: `~/Library/Application Support/REAPER/`
- Default resource path is standard (

### Existing MCP (CRITICAL FINDING)
- File: `~/Library/Application Support/REAPER/Scripts/reaper_mcp_server.lua`
- Size: ~5,392 lines (substantial, production-grade Lua script)
- Features verified by code inspection:
  - Transport handlers (play, stop, set play state)
  - Track handlers (get all, add, info, routing)
  - Project handlers (get info, save, markers)
  - FX handlers (add FX, set params, get chain)
  - Item handlers (get all, add, split, glue, select)
  - Chop/slice handlers (transient-based slicing)
  - Marker/region handlers
  - Selection handlers
  - Send/receive handlers
  - MIDI handlers
  - Compose pipeline handlers (wiping MIDI, generating)
  - Envelope/automation handlers
  - Tempo/time-signature handlers
  - Take/comp handlers
- Protocol: File-based IPC (`command.json` / `response.json` in `TMPDIR/reaper_mcp`)
- This IS a viable existing MCP. The REAPER_INTEGRATION_PLAN.md (2026-09-12) incorrectly states "no MCP server exists." The file was installed after or overlooked by that audit.

### Python ReaScript API
- File: `/Applications/REAPER.app/Contents/Plugins/reaper_python.py`
- Size: ~154 KB
- Exported functions: ~730 (`RPR_*`)
- Confirmed present; usable for Python bridge scripts.

### REAPER Scripts Directory
- `~/Library/Application Support/REAPER/Scripts/Cockos/` — default scripts
- `~/Library/Application Support/REAPER/Scripts/__startup.lua`
- `~/Library/Application Support/REAPER/Scripts/reaper_mcp_server.lua` (existing MCP)
- `~/Library/Application Support/REAPER/Scripts/Cockos/Default_6.0_theme_adjuster.lua`
- `~/Library/Application Support/REAPER/Scripts/Cockos/Default_7.0_theme_adjuster.lua`

### Themes
- Only default themes present:
  - `ColorThemes/Default_6.0.ReaperThemeZip`
  - `ColorThemes/Default_7.0.ReaperThemeZip`
- No custom AETHERWOUND theme exists.

### Keymaps / Shortcuts
- `~/Library/Application Support/REAPER/KeyMaps/DK keymap.ReaperKeyMap` (only one custom keymap found; content not fully inspected)
- Default shortcuts active; no AETHERWOUND-specific keymap.

### Config Files
- `reaper.ini` — minimal (transport/mixer settings, no theme customization, no custom actions)
- `reaper-wndpos.ini` — standard window positions
- `reaper-vstplugins_arm64.ini` — plugin database exists (ARM64 native)
- `reaper-jsfx.ini` — JSFX database exists
- `reaper-midihw.ini` — MIDI hardware config
- `reaper-fxtags.ini` — FX tags
- `reaper-mouse.ini` — mouse settings
- `reaper-reginfo2.ini` — license info

### Toolbars / Actions
- No custom toolbar definitions found in user data (only default REAPER toolbars)
- No `reaper_custom_actions.ini` or equivalent user customization
- Default toolbar icons present in `Data/toolbar_icons/150/`

### Layouts
- No user-defined layout files (`*.ReaperLayout` or equivalent)
- Only `reaper.ini` references basic mixer/transport visibility

### Project Templates
- No user template directory (`~/Library/Application Support/REAPER/ProjectTemplates/` not found)
- No `~/Library/Application Support/REAPER/TrackTemplates/`
- Only the default REAPER templates inside the app bundle are available

### FX Chains / Track Templates
- No user FX chain files (`.fxchains` or `.rfxchain` equivalents in user data)
- No user track template files (`.RTrackTemplate` equivalents)

### VST/AU Availability
- `reaper-vstplugins_arm64.ini` exists — plugins are registered (content truncated in audit, but file is non-empty)
- ARM64 native build of REAPER; VST scan has occurred previously

### Project State (Real Music)
- Active EP: `AETHERWOUND EP` (current working directory `~/AETHERWOUND EP`)
- Existing REAPER project: `songs/track-01/reaper/AW01_prototype_v003.rpp`
- This project contains real artistic work and must NOT be overwritten or corrupted by automation testing.

### ProjectSHURA Repo
- Located: `~/projectSHURA/`
- Existing docs: `docs/REAPER_INTEGRATION_PLAN.md` (outdated re: MCP)
- No `integrations/reaper/` directory existed before this audit
- No custom scripts for REAPER workflow in repo
- `AGENTS.md` defines project identity rules (identity/behavior/context separation)

### Majik Studio Integration
- `docs/ACE_STUDIO_CAPABILITY_REPORT.md` and `docs/MAJIK_MCP_VERIFICATION.md` exist
- No direct Majik Studio integration installed for REAPER
- Majik Studio is a separate audio generation layer, not a REAPER plugin

---

## 2. WHAT SHOULD BE PRESERVED

### Must Preserve (Non-Destructive)
1. **Existing REAPER MCP (`reaper_mcp_server.lua`)** — substantial, working, feature-complete for basic operations. Do NOT discard; build upon or wrap it.
2. **Existing REAPER project (`AW01_prototype_v003.rpp`)** — contains real artistic work.
3. **REAPER license and plugin database (`reaper-vstplugins_arm64.ini`)** — lost if overwritten; requires rescan.
4. **Current `reaper.ini` settings** — audio device settings, transport preferences, recent files list.
5. **Python `reaper_python.py`** — used by any Python-based bridge work.

### Should Preserve (Reversible Copy)
6. Default themes — keep as fallback.
7. Default keymap (`DK keymap`) — inspect for useful bindings before overriding.
8. Existing scripts in `Scripts/Cockos/` — theme adjusters should remain.

---

## 3. WHAT SHOULD BE MODIFIED

### Theme / Visual System (Phase 1)
- Create `projectSHURA/integrations/reaper/theme/AETHERWOUND_Theme.ReaperTheme` (or equivalent theme customization file)
- Establish semantic color palette (lavender, pink, cyan, blue, purple, white, gray, rose, dark charcoal)
- Apply to new templates; do NOT force-change existing AW01 project colors

### Project Template / Structure (Phase 1)
- Create canonical AETHERWOUND project template inside `projectSHURA/integrations/reaper/templates/`
- Define folder architecture:
  - `00_REFERENCE`, `01_GENERATION`, `02_STEMS` (DRUMS, BASS, MELODIC, FX, OTHER), `03_VOCALS` (LEAD, DOUBLES, HARMONIES, ADLIBS), `04_PROCESSING`, `05_BUSES`, `99_EXPORTS`
- Create corresponding track templates and folder hierarchy

### Scripts (Phase 2-3)
- Create `shura_create_project.lua` — uses existing MCP transport/project handlers plus REAPER actions, not destructive
- Create `shura_inspect_project.lua` — reads current track/route/item state via existing MCP or direct REAPER API
- Other workflow scripts can reference existing `reaper_mcp_server.lua` rather than duplicating its transport/project/item logic

### Toolbar / Actions (Phase 2)
- Create AETHERWOUND toolbar definitions (stored in repo, applied via REAPER action list import or script installation)
- Define semantic actions: Project / Playback / Edit / Generation / Stems / Vocals / Mix / Export / SHURA status

### Shortcuts (Phase 2)
- Design AETHERWOUND keymap file (`AETHERWOUND.Keymap.ReaperKeyMap`) with modifier-based mental model
- Do NOT destroy default shortcuts; layer custom ones carefully

### Layouts (Phase 2)
- Define layout files or layout-switching scripts for: CREATE, EDIT, MIX, MASTER, SHURA

---

## 4. WHAT IS MISSING

### High Priority
1. **AETHERWOUND visual theme** — none exists; must build from color palette definition.
2. **AETHERWOUND project template** — none exists; must create folder + routing + naming conventions.
3. **AETHERWOUND toolbar / custom actions** — none configured.
4. **AETHERWOUND keyboard map** — none exists.
5. **AETHERWOUND layouts** — none defined.
6. **Semantic track naming / metadata convention** — not implemented; must design mechanism (names + colors + folder roles + optional script metadata)

### Medium Priority
7. **Track templates** (Lead Vocal, Double Vocal, Harmony, Adlib, Drum Bus, Bass Bus, Music Bus, Master, Vocal FX) — none in user data.
8. **FX chain templates** — none in user data.
9. **JSFX custom library** — none customized for AETHERWOUND workflow.
10. **SHURA status panel / interface** — not implemented in REAPER.
11. **ProjectSHURA bridge integration file** — no `integrations/reaper/README.md`, `ARCHITECTURE.md`, or `WORKFLOW.md`.

### Low Priority / Deferred
12. **SWS Extension** — not installed; could provide additional actions but not required for Phase 1.
13. **ReaPack** — not installed; could provide additional scripts but not required for Phase 1.
14. **Majik Studio ↔ REAPER direct integration** — out of scope; Majik operates independently.
15. **Custom VST/AU plugins for AETHERWOUND identity** — artistic decision, not infrastructure.

---

## 5. WHAT CAN BE IMPLEMENTED IMMEDIATELY (Phase 1 — Foundation)

These are safe, reversible, and high-value:

A. **Repo structure creation** — create `projectSHURA/integrations/reaper/` subdirectories (done as first action of this audit session).

B. **Audit file** — `REAPER_AUDIT.md` (this file).

C. **Color palette documentation** — define exact hex/RGB values for semantic colors; document in `docs/COLOR_SEMANTICS.md`.

D. **Theme customization file** — create theme definition using REAPER's `.ReaperTheme` format or color-adjustment approach. Start from Default_7.0; do not modify original theme file directly.

E. **Canonical project template** — define folder/track structure in a `.rpp` file or script-based creation method. Keep it portable (relative paths).

F. **Semantic naming convention document** — define prefixes, folder roles, and color mappings.

G. **MCP evaluation and integration notes** — verify existing `reaper_mcp_server.lua` works (test one safe command); document capabilities, gaps, and bridge requirements in `docs/MCP.md`.

---

## 6. WHAT SHOULD BE DEFERRED

A. **Full custom MCP replacement** — existing Lua MCP is substantial; do not replace it prematurely. Build bridge layer only where missing.
B. **Advanced automation / SHURA-driven mutation** — requires stable semantic tracking first.
C. **Custom VST/AU installation** — depends on artistic direction, not infrastructure.
D. **Performance optimization** — not needed until scripts/toolbars exist.
E. **Cross-platform Windows/Linux theme compatibility** — current environment is macOS; maintain macOS focus, document portability notes.

---

## 7. CONFLICTS OR RISKS

### Risk 1: MCP State Discrepancy
- `REAPER_INTEGRATION_PLAN.md` claims "no MCP server exists."
- Actual environment has `reaper_mcp_server.lua` (5,392 lines).
- Resolution: The existing MCP takes precedence. Any bridge work must integrate with it, not ignore it. The plan document needs a correction note.

### Risk 2: Existing Project Overwrite
- `AW01_prototype_v003.rpp` is real work.
- Any automation testing (script creation, project template open) must use a disposable project (e.g., `test_AETHERWOUND_001.rpp` in a temp directory), not the AW01 file.

### Risk 3: Theme Corruption
- Modifying `Default_7.0.ReaperThemeZip` directly could corrupt the user's fallback theme.
- Resolution: Create new theme file (`AETHERWOUND_7.0.ReaperThemeZip` or equivalent) and load it as a separate theme, not an overwrite.

### Risk 4: Script Installation Path Conflicts
- Installing new scripts to `~/Library/Application Support/REAPER/Scripts/` could conflict with existing `reaper_mcp_server.lua` or `__startup.lua`.
- Resolution: Use a dedicated subfolder (`~/Library/Application Support/REAPER/Scripts/AETHERWOUND/` or install via repo reference) and reference in REAPER action list without replacing system files.

### Risk 5: Keyboard Map Collisions
- Overriding common REAPER shortcuts could break existing workflow.
- Resolution: Create separate `AETHERWOUND.Keymap.ReaperKeyMap` that can be switched via REAPER's keymap manager rather than permanently replacing defaults.

### Risk 6: Portability
- Many configurations (toolbar definitions, action lists, layouts) are stored in binary/ini formats that are not easily version-controlled as text.
- Resolution: Prefer script-based generation (Lua/JS) of toolbars/actions where possible; document binary files that must be manually installed.

---

## 8. MCP STATUS SUMMARY

### Existing Implementation (`reaper_mcp_server.lua`)
- Protocol: File-based IPC (polling)
- Commands verified by inspection: `transport_play`, `transport_stop`, `transport_set_play_state`, `track_get_all`, `track_add`, `track_get_info`, `project_get_info`, `project_save`, `fx_add`, `fx_get_all`, `item_get_all`, `item_add`, `item_split`, `marker_get_all`, `selection_set_time`, `send_create`, `midi_add_notes`, `compose_wipe_all_midi`, `envelope_set`, `tempo_list_markers`, `item_take_list`
- Response format: JSON with `success`/`error`, `id` echo for correlation
- Security: Safe path construction for IPC directory; uses REAPER native `RecursiveCreateDirectory`; no shell injection via unquoted paths (defensive character filtering applied)
- Stability: `pcall` wrapping around all handlers; `defer()` loop for non-blocking operation

### Gaps / Limitations
- No HTTP server interface (only file-based IPC) — fine for local automation but less convenient for remote/network access
- No `render` / `export` command found in handler list — must verify if `RPR_Render` is exposed
- No `script_exec` command — custom scripts must be loaded separately
- No `project_template_create` or `folder_create` semantic operations — these can be built with combinations of `track_add` + routing setup
- The Python `mcp_client` package exists (`.venv/lib/python3.11/site-packages/`) but no REAPER-specific Python MCP client exists in the repo

### Integration Recommendation
- Keep existing Lua MCP as primary control layer
- Build Python bridge in `projectSHURA/integrations/reaper/scripts/` that communicates with file-based IPC using Python `json` + `pathlib`
- If higher-level MCP is needed for Hermes agent integration, wrap the file-based protocol in a Python stdio MCP server that translates Hermes tool calls to REAPER file commands
- Do NOT write a new Lua MCP; extend the existing one only if a missing operation is critical

---

## 9. TEST MATRIX STATUS (Pre-Implementation)

All tests deferred until Phase 1 is complete; no destructive automation has been executed against any REAPER project.

---

## 10. ARCHITECTURAL DECISIONS MADE DURING AUDIT

1. **Use existing MCP as base** — not creating a new one from scratch.
2. **Keep theme customization separate** — create new theme file, don't modify Default.
3. **Script installation subfolder** — `Scripts/AETHERWOUND/` to avoid system conflicts.
4. **Separate audit/disposable test projects** — never test against `AW01_prototype_v003.rpp`.
5. **Semantic tracking via names + colors + folder roles** — no custom metadata database; rely on REAPER's native capabilities plus naming conventions.
6. **Phased approach** — Phase 1 = audit + repo structure + palette + theme base; Phase 2 = workflow scripts/toolbars/actions; Phase 3 = automation + MCP integration; Phase 4 = SHURA status/interface; Phase 5 = polish + docs.
