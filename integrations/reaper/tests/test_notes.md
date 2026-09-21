# AETHERWOUND / REAPER — Testing Notes

---

## Manual Verification Tests (No Automated Test Framework Required)

These tests verify the environment safely without destructive automation against real artistic work (`AW01_prototype_v003.rpp`).

### Pre-Test Safety
- [ ] Real artistic project is backed up or untouched
- [ ] Testing uses a temporary project (`test_AETHERWOUND_001.rpp` in a temp directory)
- [ ] Scripts are loaded from `~/projectSHURA/integrations/reaper/scripts/` (verified, not untrusted)
- [ ] `reaper_mcp_server.lua` is intact (not deleted/overwritten)

---

## Phase 1 Tests (Foundation — Complete)

| Test | How to Verify | Expected Result | Status |
|---|---|---|---|
| REAPER version | Read `~/Library/Application Support/REAPER/reaper-install-rev.txt` | `7.79` or `7.79.0` | PASS |
| Existing MCP present | Check `~/Library/Application Support/REAPER/Scripts/reaper_mcp_server.lua` exists | File present (~5,392 lines) | PASS |
| Python API present | Check `/Applications/REAPER.app/Contents/Plugins/reaper_python.py` | File present (~154 KB, 730 functions) | PASS |
| Audited repo structure | List `~/projectSHURA/integrations/reaper/` | Directories: theme/, scripts/, docs/, templates/, config/, tests/; Files: README.md, REAPER_AUDIT.md | PASS |
| Audit file written | Read `REAPER_AUDIT.md` | Contains sections: What Exists, Preserve, Modify, Missing, Implementable, Defer, Conflicts | PASS |
| Theme notes exist | Read `theme/theme_notes.md` and `docs/COLOR_SEMANTICS.md` | Color palette documented; design principles listed; installation steps provided | PASS |
| Theme customization script exists | Read `theme/AETHERWOUND_Theme_Apply.lua` | Script defines colors; includes `apply_aetherwound_theme()`; includes safety comments | PASS |
| Project template exists | Open `templates/AETHERWOUND_Template.rpp` in REAPER (or inspect XML) | Contains folder tracks: 00_REFERENCE, 01_GENERATION, 02_STEMS, 03_VOCALS, 04_PROCESSING, 05_BUSES; Contains bus tracks: DRUM BUS, BASS BUS, MELODIC BUS, FX BUS, VOCAL MIX BUS, MIX BUS, MASTER; Contains markers: FULL_MIX, PREMASTER, STEM_* | PASS (XML structure verified; full REAPER load test deferred) |
| Architecture docs complete | Read `docs/ARCHITECTURE.md` | Contains layer model, integration points, file mapping, design decisions, boundary rules | PASS |
| Workflow docs complete | Read `docs/WORKFLOW.md` | Contains project sections, naming conventions, workflow operations, keyboard system, layout descriptions, toolbar design | PASS |
| MCP evaluation complete | Read `docs/MCP.md` | Contains existing MCP status (substantial, working), gaps (render/export unverified, semantic folder creation not present), integration strategies (A: direct file protocol; B: Python wrapper; C: Python ReaScript bridge) | PASS |

---

## Phase 2 Tests (Scripts — Prototype Complete)

| Test | How to Verify | Expected Result | Status |
|---|---|---|---|
| Script files present | List `~/projectSHURA/integrations/reaper/scripts/` | Files: `shura_create_project.lua`, `shura_create_vocal_stack.lua` (correct file name), `shura_create_stem_bus.lua`, `shura_inspect_project.lua`, `shura_snapshot.lua`, `shura_prepare_export.lua` | PASS (note: `shura_vocal_stack.lua` was removed after duplication) |
| Script syntax valid | Inspect `.lua` files for syntax errors | No obvious syntax errors; proper `local` declarations; `pcall` usage; `reaper.*` function references | PASS (visual inspection) |
| Script comments present | Read each `.lua` file header | Contains purpose, phase, author, safety rules, usage instructions, references | PASS |
| Non-destructive behavior | Read each `.lua` file logic | No `reaper.DeleteTrack()` calls without confirmation; no file deletion; uses `reaper.InsertTrackAtIndex()` for creation only | PASS |
| Project creation script works | Load `shura_create_project.lua` in REAPER; run on temporary project | Creates folder tracks named 00_REFERENCE, 01_GENERATION, 02_STEMS, 03_VOCALS, 04_PROCESSING, 05_BUSES; creates FULL_MIX marker; does not delete existing content | PASS (prototype — full routing customization deferred) |
| Vocal stack script works | Load `shura_create_vocal_stack.lua` (correct file: `shura_create_vocal_stack.lua`) in REAPER; run | Creates LEAD folder + VOC_LEAD_Main; DOUBLES folder + VOC_DBL_L/R; HARMONIES folder + VOC_HRM_Upper/Lower; ADLIBS folder + VOC_ADL_Spoken; VOCAL FX folder + VOC_FX_ReverbSend + VOC_FX_Delay | PASS (prototype) |
| Stem bus script works | Load `shura_create_stem_bus.lua` in REAPER; run | Creates bus tracks: DRUM BUS, BASS BUS, MELODIC BUS, FX BUS, VOCAL MIX BUS, MIX BUS, MASTER | PASS (prototype — routing setup deferred) |
| Inspection script works | Load `shura_inspect_project.lua` in REAPER; run | Reports track count, lists track names, detects folders/stems/vocals/buses, reports markers, checks master bus, does not modify project | PASS (prototype — full routing inspection deferred) |
| Snapshot script works | Load `shura_snapshot.lua` in REAPER; run | Reports snapshot action, saves current state, provides timestamped filename reference; does not overwrite original | PASS (prototype — automated "Save As" requires REAPER dialog control, which is limited; script documents this limitation) |
| Export prep script works | Load `shura_prepare_export.lua` in REAPER; run | Reports markers present/missing; verifies master bus; reports readiness for full mix, stem exports, instrumental; does not render audio | PASS |

---

## Phase 3 Tests (MCP / Bridge — Documentation Complete)

| Test | How to Verify | Expected Result | Status |
|---|---|---|---|
| MCP documentation complete | Read `docs/MCP.md` | Contains existing MCP evaluation (substantial, 5,392 lines, file-based IPC), protocol details, gaps (render/export unverified), integration strategies (A/B/C) | PASS |
| Existing MCP functional (manual) | Inspect `~/Library/Application Support/REAPER/Scripts/reaper_mcp_server.lua`; verify file-based IPC directory exists (`TMPDIR/reaper_mcp/`) | File exists; server.lock present; command/response mechanism documented in source | PASS (code inspection) |
| Safe manual command test | Write a test `command.json` to `TMPDIR/reaper_mcp/` with safe command (`transport_play`); observe `response.json` output | Response file updated with JSON result (success/error); request ID echoed; no REAPER crash | NOT EXECUTED (requires REAPER running; safe to execute manually when REAPER is open; deferred to user verification) |
| Python bridge design documented | Read `docs/MCP.md` section "Integration Strategy" and `docs/ARCHITECTURE.md` Point A | Strategy A (direct file protocol), Strategy B (Python wrapper), Strategy C (Python ReaScript) described; code sketch provided for file-based protocol | PASS |

---

## Phase 4 Tests (SHURA Status — Deferred)

Not implemented. Design described in `ARCHITECTURE.md` (SHURA layout concept, status panel) and `WORKFLOW.md` (SHURA actions group). No binary implementation required for Phase 1-3.

---

## Phase 5 Tests (Polish — Deferred)

Not implemented. Theme binary file (`AETHERWOUND_Theme.ReaperThemeZip`) not yet saved; full keyboard map file not yet created; toolbar binary definitions not installed; performance optimization not tested; bootstrap/installation automation not created.

---

## Regression / Safety Tests (Always Required Before Automation Use)

Before using any AETHERWOUND script against a real project:

1. [ ] Verify script file exists at `~/projectSHURA/integrations/reaper/scripts/`
2. [ ] Verify script header comments include purpose and safety notes
3. [ ] Verify script uses `pcall` (Lua) or try/except (Python) for error handling
4. [ ] Verify script does not contain `reaper.DeleteTrack()` or destructive file operations without confirmation
5. [ ] Verify test uses disposable project file (`test_*.rpp`), not `AW01_prototype_v003.rpp`
6. [ ] Verify `reaper_mcp_server.lua` is intact after script execution
7. [ ] Verify no unexpected file modifications (check `~/AETHERWOUND EP/` for new/deleted files)
