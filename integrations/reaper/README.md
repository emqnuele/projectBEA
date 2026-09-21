# AETHERWOUND / REAPER — ProjectSHURA Integration

ProjectSHURA repository: `~/projectSHURA/` (version-controlled)
REAPER installation: `/Applications/REAPER.app/` (v7.79.0, ARM64)
Current working EP: `~/AETHERWOUND EP/`

---

## What This Is

This is the REAPER-side implementation of the AETHERWOUND production identity. It contains:

- Visual identity (theme customization, color semantics, palette)
- Project structure (folder architecture, routing, naming conventions)
- Workflow scripts (project creation, vocal stack, stem bus, export, snapshot, inspection)
- Custom actions (toolbar definitions, keyboard shortcuts, layout concepts)
- MCP integration notes and bridge design (using the existing `reaper_mcp_server.lua`)
- Documentation (architecture, workflow, color semantics, MCP evaluation)

It does NOT contain:
- A new REAPER installation (REAPER is installed separately)
- A replacement for the existing REAPER MCP (the existing Lua server is preserved)
- A custom DAW (REAPER remains the engine; this is a layer on top)
- Artistic content (music files, audio recordings, mix decisions — those live in `~/AETHERWOUND EP/`)

---

## Quick Start (After Installation)

1. **Audit**: Read `REAPER_AUDIT.md` to understand the current environment.
2. **Palette**: Read `docs/COLOR_SEMANTICS.md` for the semantic color system.
3. **Architecture**: Read `docs/ARCHITECTURE.md` for the layer model and integration points.
4. **Workflow**: Read `docs/WORKFLOW.md` for production flow and naming conventions.
5. **Theme**: Install the AETHERWOUND theme file (Phase 1 — see `theme/` and `docs/COLOR_SEMANTICS.md`).
6. **Templates**: Load or create an AETHERWOUND project template (`templates/AETHERWOUND_Template.rpp`).
7. **Scripts**: Install workflow scripts to REAPER's script directory (`Scripts/AETHERWOUND/`).
8. **Actions/Shortcuts**: Apply toolbar and keyboard configurations (see `actions/` and `layouts/` for notes; full binary files installed manually per instructions in `config/install_instructions.md`).
9. **MCP Check**: Verify `reaper_mcp_server.lua` is loaded; test with a safe command (see `docs/MCP.md`).

---

## Directory Structure

```
projectSHURA/
└── integrations/
    └── reaper/
        ├── README.md                  # This file
        ├── REAPER_AUDIT.md            # Environment inspection results
        ├── docs/
        │   ├── ARCHITECTURE.md        # System layer design
        │   ├── WORKFLOW.md             # Production flow documentation
        │   ├── COLOR_SEMANTICS.md      # Palette and color rules
        │   └── MCP.md                  # MCP evaluation + bridge plan
        ├── theme/                      # Theme customization
        ├── scripts/                    # ReaScripts (Lua)
        ├── actions/                    # Custom action documentation
        ├── toolbars/                   # Toolbar design notes
        ├── layouts/                    # Layout design notes
        ├── templates/                  # Project and track templates
        ├── track-templates/            # Track-level templates (.RTrackTemplate)
        ├── fxchains/                   # FX chain templates (.RfxChain)
        ├── jsfx/                        # Custom JSFX plugins (optional/deferred)
        ├── config/                     # Installation and setup instructions
        └── tests/                      # Manual verification steps
```

---

## Key Design Principles

1. **Modular, not monolithic**: The AETHERWOUND layer is separate from REAPER, SHURA, and ProjectSHURA. It can be installed, removed, or modified independently.
2. **Reuse existing infrastructure**: The existing `reaper_mcp_server.lua` (5,392 lines, file-based IPC, extensive handlers) takes precedence. We extend it; we do not replace it.
3. **Semantic tracking over custom metadata**: Track roles are inferred from names, folder hierarchy, colors, and routing — not from a proprietary database.
4. **Visual coherence without sacrificing usability**: The theme is dark, cybernetic, feminine, and eerie — but contrast and readability come first.
5. **Portability**: All configuration files (scripts, templates, color documentation) live in this repository. Machine-local settings (`reaper.ini`, plugin database) are preserved but not overwritten.
6. **Safety**: No destructive automation is executed without explicit user confirmation or clear separation. All scripts fail gracefully.

---

## Implementation Phase Status

As of audit (2026-09-15):

| Phase | Status | Deliverables |
|---|---|---|
| Phase 1 — Foundation (Audit + Repo + Palette + Theme Base + Naming) | **ACTIVE / In Progress** | `REAPER_AUDIT.md`, repo structure, `COLOR_SEMANTICS.md`, `ARCHITECTURE.md`, `WORKFLOW.md`, theme design, project template design |
| Phase 2 — Workflow (Scripts + Toolbars + Actions + Shortcuts + Layouts + Templates) | **Planned** | `shura_create_project.lua`, `shura_create_vocal_stack.lua`, toolbar notes, keyboard map design, track templates |
| Phase 3 — Automation (Script Integration + MCP Bridge + Inspection) | **Planned** | `shura_inspect_project.lua`, Python bridge (`reaper_mcp_client.py`), MCP evaluation (`docs/MCP.md`) |
| Phase 4 — SHURA (Status Panel + Semantic Operations + Bidirectional State) | **Planned / Deferred** | SHURA status interface, advanced automation |
| Phase 5 — Polish (Visual Refinement + Performance + Docs + Testing + Bootstrap) | **Planned / Deferred** | Final theme file, performance checks, full documentation, regression tests |

---

## Dependencies

### Required (Already Present)
- REAPER 7.79.0 (ARM64) — installed at `/Applications/REAPER.app/`
- Python 3.11.15 (used by ProjectSHURA `.venv`) — available
- `reaper_python.py` (730 `RPR_*` functions) — present in REAPER app bundle
- `reaper_mcp_server.lua` (existing MCP) — present in `~/Library/Application Support/REAPER/Scripts/`

### Optional / Deferred
- SWS Extension — not installed; provides additional actions but not required
- ReaPack — not installed; provides community scripts but not required for Phase 1-2
- Custom VST/AU plugins — artistic decision, not infrastructure
- Majik Studio direct integration — operates independently; integrated via file import only

---

## Safety Notes

- **Do NOT test automation against `~/AETHERWOUND EP/songs/track-01/reaper/AW01_prototype_v003.rpp`**. This is real artistic work. All script testing uses temporary project files.
- **Do NOT modify `~/Library/Application Support/REAPER/reaper.ini` destructively**. The file is preserved; new configurations are added via separate theme files, script installations, or user-applied settings.
- **Do NOT delete or disable `reaper_mcp_server.lua`**. The existing MCP is a substantial asset.
- **Do NOT commit machine-local secrets** (`reaper.ini`, `.env`, API keys, plugin database files) to the repository.

---

## References

- ProjectSHURA repo root: `~/projectSHURA/`
- AETHERWOUND EP (current artistic project): `~/AETHERWOUND EP/`
- REAPER user guide: https://www.reaper.fm/userguide.php
- REAPER scripting docs: https://www.reaper.fm/sdk/reascript/reascript.php
- Existing MCP source: `~/Library/Application Support/REAPER/Scripts/reaper_mcp_server.lua`
- SHURA identity: `~/projectSHURA/data/prompts/soul.md`, `~/projectSHURA/AGENTS.md`
