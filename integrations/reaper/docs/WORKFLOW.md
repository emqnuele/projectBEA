# AETHERWOUND / REAPER WORKFLOW DOCUMENTATION

Version: 1.0 | Date: 2026-09-15 | Status: ACTIVE

---

## Overview: Production Flow

The AETHERWOUND workflow is designed for electronic, vocal, and experimental production that combines AI-generated stems with live performance, editing, vocal recording, and manual mixing. The flow is linear but allows branching (e.g., generating new stems during arrangement, recording vocals after initial mix layout).

```
IDEA / INTENT
      ↓
GENERATION (Majik Studio / AI tools) → RAW GENERATED TRACKS
      ↓ (import / organize)
AETHERWOUND PROJECT TEMPLATE (00_REFERENCE, 01_GENERATION, ...)
      ↓
STEM SEPARATION & ARRANGEMENT (02_STEMS)
      ↓
VOCAL RECORDING & EDITING (03_VOCALS: LEAD, DOUBLES, HARMONIES, ADLIBS)
      ↓
PROCESSING & MIXING (04_PROCESSING, 05_BUSES)
      ↓
EXPORT (99_EXPORTS: instrumental, vocal, stem, premaster, FLAC, WAV)
```

---

## Project Sections (Canonical Structure)

Every new AETHERWOUND project should follow this folder and routing architecture. Not all folders will have tracks at project start; the structure is a scaffold that grows as the project develops.

### 00_REFERENCE
Purpose: Comparison and reference material, not part of the mix output.
Tracks:
- Reference A (external reference track — muted in mix, solo for A/B comparison)
- Reference B (secondary reference — muted)
- Monitor / Working Mix (optional — current rough mix routed here for quick playback)
Color: Gray / neutral (`#6A6A7A`)
Routing: Direct to monitor bus; not routed to master mix bus (or routed with -inf gain if kept in master chain)
Behavior: Reference tracks should never appear in exports. Scripts that prepare exports must mute or exclude this folder.

### 01_GENERATION
Purpose: Raw AI-generated audio, unprocessed source material, generation experiments.
Folder structure:
- SOURCE (main generated source file — full length, original render)
- EXPERIMENTS (variations, alternate generations, partial stems, test slices)
Color: Lavender (`#C8A8E8`)
Routing: All generation tracks routed to `GENERATION BUS` (optional sub-bus) or directly to `STEMS BUS` depending on how the material will be used.
Naming convention: `GEN_Src_[Type]_[Name]_[Version]` (e.g., `GEN_Src_Melodic_Arp_01.v2`)
Behavior: This folder is temporary. Once a generation is approved for arrangement, it should be moved (via script or manual operation) to `02_STEMS` and renamed to match stem naming conventions. The original in `GENERATION` can be kept for reference but should be muted once stemmed.

### 02_STEMS
Purpose: The actual production material — separated stems organized by role.
Subfolders:
- DRUMS (pink `#F0A0D0`): Kick, Snare, Hi-Hat, Percussion, Drum Bus
- BASS (blue `#6AB8F0`): Sub Bass, Bass Synth, Bass Line, Bass Bus
- MELODIC (purple `#A070E0`): Synth Lead, Pad, Arp, Melodic FX, Melodic Bus
- FX (cyan `#30D0D0`): Atmosphere, Glitch, Transition, Impact, FX Bus
- OTHER (gray `#6A6A7A`): Unclassified, experimental, temporary — should be resolved before final mix
Routing: Each stem category routes to its own bus (`DRUM BUS`, `BASS BUS`, `MELODIC BUS`, `FX BUS`). All stem buses route to `MIX BUS`.
Naming convention:
- Drum tracks: `DR_[Instrument]_[Variant]` (e.g., `DR_Kick_Main`, `DR_Snare_Layer`)
- Bass tracks: `BA_[Instrument]_[Variant]`
- Melodic tracks: `ML_[Instrument]_[Variant]`
- FX tracks: `FX_[Type]_[Variant]`
- Bus tracks: `BUS_[Category]`

### 03_VOCALS
Purpose: All vocal content — lead, doubles, harmonies, adlibs, processing.
Subfolders:
- LEAD (near-white `#F8F0F8`): Main vocal performance
- DOUBLES (rose-pink `#F0A0C0`): Double-tracked vocals
- HARMONIES (lavender-pink `#D8B0E8`): Harmony layers, backing vocals
- ADLIBS (coral-rose `#E87090`): Adlibs, spoken word, experimental vocal
- VOCAL FX (cyan `#30D0D0`): Reverb sends, delay sends, pitch-shift, vocal processing chains
Routing: All vocal tracks route to `VOCAL MIX BUS` (optional intermediate bus) or directly to `MIX BUS`. The `VOCAL FX` folder routes to the `VOCAL FX BUS`, which routes to `VOCAL MIX BUS` or `MIX BUS`.
Naming convention:
- Lead: `VOC_LEAD_[Part]` (e.g., `VOC_LEAD_Verse`, `VOC_LEAD_Chorus`)
- Doubles: `VOC_DBL_[Side/Type]` (e.g., `VOC_DBL_Left`, `VOC_DBL_R`)
- Harmonies: `VOC_HRM_[Type]` (e.g., `VOC_HRM_Upper`, `VOC_HRM_Lower`)
- Adlibs: `VOC_ADL_[Type]` (e.g., `VOC_ADL_Spoken`, `VOC_ADL_Whisper`)
- FX tracks: `VOC_FX_[Effect]` (e.g., `VOC_FX_ReverbSend`, `VOC_FX_Delay`)

### 04_PROCESSING
Purpose: Non-vocal processing — EQ, compression, effects, automation lanes, processing chains.
This folder is typically empty for arrangement and fills during mixing. It may contain:
- Automation-only tracks (no media items, only envelopes)
- Processing reference tracks (e.g., EQ curve analysis, spectrum reference)
- Sidechain key tracks (if using external sidechain signals)
Color: Deep charcoal / muted gold (`#B0A070` for bus-related processing, `#A070E0` for melodic processing tracks)
Note: Processing is primarily handled through FX chains on individual tracks and buses. This folder is for special cases.

### 05_BUSES
Purpose: The mix architecture. All buses live here.
Standard bus structure:
- `DRUM BUS` (pink)
- `BASS BUS` (blue)
- `MELODIC BUS` (purple)
- `FX BUS` (cyan)
- `VOCAL MIX BUS` (lavender-pink mix, optional but recommended)
- `MIX BUS` (gold)
- `MASTER` (high-contrast white/ice)
Routing: All stem buses → `MIX BUS` → `MASTER`. If `VOCAL MIX BUS` is used: `VOCAL` tracks → `VOCAL MIX BUS` → `MIX BUS`. The `REFERENCE` folder routes separately (not through `MIX BUS` unless specifically configured for comparison).
Notes: Buses should have meaningful FX chains installed (e.g., light compression on `MIX BUS`, reference limiter on `MASTER`). These FX chains are configured via `FX Chains` templates (Phase 2) but are applied manually or via script.

### 99_EXPORTS
Purpose: Output files, bounce files, render targets.
This folder contains markers (not audio tracks) that define export regions:
- `MARKER: INSTRUMENTAL` — region from start of `MIX BUS` content to end, excluding vocal sections
- `MARKER: VOCAL` — region covering the full vocal arrangement (for vocal-only export if needed)
- `MARKER: STEM_DRUMS` — region for drum stem bounce
- `MARKER: STEM_BASS` — region for bass stem bounce
- `MARKER: STEM_MELODIC` — region for melodic stem bounce
- `MARKER: STEM_FX` — region for FX stem bounce
- `MARKER: STEM_VOCALS` — region for vocal stem bounce
- `MARKER: FULL_MIX` — full song region
- `MARKER: PREMASTER` — same as full mix; used for premaster bounce
Note: These are markers, not tracks. The export workflow (`shura_prepare_export.lua`) verifies that these markers exist and creates them if missing. The actual rendering uses REAPER's `RPR_Render` or `File > Render project` with appropriate settings.

---

## Workflow Operations (Conceptual Actions)

These are the high-level operations that scripts and custom actions should support. Each maps to a combination of REAPER actions and script functions.

### PROJECT — Create AETHERWOUND Project
Trigger: Custom action / toolbar button / script call
What it does:
1. Creates new REAPER project
2. Creates folder structure (`00_REFERENCE` through `99_EXPORTS`)
3. Creates standard bus tracks (`DRUM BUS`, `BASS BUS`, etc.)
4. Sets initial colors (semantic palette)
5. Sets initial routing (stem categories → bus → mix → master)
6. Creates initial markers (`FULL_MIX`, `PREMASTER`)
7. Saves project to a new file (names: `AETHERWOUND_[Name]_v001.rpp` or user-defined)
Safety: Non-destructive (creates new file, does not modify existing project)
Script reference: `shura_create_project.lua` (Phase 2)

### PROJECT — Save Snapshot
Trigger: Keyboard shortcut (`Shift+S`) / toolbar button
What it does:
1. Saves current project (if dirty)
2. Creates timestamped copy (`AETHERWOUND_[Name]_v001_snapshot_YYYYMMDD_HHMMSS.rpp` in `/snapshots/` subfolder or user-defined location)
3. Updates project notes or script state file with timestamp and brief description (optional future feature)
Safety: Non-destructive (creates copy, does not delete original)
Script reference: `shura_snapshot.lua` (Phase 2)

### GENERATION — Import Generated Audio
Trigger: Custom action / script call
What it does:
1. Opens file browser or receives path from SHURA / external tool
2. Imports audio file(s) into `01_GENERATION / SOURCE` folder
3. Creates appropriate folder/track structure (e.g., `GEN_Src_Melodic_Arp_01`)
4. Sets initial color (lavender for generation source)
Safety: Non-destructive (adds media, does not remove existing)

### GENERATION — Create Generation Folder
Trigger: Custom action
What it does:
1. Creates `01_GENERATION / EXPERIMENTS` subfolder structure (optional)
2. Creates empty tracks in `01_GENERATION` with semantic naming
Safety: Non-destructive

### GENERATION — Prepare Generated Source
Trigger: Custom action / script
What it does:
1. Verifies generation source file exists
2. Creates a new track in `01_GENERATION` with the source file
3. Sets routing, color, and initial volume (0 dB default, muted or unmuted based on workflow preference)
Safety: Non-destructive

### STEMS — Create Stem Structure
Trigger: Custom action / script
What it does:
1. Verifies `02_STEMS` folder exists; creates subfolders (`DRUMS`, `BASS`, `MELODIC`, `FX`, `OTHER`) if missing
2. Creates bus tracks for each stem category (if not present)
3. Verifies routing from stem categories to mix architecture
4. Sets colors for new stem folders/tracks
Safety: Non-destructive
Script reference: `shura_create_stem_bus.lua` (Phase 2)

### STEMS — Organize Stems
Trigger: Custom action
What it does:
1. Scans `01_GENERATION` folder for approved sources
2. Moves/copies media items from `01_GENERATION` to appropriate `02_STEMS` subfolder (manual confirmation or automatic based on naming convention)
3. Updates track names to match stem naming convention
Note: This is a structural action; it does not edit audio. It may move items or create new items from the same source file.
Safety: Reversible (original generation folder preserved unless explicitly deleted by user)

### STEMS — Route Stems
Trigger: Custom action / script
What it does:
1. Verifies each stem category folder routes to its bus (`DRUMS` → `DRUM BUS`, etc.)
2. Verifies bus routing to `MIX BUS` → `MASTER`
3. Reports any missing connections
Safety: Non-destructive (only verifies/modifies routing, not audio)

### STEMS — Prepare Stem Export
Trigger: Custom action / script call
What it does:
1. Verifies stem markers exist (`STEM_DRUMS`, `STEM_BASS`, etc.); creates them if missing
2. Creates temporary region selections for each stem export
3. Prepares render settings (if configured) for stem bounce
4. Reports current state (ready / missing markers / missing routing)
Safety: Non-destructive (prepares but does not render; user confirms render)
Script reference: `shura_prepare_export.lua` (Phase 2)

### VOCALS — Create Vocal Stack
Trigger: Custom action (`Shift+V`) / script
What it does:
1. Creates `03_VOCALS / LEAD` track with initial setup (color, routing, basic FX chain reference)
2. Creates `03_VOCALS / DOUBLES` folder with `Double L` and `Double R` tracks (or user-defined structure)
3. Creates `03_VOCALS / HARMONIES` folder (optional; can be created on demand)
4. Creates `03_VOCALS / ADLIBS` folder (optional)
5. Creates `03_VOCALS / VOCAL FX` folder with routing (reverb/delay send tracks)
6. Sets routing: `LEAD` → `VOCAL MIX BUS`; `DOUBLES` → `VOCAL MIX BUS`; `VOCAL FX` → `VOCAL MIX BUS` (or `MIX BUS` depending on architecture preference)
Safety: Non-destructive; creates empty tracks, not audio
Script reference: `shura_create_vocal_stack.lua` (Phase 2)

### VOCALS — Create Doubles
Trigger: Custom action / sub-action of vocal stack
What it does:
1. Creates or verifies `DOUBLES` folder
2. Creates `Double L` and `Double R` (or `DBL_L` / `DBL_R`) tracks
3. Sets routing, colors, initial panning (optional: hard L/R for doubles if desired)
Safety: Non-destructive

### VOCALS — Create Harmonies
Trigger: Custom action
What it does:
1. Creates `HARMONIES` folder
2. Creates initial harmony tracks (`VOC_HRM_Upper`, `VOC_HRM_Lower`) — empty
3. Sets routing and color (lavender-pink mix)
Safety: Non-destructive

### VOCALS — Create Adlibs
Trigger: Custom action
What it does:
1. Creates `ADLIBS` folder
2. Creates `ADLIB` track
3. Sets routing and color (coral-rose)
Safety: Non-destructive

### MIX — Create Bus
Trigger: Custom action (`Shift+B`)
What it does:
1. Creates new bus track (folder or non-folder depending on use case)
2. Names it based on user input or standard convention (`BUS_[Category]`)
3. Sets color (gold `#B0A070` for standard bus; custom for special cases)
4. Sets routing: receives from appropriate source tracks; sends to `MIX BUS` (or user-defined destination)
Safety: Non-destructive
Script reference: `shura_create_stem_bus.lua` (Phase 2)

### MIX — Show Routing
Trigger: Custom action / script (`Shift+S` for routing visibility — but `Shift+S` is reserved for snapshot; routing visibility uses a different shortcut, e.g., `Ctrl+Shift+R` or a dedicated toolbar button)
What it does:
1. Opens routing view (if available) or displays routing summary via script message
2. Reports: which tracks route to which buses, which buses route to master, any unconnected tracks
Safety: Read-only
Script reference: `shura_inspect_project.lua` (Phase 3, partial feature)

### MIX — Open FX
Trigger: Custom action / standard REAPER action (recommended: use existing REAPER FX chain view action)
What it does: Opens FX chain for selected track or bus
Notes: This can be a direct REAPER action reference rather than a custom script.

### MIX — Open Mix Layout
Trigger: Custom action / layout switch (`F5` or similar — user-configurable)
What it does: Switches to MIX layout (mixer-heavy view, visible routing, meters, FX access)
Notes: Implemented via REAPER layout switching mechanism (`View > Window > Layout A`, etc.) or custom action that activates a saved window state.
Script/implementation reference: Layout definitions in `layouts/` (Phase 2)

### EXPORT — Prepare Instrumental
Trigger: Custom action / script
What it does:
1. Verifies `FULL_MIX` marker exists
2. Creates or verifies `INSTRUMENTAL` region (full mix region minus vocal sections — requires user-defined vocal region markers; can be approximated by using `FULL_MIX` region and relying on mix state at render time, or by creating a separate region)
3. Reports ready state
Note: A true instrumental export requires either (a) a separate region marker that excludes vocal sections, or (b) manual muting of vocal tracks before render. The script can assist by creating the marker but should not automatically mute tracks (destructive/misleading for the mix).
Safety: Non-destructive (prepares markers, does not mute or render without confirmation)

### EXPORT — Prepare Stem Export
Trigger: Custom action / script call (`Shift+X`)
What it does:
1. Verifies all stem markers exist (`STEM_DRUMS`, `STEM_BASS`, `STEM_MELODIC`, `STEM_FX`, `STEM_VOCALS`)
2. Verifies routing (each stem bus receives only its category tracks)
3. Reports ready state for each stem type
Safety: Non-destructive (only verifies, does not render)

### EXPORT — Prepare Premaster
Trigger: Custom action / script
What it does:
1. Verifies `MASTER` bus has appropriate FX chain (limiter, loudness reference if configured)
2. Reports peak level, approximate loudness (if metering script available), and any clipping risk
3. Creates `PREMASTER` region (same as `FULL_MIX` unless user specifies a different start/end)
Note: Actual loudness measurement requires either (a) a JSFX meter plugin, (b) REAPER's built-in meters (approximate), or (c) external analysis after render. The script reports approximate state based on available data.

### EXPORT — FLAC / WAV Export
Trigger: Custom action / script / REAPER render action
What it does:
1. Opens REAPER render dialog (or calls `RPR_Render` with predefined settings if fully automated)
2. Applies preset settings: format (FLAC or WAV), bit depth (24-bit for archive, 16-bit for delivery), sample rate (match project)
3. Reports output file path
Note: Full automation of render settings requires either custom script control of render parameters (complex in REAPER) or manual confirmation. The recommended approach is a script that prepares settings and opens the render dialog with preset values filled, requiring only user confirmation to execute.

### SHURA — Status / Refresh Project State
Trigger: Custom action / toolbar button / script (`Shift+A` for automation/status — but `Shift+A` for SHURA status, `Shift+M` for mix, etc. — final shortcuts defined in Phase 2)
What it does:
1. Reads current project info (track count, folder count, BPM, time signature, length, master peak, selected track info)
2. Reports status in a text window, console message, or (Phase 4) custom SHURA status panel
3. Updates any internal script state files (if used for tracking)
Notes: This is informational. It does not modify the project. It provides SHURA (or the user) with a quick snapshot of the current environment.
Script reference: `shura_inspect_project.lua`, `shura_status.lua` (Phase 3-4)

---

## Keyboard System Design (Mental Model)

The AETHERWOUND keyboard system uses a layered modifier approach rather than overriding all default REAPER shortcuts.

### Layer 0: Default REAPER Shortcuts (Preserved)
All standard REAPER shortcuts remain functional (`Space` = play/stop, `Ctrl+Space` = loop play, `R` = record, etc.). The user does not lose any existing capability.

### Layer 1: Direct Semantic Actions (No Modifier — Custom Actions Only)
These are new actions assigned to keys that REAPER does not use by default, or keys reassigned with user awareness:
- `F1` — SHURA Status (show current project state summary)
- `F2` — AETHERWOUND Theme Toggle (switch between AETHERWOUND and default theme)
- `F3` — Open AETHERWOUND Project Template
- `F4` — Create AETHERWOUND Project (new file with template)
- `F5` — Create Vocal Stack (`Shift+V` is reserved; `F5` is faster access)
- `F6` — Create Stem Bus (`Shift+B` reserved; `F6` faster)
- `F7` — Snapshot (`Shift+S` reserved; `F7` faster)
- `F8` — Show Routing / Inspect Project (`Shift+R` or similar reserved)
Note: These are conceptual assignments. The final keymap file (`AETHERWOUND.Keymap.ReaperKeyMap`) defines the exact bindings.

### Layer 2: Modifier + Semantic Key (Shift / Ctrl / Option / Command)
These are the primary custom shortcuts that layer over defaults without collision:

| Key | Modifier | Action Concept | Actual Implementation |
|---|---|---|---|
| `V` | `Shift` | Create Vocal Stack | Script call (`shura_create_vocal_stack.lua`) |
| `B` | `Shift` | Create Bus / Stem Bus | Script call (`shura_create_stem_bus.lua`) |
| `S` | `Shift` | Save Snapshot | Script call (`shura_snapshot.lua`) |
| `X` | `Shift` | Prepare Stem Export / Stem Workflow | Script call (`shura_prepare_export.lua` or combined stem/export script) |
| `E` | `Shift` | Export / Prepare Export | Script call (`shura_prepare_export.lua`) or render preset activation |
| `C` | `Shift` | Create Project / New AETHERWOUND | Script call (`shura_create_project.lua`) |
| `A` | `Shift` | Automation / SHURA Status / Inspect | Script call (`shura_inspect_project.lua` or `shura_status.lua`) |
| `R` | `Shift` | Routing View / Show Routing | Layout switch or routing summary script |
| `M` | `Shift` | Open Mix Layout | Layout switch (to MIX layout) |
| `1`–`9` | `Ctrl` | Quick project section jump | Custom action (e.g., `Ctrl+1` = select all `00_REFERENCE` tracks; `Ctrl+2` = select `02_STEMS` folder; etc.) — optional, deferred to Phase 2/5 |

Note: Some of these concepts overlap with the toolbar design. The keyboard system and toolbar system are complementary: keyboard for speed (experienced user), toolbar for discoverability (new user or SHURA-assisted operation).

---

## Layout System

Layout switching in REAPER is handled through `View > Window > Layout` options or via custom actions that activate specific saved window states. The AETHERWOUND architecture defines conceptual layouts rather than forcing a specific REAPER layout mechanism (since REAPER's layout system varies by version and platform).

### CREATE Layout
Purpose: Arrangement-focused; minimal mixer distraction.
Characteristics:
- Large track view (arrangement area takes most screen)
- Mixer hidden or minimized (only visible when needed)
- Transport clearly visible
- Reference folder expanded (visible for A/B comparison during arrangement)
- Generation folder expanded (visible for source selection)
- Stem folders collapsed (hidden until arrangement is ready for mixing)
Usage: Early arrangement, stem selection, vocal recording setup.
Switch method: Custom action (`F3` / `Ctrl+C` / toolbar button) that activates saved layout or runs a script that sets mixer visibility, track height, and folder collapse state.

### EDIT Layout
Purpose: Editing-focused; detailed item/take controls.
Characteristics:
- Large track view with detailed item display (take lanes visible)
- Editor visible (if using REAPER's MIDI/note editor)
- Mixer visible but compact (only selected track's mixer strip fully expanded)
- Transport visible but small
- Reference folder collapsed (not needed during editing)
Usage: Detailed vocal editing, stem editing, automation envelope editing, MIDI editing.

### MIX Layout
Purpose: Mixer-heavy; visible routing, meters, FX access.
Characteristics:
- Mixer takes primary screen space (large mixer strips, visible routing)
- Track view visible but smaller (only for item selection, not arrangement)
- Routing matrix visible (REAPER's routing view or custom routing summary panel)
- FX windows easily accessible (either via toolbar shortcut or visible FX chain area)
- Master bus prominently visible (tall, centered)
Usage: Mixing, bus processing, master processing, loudness reference comparison.

### MASTER Layout
Purpose: Master channel focus; loudness metering; final verification.
Characteristics:
- Master track maximally visible (tall mixer strip, large meters)
- Loudness/reference meters visible (if available via JSFX or plugin)
- Spectrum/reference analysis visible (if available)
- All production tracks collapsed (not needed for final master check)
- Only master FX chain and output controls prominently visible
Usage: Final mix verification, loudness measurement, export confirmation, premaster check.

### SHURA Layout
Purpose: SHURA-assisted operation; clear track hierarchy; easy access to semantic workflow actions.
Characteristics:
- Track hierarchy clearly visible (folder structure expanded, names readable)
- SHURA status panel visible (Phase 4 — custom interface or script window showing project state)
- Toolbar visible with SHURA-oriented actions (status, inspect, create project, create vocal stack, etc.)
- Mixer visible but not dominant (balanced between track view and mixer)
- Routing visible (routing summary or routing view active)
Usage: SHURA-driven automation, project inspection, automated workflow steps, status checking.
Note: This layout is optional until Phase 4. Before Phase 4, the SHURA status interface is a script message or console window rather than a dedicated panel.

---

## Toolbar Design (Conceptual)

The toolbar is a compact set of buttons organized by production phase, not by REAPER's default toolbar structure. The toolbar definitions are stored in the repository (`toolbars/toolbar_notes.md`) and applied via REAPER's toolbar customization mechanism or via script-based installation instructions.

### Group 1: PROJECT (Left)
Buttons (left to right):
- New AETHERWOUND Project (script: `shura_create_project.lua`)
- Save (standard REAPER save action)
- Snapshot / Checkpoint (script: `shura_snapshot.lua`)
Note: Only 3 buttons. The principle is that project-level actions are rarely needed compared to playback/edit actions.

### Group 2: PLAYBACK (Center-Left)
Buttons:
- Play / Stop (standard REAPER transport action — same button or separate)
- Record (standard)
- Loop On/Off (standard)
Note: Standard transport actions; no custom scripts needed unless special loop behavior is desired.

### Group 3: EDIT (Center)
Buttons:
- Split (`S` — standard action, but available via toolbar)
- Glue / Consolidate (standard REAPER consolidate action — useful for stem work)
- Undo (standard)
- Redo (standard)
- Automation Mode Toggle (standard REAPER automation mode action)

### Group 4: GENERATION (Center-Right)
Buttons:
- Import Generated Audio (script or standard import with preset)
- Prepare Generated Source (script: `shura_create_project` sub-action or dedicated script)
- Create Generation Folder (script: creates empty folder structure)
- Create Experiment Track (script: creates new track in `01_GENERATION`)

### Group 5: STEMS (Right-Center)
Buttons:
- Create Stem Structure (script: verifies/creates `02_STEMS` folders and bus tracks)
- Organize Stems (script: verifies stem routing, reports state)
- Route Stems (script: verifies routing connections)
- Prepare Stem Export (script: verifies markers, reports ready state)

### Group 6: VOCALS (Right)
Buttons:
- Create Lead Stack (script: creates lead vocal track + basic routing)
- Create Doubles (script: creates double folder + tracks)
- Create Harmonies (script: creates harmony folder + initial tracks)
- Create Adlib Tracks (script: creates adlib folder + track)
- Create Vocal FX Routing (script: creates vocal FX folder + routing)
Note: Some of these could be combined into the full "Create Vocal Stack" action (`Shift+V` / `F5`). The toolbar provides individual buttons for granular control.

### Group 7: MIX (Far Right — Small)
Buttons:
- Open Mix Layout (layout switch)
- Create Bus (script: `shura_create_stem_bus.lua`)
- Show Routing (script: routing summary / inspection)
- Open FX (standard REAPER action or script reference)

### Group 8: EXPORT (Far Right — Separate Section or Bottom Row)
Buttons:
- Instrumental (script: verifies `FULL_MIX` / `INSTRUMENTAL` markers)
- Vocal (script: verifies vocal markers / prepares vocal region)
- Stem Export (script: verifies stem markers)
- Premaster (script: verifies master FX / loudness state)
- FLAC / WAV (script: opens render dialog with preset)
Note: These buttons prepare; they do not automatically render. The user confirms render settings before execution (except for fully automated workflows configured separately).

### Group 9: SHURA (Top Bar or Separate Toolbar)
Buttons:
- SHURA Status (script: `shura_status.lua` or `shura_inspect_project.lua`)
- Refresh Project State (re-run inspection, update status)
- SHURA Actions / Bridge (future: connection status, command execution interface — Phase 4)
Note: Before Phase 4, the SHURA toolbar group is minimal (status only). The full SHURA interface (bidirectional communication, command panel) requires Phase 4 architecture.

---

## Testing Workflow (Manual Verification)

These steps verify that the AETHERWOUND environment functions correctly without relying on automated test frameworks.

### Basic Function (Every Session)
1. Launch REAPER.
2. Verify AETHERWOUND theme loads (or can be loaded manually).
3. Verify toolbar is visible (if installed).
4. Verify keyboard shortcuts work (`Space` = play; custom shortcuts respond).

### Project Creation Test
1. Create new AETHERWOUND project (`New AETHERWOUND Project` action or open template).
2. Verify folder structure exists (`00_REFERENCE`, `01_GENERATION`, `02_STEMS`, `03_VOCALS`, `04_PROCESSING`, `05_BUSES`, `99_EXPORTS`).
3. Verify bus tracks exist (`DRUM BUS`, `BASS BUS`, etc.).
4. Verify master track exists and routes correctly.
5. Verify colors match semantic palette (lavender for generation, pink for drums, etc.).
6. Save project with new name (do NOT overwrite AW01).

### Vocal Stack Test
1. In test project, trigger `Create Vocal Stack`.
2. Verify `03_VOCALS` folder and subfolders (`LEAD`, `DOUBLES`, `HARMONIES`, `ADLIBS`, `VOCAL FX`) exist.
3. Verify tracks have correct colors.
4. Verify routing: `LEAD` → `VOCAL MIX BUS`; `DOUBLES` → `VOCAL MIX BUS`; `VOCAL FX` → `VOCAL MIX BUS` (or `MIX BUS` depending on architecture).
5. Verify no audio files were created or deleted (non-destructive).

### Stem Workflow Test
1. In test project, trigger `Create Stem Structure`.
2. Verify `02_STEMS` subfolders and bus tracks exist.
3. Verify routing: `DRUMS` folder → `DRUM BUS` → `MIX BUS` → `MASTER`.
4. Trigger `Show Routing` (if implemented); verify routing summary reports correctly.
5. Trigger `Prepare Stem Export`; verify markers (`STEM_DRUMS`, etc.) exist or are reported missing.

### Export Workflow Test
1. In test project, trigger `Prepare Premaster`.
2. Verify master bus state is reported (FX chain present, no obvious clipping).
3. Verify `FULL_MIX` and `PREMASTER` markers exist.
4. Manually open render dialog; verify format settings match AETHERWOUND defaults (FLAC, 24-bit, 48kHz or project rate).
5. Execute render to a temporary file; verify output exists and is readable.
6. Delete temporary output file (clean up after test).

### MCP Integration Test
1. Verify `reaper_mcp_server.lua` is loaded (Action list or script console).
2. Verify file-based IPC directory exists (`TMPDIR/reaper_mcp/`).
3. Write a test `command.json` with a safe command (e.g., `transport_play` or `project_get_info`).
4. Read response from `response.json`; verify JSON format and success/error status.
5. Delete test command/response files (clean up).
Note: This is a low-level protocol test. The Python bridge (`reaper_mcp_client.py`) is tested separately (Phase 3) by verifying that Python calls to the bridge produce the same file-based results.

---

## Safety Rules (Every Script / Action)

Every custom script and action must follow these rules:

1. **No destructive behavior without explicit user confirmation.** Actions that delete tracks, delete media items, overwrite files, or change routing in ways that would alter the mix must either (a) be clearly separated (e.g., a "Delete Generation Folder" action that requires a confirmation dialog), or (b) not exist as automatic actions.

2. **Fail gracefully.** All scripts use `pcall` (Lua) or `try/except` (Python). If a command fails (track not found, file not present, routing missing), the script reports the error clearly (in console, message box, or status output) rather than crashing REAPER or producing silent failure.

3. **Avoid hardcoded absolute paths.** Scripts reference files and directories relative to the current project (`reaper.GetProject(0)` in Python; `reaper.GetProject()` in Lua) or relative to the repository (`~/projectSHURA/` is acceptable as a base reference, but scripts should verify the directory exists before using it).

4. **Use existing actions first.** Before writing a custom Lua script that performs an operation, verify whether REAPER's native action list (`Actions > Show action list`) already has an equivalent action. If it does, the custom script should call that action (`reaper.Main_OnCommand`) rather than duplicating the logic.

5. **Document behavior.** Every script file includes comments explaining: (a) what it does, (b) what inputs it requires, (c) what outputs it produces, (d) any safety considerations, (e) how to test it safely.

6. **Test in disposable project.** No destructive automation is tested against `AW01_prototype_v003.rpp` or any other real project. All automation testing uses temporary project files created specifically for testing.

---

## References

- Canonical folder architecture: See `ARCHITECTURE.md` (system layer model) and this document's section "Project Sections."
- Semantic naming: See `COLOR_SEMANTICS.md` (color mapping) and workflow notes above.
- Script references: See `scripts/` directory (planned / implemented files listed in `ARCHITECTURE.md` file mapping).
- MCP protocol: See `docs/MCP.md` (MCP evaluation and integration notes).
