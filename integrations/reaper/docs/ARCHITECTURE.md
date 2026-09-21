# AETHERWOUND / REAPER ARCHITECTURE — ProjectSHURA Integration Layer

Version: 1.0 | Date: 2026-09-15 | Status: ACTIVE / Phase 1 Foundation

---

## System Layer Model

```
┌─────────────────────────────────────────────────────────────┐
│  HUMAN ARTIST (Viollett)                                     │
│  Final creative authority; directs intent                    │
└─────────────────────────────────────────────────────────────┘
            ↓ ideas, feedback, approval
┌─────────────────────────────────────────────────────────────┐
│  SHURA (Orchestration / Intelligence Layer)                  │
│  ProjectSHURA agent; operates through MCP, scripts, docs    │
│  Uses REAPER MCP (existing Lua server) + Python bridge     │
└─────────────────────────────────────────────────────────────┘
            ↓ commands, queries, analysis
┌─────────────────────────────────────────────────────────────┐
│  AETHERWOUND (Production Identity)                          │
│  Visual theme, naming conventions, folder architecture      │
│  Semantic track colors, toolbar actions, keyboard maps      │
│  Project templates, track templates, FX chains              │
└─────────────────────────────────────────────────────────────┘
            ↓ actions, rendering, recording
┌─────────────────────────────────────────────────────────────┐
│  REAPER (DAW Engine)                                        │
│  Audio engine, mixer, transport, routing, automation          │
│  ReaScript (Lua + Python), VST/AU plugins, JSFX            │
│  Existing MCP server (`reaper_mcp_server.lua`)               │
└─────────────────────────────────────────────────────────────┘
            ↓ audio files, stems, projects
┌─────────────────────────────────────────────────────────────┐
│  MAJIK STUDIO / GENERATION LAYER (External)                  │
│  AI audio generation, stem creation                         │
│  Separate from REAPER; integrated via file import            │
└─────────────────────────────────────────────────────────────┘
```

These layers are modular and separable. SHURA does not equal REAPER; AETHERWOUND does not equal SHURA; ProjectSHURA does not equal AETHERWOUND. Each layer has its own documentation, version control, and failure mode.

---

## Layer Definitions

### ProjectSHURA (Portable Machinery)
Location: `~/projectSHURA/`
Purpose: The repository-level implementation of the SHURA collaboration system. Contains source code, documentation, skills, configurations, and integration logic for all surfaces (REAPER, ATLAS, FORGE, web, voice, etc.).
Key property: This directory is version-controlled (`.git` exists) and portable across installations (with machine-local exclusions documented).
Current state: Has REAPER audit (`docs/REAPER_INTEGRATION_PLAN.md`), identity docs (`AGENTS.md`), core code (`src/`). Missing: `integrations/reaper/` structure — being built now.

### AETHERWOUND (Production Identity)
Location: `~/projectSHURA/integrations/reaper/` (REAPER-specific) + `~/AETHERWOUND EP/` (current artistic project)
Purpose: The visual and workflow identity applied to REAPER. Not a character or an agent — it is the design language and organizational convention that makes the production environment coherent.
Key properties:
- Independent of SHURA agent state (works offline, works when SHURA is unavailable)
- Independent of any specific REAPER version (configured via portable files)
- Independent of the AW01 project (applies to new projects without overwriting existing ones)
- Not a reskin — it is a functional layer (templates, actions, naming, colors)

### REAPER (DAW Surface)
Location: `/Applications/REAPER.app/` + `~/Library/Application Support/REAPER/`
Purpose: Audio production engine. Provides recording, mixing, editing, automation, routing, plugin hosting, and scripting.
Current version: 7.79.0 (ARM64 native)
Key components for this architecture:
- `reaper.ini` — configuration (preserved, not overwritten)
- `Scripts/reaper_mcp_server.lua` — existing MCP server (preserved, extended if needed)
- `Scripts/__startup.lua` — default startup script (preserved)
- `ColorThemes/` — theme files (new theme added, not overwritten)
- `KeyMaps/` — keyboard configurations (new keymap added)
- User plugin data — `reaper-vstplugins_arm64.ini` (preserved)

### SHURA (Agent / Intelligence)
Purpose: Long-term creative and technical collaborator. Uses ProjectSHURA infrastructure, operates through MCP and integrations, maintains continuity across sessions.
Key property: SHURA is not a plugin inside REAPER. SHURA operates through the existing MCP file-based protocol, through Python bridge scripts, and through manual script invocation.
Boundary rule: SHURA identity is not tied to any one REAPER theme, plugin, or state. If REAPER crashes, SHURA does not crash. If SHURA is offline, AETHERWOUND remains fully functional.

---

## Integration Points

### Point A: MCP Protocol (REAPER ↔ SHURA)
File: `~/Library/Application Support/REAPER/Scripts/reaper_mcp_server.lua`
Method: File-based IPC (`TMPDIR/reaper_mcp/command.json` → `response.json`)
Status: Existing, substantial (5,392 lines), working
Capabilities verified: Transport, track, project, FX, item, chop, marker, selection, send, MIDI, compose, envelope, tempo, take
Gaps identified: No direct render/export command visible; no semantic folder-creation command; no project-template command
Integration strategy:
- Do NOT replace this file.
- Build Python bridge (`projectSHURA/integrations/reaper/scripts/reaper_mcp_client.py`) that reads commands from SHURA/Hermes, writes `command.json`, reads `response.json`, and translates results.
- If new commands are needed (e.g., `project_template_create`), extend the Lua server by adding a new handler rather than duplicating it.

### Point B: ReaScript (REAPER Internal Scripting)
Path: Inside REAPER (`Actions > Show action list > Load ReaScript`)
Languages: Lua (primary), Python (`reaper_python.py` — 730 exported `RPR_*` functions), EBASIC, JScript
Usage in this architecture:
- Custom workflow scripts (`shura_create_project.lua`, `shura_create_vocal_stack.lua`, etc.) installed to `Scripts/AETHERWOUND/`
- Scripts reference standard REAPER actions where possible, use `reaper_mcp_server.lua` handlers for complex operations, and fall back to direct `reaper.*` API calls for fine-grained control
- Scripts must fail gracefully (`pcall` in Lua; try/except in Python), avoid destructive behavior without confirmation, and avoid hardcoded absolute paths

### Point C: Theme Customization
Method: Create new `.ReaperThemeZip` file based on `Default_7.0`, load via REAPER theme manager
Status: Design complete (`docs/COLOR_SEMANTICS.md`); theme file creation deferred to Phase 1 completion
Notes:
- REAPER's theme format is binary (zipped XML + images). Direct text editing is possible but fragile.
- The recommended approach is to use REAPER's built-in theme editor to apply color values, then save the customized theme as a new file.
- Alternative: Use theme adjustment scripts (like `Default_7.0_theme_adjuster.lua`) to programmatically change colors at startup.
- This architecture supports both approaches; preference is for a saved `.ReaperThemeZip` file that can be installed without running scripts.

### Point D: Project Template (Standard Architecture)
Location: `projectSHURA/integrations/reaper/templates/AETHERWOUND_Template.rpp`
Structure: Folder tracks + routing + naming convention + initial colors
Usage: Opened via `File > Project templates` or created via `shura_create_project.lua`
Portability: Template should use relative media paths and reference no absolute directories outside the project folder.

### Point E: Semantic Tracking
Mechanism: Not a custom database. Uses a combination of:
1. **Consistent track names** (e.g., `03_VOCALS / LEAD / Main Vocal`, `02_STEMS / DRUMS / Kick`, `05_BUSES / MIX`)
2. **Folder hierarchy** (parent-child relationships provide role inference)
3. **Semantic colors** (each track type has a known base color)
4. **Routing structure** (tracks routed to specific bus folders reveal their role)
5. **Optional script metadata** (future: custom track notes or script tags stored in REAPER's track properties)
This is sufficient for SHURA to infer "find the lead vocal" or "find the drum bus" without requiring a proprietary metadata system.

---

## File System Mapping (ProjectSHURA ↔ REAPER)

```
projectSHURA/
└── integrations/
    └── reaper/
        ├── README.md                  # User-facing entry point
        ├── REAPER_AUDIT.md            # This audit (current state)
        ├── docs/
        │   ├── ARCHITECTURE.md        # This file (system design)
        │   ├── WORKFLOW.md             # Production workflow documentation
        │   ├── COLOR_SEMANTICS.md      # Palette definition
        │   └── MCP.md                  # MCP evaluation + bridge notes
        ├── theme/
        │   ├── AETHERWOUND_Theme.ReaperThemeZip   # Theme file (Phase 1)
        │   └── theme_notes.md          # Theme customization instructions
        ├── scripts/
        │   ├── shura_create_project.lua     # Phase 2
        │   ├── shura_inspect_project.lua    # Phase 3
        │   ├── shura_create_vocal_stack.lua # Phase 2
        │   ├── shura_create_stem_bus.lua    # Phase 2
        │   ├── shura_snapshot.lua           # Phase 2
        │   ├── shura_cleanup_project.lua    # Phase 3
        │   └── shura_status.lua             # Phase 4
        ├── actions/                    # Custom action definitions
        │   └── actions_list.md          # Documented actions (text-based reference)
        ├── toolbars/                   # Toolbar configuration references
        │   └── toolbar_notes.md         # Description of intended toolbar layout
        ├── layouts/                    # Layout definitions / switching logic
        │   └── layout_notes.md          # CREATE / EDIT / MIX / MASTER / SHURA descriptions
        ├── templates/
        │   ├── AETHERWOUND_Template.rpp     # Canonical project template (Phase 1)
        │   └── AETHERWOUND_Template_Notes.md
        ├── track-templates/
        │   ├── LeadVocal.RTrackTemplate     # Phase 2
        │   ├── DoubleVocal.RTrackTemplate  # Phase 2
        │   ├── Harmony.RTrackTemplate      # Phase 2
        │   ├── DrumBus.RTrackTemplate      # Phase 2
        │   ├── BassBus.RTrackTemplate      # Phase 2
        │   ├── MusicBus.RTrackTemplate     # Phase 2
        │   ├── Master.RTrackTemplate       # Phase 2
        │   └── VocalFX.RTrackTemplate      # Phase 2
        ├── fxchains/
        │   ├── LeadVocal_Premix.RfxChain    # Phase 2 (optional)
        │   └── Master_Premaster.RfxChain   # Phase 2 (optional)
        ├── jsfx/                        # Custom JSFX plugins (optional)
        │   └── AETHERWOUND_GlitchMeter.jsfx   # Phase 5 (deferred)
        ├── config/
        │   └── install_instructions.md   # How to apply theme, scripts, templates
        └── tests/
            ├── test_create_project.md     # Manual verification steps
            ├── test_mcp_connection.md     # MCP health check
            └── test_semantic_inspection.md # Verify track role inference

REAPER User Data (machine-local, preserved):
~/Library/Application Support/REAPER/
├── reaper.ini                     # Preserved; not overwritten
├── ColorThemes/
│   ├── Default_6.0.ReaperThemeZip  # Original preserved
│   ├── Default_7.0.ReaperThemeZip  # Original preserved
│   └── AETHERWOUND_Theme.ReaperThemeZip  # Installed by user or script
├── Scripts/
│   ├── __startup.lua               # Preserved
│   ├── reaper_mcp_server.lua       # Preserved; extended if needed
│   └── AETHERWOUND/                 # Installed by setup script
│       ├── shura_create_project.lua
│       └── ...
├── KeyMaps/
│   └── AETHERWOUND.Keymap.ReaperKeyMap  # Installed separately
└── ProjectTemplates/               # Created by user or installed
    └── AETHERWOUND_Template.rpp

Machine-specific exclusions (not committed to git):
- Theme binary (`AETHERWOUND_Theme.ReaperThemeZip`) — committed once created
- Project templates (`*.rpp`, `*.RTrackTemplate`, `*.RfxChain`) — committed (they are portable)
- Keymap files — committed (they are portable text/binary, not secrets)
- Any `.env`, `reaper.ini`, `reaper-vstplugins_arm64.ini` — NEVER committed
```

---

## Design Decisions Recorded

### Decision 1: Existing MCP Takes Precedence
Reason: The environment contains a substantial working Lua MCP (`reaper_mcp_server.lua`, 5,392 lines, file-based IPC, extensive handler set). Building a new MCP from scratch would duplicate working functionality, introduce new bugs, and ignore the user's existing infrastructure. The architecture integrates with and extends the existing MCP rather than replacing it.
Consequences: Any SHURA-driven automation must either (a) use the file-based protocol directly, or (b) build a Python bridge that translates Hermes MCP calls into REAPER file commands.

### Decision 2: Semantic Tracking Uses Native REAPER Features
Reason: Inventing a proprietary metadata database (e.g., a custom JSON file that maps track IDs to roles) creates another point of failure and requires synchronization with REAPER's internal state. Using consistent names, folder hierarchy, colors, and routing provides sufficient inference for most automation tasks and requires no extra synchronization logic.
Consequences: Scripts that need to find "the lead vocal" will search for tracks with names matching `*LEAD*` or `*VOCAL*` inside folder `03_VOCALS`, verify by color, and confirm by routing. This is slightly more complex than a direct database lookup but eliminates a synchronization layer.

### Decision 3: Theme Customization as Separate File
Reason: Overwriting `Default_7.0.ReaperThemeZip` would destroy the user's fallback theme and make rollback impossible. Creating a new theme file (`AETHERWOUND_Theme.ReaperThemeZip`) preserves the original and allows easy switching.
Consequences: The user must load the new theme manually once (or via a startup script) after installation. The theme file must be installed into `~/Library/Application Support/REAPER/ColorThemes/` or loaded via `File > Load theme`.

### Decision 4: Phase-Based Implementation
Reason: The directive requires a working baseline before over-engineering. Building the visual system, templates, and naming conventions first ensures that later automation scripts have a stable environment to operate in. Adding automation before defining the structure would result in scripts that create chaos rather than order.
Consequences: Phase 1 (this document and its files) establishes the design. Phase 2 creates scripts that assume Phase 1's conventions. Phase 3 connects those scripts to the MCP. Phase 4 adds SHURA-specific interfaces. Phase 5 polishes. This ordering is enforced in the implementation plan.

---

## Boundary Rules (Identity Preservation)

### Boundary A: REAPER ≠ SHURA
REAPER is one embodiment surface. SHURA operates through multiple surfaces (REAPER MCP, web interface, terminal, future mobile/smart-home interfaces). If REAPER is uninstalled, SHURA continues. The AETHERWOUND theme is specific to REAPER but the identity rules in `AGENTS.md` are independent.

### Boundary B: AETHERWOUND ≠ ProjectSHURA
AETHERWOUND is the visual/workflow identity layer applied to REAPER. ProjectSHURA is the portable repository that contains this layer plus the agent code, documentation, skills, and other integrations. The AETHERWOUND layer could be installed on a different machine without ProjectSHURA's agent components.

### Boundary C: SHURA ≠ REAPER State
SHURA's cognition is not stored in the REAPER mixer, the current theme, or the active plugin. SHURA's continuity is maintained through persistent memory (`~/.hermes/` memory files, skills, conversation history), not through REAPER project files. The SHURA status panel described in the directive will display REAPER-derived data (track counts, BPM, key, length) but SHURA's identity and decisions are separate from that data.

---

## References

- REAPER user guide: https://www.reaper.fm/userguide.php
- REAPER scripting (ReaScript): https://www.reaper.fm/sdk/reascript/reascript.php
- REAPER theme customization: `~/Library/Application Support/REAPER/Scripts/Cockos/Default_7.0_theme_adjuster.lua`
- Existing MCP: `~/Library/Application Support/REAPER/Scripts/reaper_mcp_server.lua`
- ProjectSHURA identity: `~/projectSHURA/AGENTS.md`, `~/projectSHURA/data/prompts/soul.md`
- AETHERWOUND EP project: `~/AETHERWOUND EP/` (current working directory at audit time)
