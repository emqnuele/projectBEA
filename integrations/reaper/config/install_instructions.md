# AETHERWOUND / REAPER — Installation and Setup Instructions

---

## Quick Installation (Phase 1 — Foundation)

These steps establish the AETHERWOUND layer on top of an existing REAPER 7.79 installation.

### 1. Verify REAPER Environment
- REAPER version: 7.79 (confirmed via `~/Library/Application Support/REAPER/reaper-install-rev.txt`)
- REAPER app: `/Applications/REAPER.app/`
- User data: `~/Library/Application Support/REAPER/`
- Existing MCP: `Scripts/reaper_mcp_server.lua` (DO NOT DELETE)

### 2. Install Repository Files
No binary installation is required for Phase 1 (documentation, theme scripts, templates are text/file-based).

For full installation (after Phase 2 scripts complete):
```bash
# Example (manual installation — scripts installed individually)
mkdir -p ~/Library/Application\ Support/REAPER/Scripts/AETHERWOUND/
cp /path/to/projectSHURA/integrations/reaper/scripts/*.lua ~/Library/Application\ Support/REAPER/Scripts/AETHERWOUND/
```

### 3. Load Theme Customization (Manual)
- Read `theme/theme_notes.md` and `docs/COLOR_SEMANTICS.md`
- Use REAPER's theme customization (or `theme/AETHERWOUND_Theme_Apply.lua`) to apply colors
- Save customized theme as `AETHERWOUND_Theme.ReaperThemeZip` (optional — deferred)

### 4. Load Project Template (Optional)
- Open REAPER
- Load `templates/AETHERWOUND_Template.rpp` (this applies the folder architecture as a new project base)

### 5. Load Scripts (Manual)
- In REAPER: Actions > Show action list > ReaScript: Load
- Select individual `.lua` files from `scripts/`
- Or install all to `Scripts/AETHERWOUND/` and reference from the action list

### 6. Configure Shortcuts / Toolbars (Manual / Deferred)
- Shortcuts: Load `AETHERWOUND.Keymap.ReaperKeyMap` (when created — Phase 2)
- Toolbars: Apply toolbar definitions (described in `docs/WORKFLOW.md` — full binary installation deferred to Phase 2/5)

---

## What Must Remain Machine-Local (Do Not Commit)

- `~/Library/Application Support/REAPER/reaper.ini` (user preferences, audio device settings)
- `~/Library/Application Support/REAPER/reaper-vstplugins_arm64.ini` (plugin database)
- Any `.env` or API key files in `~/projectSHURA/`
- Generated audio files, mixes, or render outputs
- User-specific snapshot files (`.rpp` copies created by `shura_snapshot.lua`)

---

## Restoration Process (Fresh macOS Installation)

If REAPER is installed on a new machine:

1. Install REAPER 7.79 (or compatible version)
2. Verify Python `reaper_python.py` exists in REAPER app bundle
3. Copy this repository to the new machine (`~/projectSHURA/`)
4. Copy script files to REAPER Scripts directory (`~/Library/Application Support/REAPER/Scripts/AETHERWOUND/`)
5. Apply theme customization manually or via `AETHERWOUND_Theme_Apply.lua`
6. Load `AETHERWOUND_Template.rpp` for new projects
7. Verify existing `reaper_mcp_server.lua` is present; if not, restore from backup or repository reference
8. Test with a disposable project (do not test against real artistic work)

---

## Safety Checklist (Before Any Automation)

- [ ] Real project (`AW01_prototype_v003.rpp`) is backed up or untouched
- [ ] Testing uses temporary/disposable project files only
- [ ] Scripts are loaded from `scripts/` directory (not untrusted sources)
- [ ] `reaper_mcp_server.lua` is not deleted or overwritten
- [ ] Any destructive operation (delete, overwrite) is clearly separated and requires user confirmation

---

## Phase Status

| Phase | Status | Key Deliverables | How to Verify |
|---|---|---|---|
| Phase 1 — Foundation | **COMPLETE (docs + repo + theme design)** | Audit (`REAPER_AUDIT.md`), architecture docs (`ARCHITECTURE.md`), workflow (`WORKFLOW.md`), palette (`COLOR_SEMANTICS.md`), theme notes (`theme_notes.md`), template (`templates/AETHERWOUND_Template.rpp`) | Read docs; verify theme script exists; verify template file opens in REAPER |
| Phase 2 — Scripts | **COMPLETE (prototype scripts)** | `scripts/shura_create_project.lua`, `scripts/shura_create_vocal_stack.lua`, `scripts/shura_create_stem_bus.lua`, `scripts/shura_inspect_project.lua`, `scripts/shura_snapshot.lua`, `scripts/shura_prepare_export.lua` | Load scripts via REAPER action list; test each with disposable project |
| Phase 2 — Toolbars / Actions / Shortcuts | **PLANNED / NOTES ONLY** | Toolbar notes (`docs/WORKFLOW.md` section), keyboard design (same doc) | Not implemented as binary files; described in documentation |
| Phase 3 — MCP / Automation | **IN PROGRESS (docs)** | `docs/MCP.md` (MCP evaluation and bridge notes) | Verify existing `reaper_mcp_server.lua` works; test safe command manually |
| Phase 4 — SHURA Status / Interface | **DEFERRED** | Concept described in `ARCHITECTURE.md` and `WORKFLOW.md` | Not implemented |
| Phase 5 — Polish / Performance / Bootstrap | **DEFERRED** | Theme binary file (`AETHERWOUND_Theme.ReaperThemeZip`), final tests, installation automation | Not implemented |
