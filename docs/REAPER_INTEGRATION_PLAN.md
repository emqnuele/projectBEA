# REAPER Integration Plan
Status: DONE (research complete, no implementation)
Date: 2026-09-12

## Status
Research complete. REAPER is installed but **no MCP server exists**. Integration requires a custom adapter bridge.

## Installation Details

- **Version**: REAPER 7.79.0 (build 06dd787u)
- **Install path**: `/Applications/REAPER.app`
- **Python API**: `/Applications/REAPER.app/Contents/Plugins/reaper_python.py`
- **User data**: `/Users/ultraviollett/Library/Application Support/REAPER/`
  - `reaper.ini` (config, 42 lines — minimal OSC/python config)
  - `Scripts/` (with `Cockos/` subdirectory)
  - `UserPlugins/` (empty)

## Verified Capabilities

### DIRECTLY AUTOMATABLE

| Capability | Interface | Evidence |
|---|---|---|
| ReaScript (Python) | `reaper_python.py` with 730 `RPR_*` functions | File exists, 154KB, 730 exported functions |
| ReaScript (Lua) | Built-in Lua interpreter | `Default_6.0_theme_adjuster.lua`, `Default_7.0_theme_adjuster.lua` in Scripts dir |
| ReaScript (EBASIC/JScript) | Built-in ELEnstein script engine | Part of standard REAPER install |
| Built-in web server | `reaper_www_root/` directory (`basic.html`, `click.html`, `fancier.html`, `index.html`, `lyrics.html`, `main.js`) | 5 files present in app bundle |
| OSC (Open Sound Control) | `Default.ReaperOSC`, `LogicPad.ReaperOSC`, `LogicTouch.ReaperOSC` config templates | Found in `InstallFiles/OSC/` |
| MIDI control | Built-in MIDI learn and control | Part of core REAPER |
| Project file manipulation | `.rpp` files (plain text/XML format) | Standard REAPER feature |
| JSFX (JavaScript audio effects) | Built-in JS engine | Part of core REAPER |

### AUTOMATABLE WITH CUSTOM ADAPTER

| Capability | Adapter Approach | Complexity |
|---|---|---|
| Full REAPER control via Python | Write a ReaScript Python script that runs headless, reads commands from stdin/file, and answers via stdout/HTTP | Medium |
| MCP server for REAPER | Bridge: Python ReaScript (using `reaper_python.py`) ↔ MCP protocol wrapper | Medium-High |
| OSC-based control from Hermes | Hermes sends OSC messages to REAPER's OSC input (configured in `reaper.ini`) | Low-Medium |
| HTTP/Web API bridge | Use REAPER's built-in web server endpoints, expose as MCP | Medium |

### MANUAL

| Task | Reason |
|---|---|
| Initial REAPER preferences setup | Requires GUI interaction for audio device, buffer size, etc. |
| Plugin scanning | Initial plugin database population requires GUI launch |
| Project template creation | Best done interactively first, then automated via script |

### UNVERIFIED

| Capability | Status |
|---|---|
| REAPER headless mode | REAPER's `--help` hangs when invoked from terminal (attempts GUI launch). No documented `--no-gui` or headless CLI flag confirmed. |
| REAPER MCP server | No MCP server found in config, pip, or Homebrew. |
| JSFX extension SDK | Not inspected (`reaper_js` integration libraries not found) |
| SWS Extension | Not found installed (would provide additional Python functions) |
| ReaPack | Not found installed (community extension repository) |
| reachengos | Not installed |
| REAPER Python external control surface API | `reaper_python.py` present but requires REAPER running for `RPR_*` calls to resolve |

## Recommended Architecture

The safest architecture for Hermes → REAPER control is a **two-layer bridge**:

```
Hermes Agent
  ↓ (MCP protocol)
Custom REAPER MCP Server (Python)
  ↓ (stdin/stdout or HTTP)
REAPER ReaScript (Python, running inside REAPER)
  ↓ (RPR_* API calls)
REAPER Engine
```

### Layer 1: MCP Server (external to REAPER)
- Written in Python using the `mcp` SDK
- Runs as a stdio MCP server (simplest for local deployment)
- Configured in `~/.hermes/config.yaml` under `mcp_servers`
- Exposes tools matching the SHURA_V1 architecture spec (project, track, transport, etc.)

### Layer 2: ReaScript Bridge (inside REAPER)
- Python script loaded via REAPER's ReaScript console
- Listens for commands from the MCP server via:
  - **Named pipe** (recommended — cross-platform, no network port needed)
  - **Local HTTP** (REAPER's built-in web server — already has `reaper_www_root`)
  - **OSC** (if OSC interface is simpler)
- Receives commands, calls `RPR_*` functions, returns results as JSON

### Why not OSC-only?
REAPER's native OSC interface controls transport, mixer, and track parameters. However, it has limited capability for project creation, clip editing, and MIDI note manipulation. The Python ReaScript API (`reaper_python.py` with 730 RPR functions) covers the full REAPER API surface.

### Why not direct REAPER web server?
REAPER's built-in web server serves static HTML/JS pages from `reaper_www_root/` but does not expose a JSON API for project manipulation. It's designed for web-based MIDI controllers, not programmatic project editing.

## Tool Families (mapping to spec)

The SHURA_V1 architecture spec (§4.C) defines these REAPER tool families. Each maps to `RPR_*` functions:

| Spec Family | Key RPR Functions | MCP Tool Prefix |
|---|---|---|
| Project | `RPR_GetCurrentProject`, `RPR_SaveOrCreateThread`, `RPR_Main_OnCommand` | `reaper_project_*` |
| Track | `RPR_AddTrack`, `RPR_GetTrack`, `RPR_GetSetMediaTrackInfo` | `reaper_track_*` |
| Transport | `RPR_Play`, `RPR_Stop`, `RPR_SetPlayState` | `reaper_transport_*` |
| Audio Import/Export | `RPR_AddMediaItemToTrack`, `RPR_Render` | `reaper_audio_*` |
| MIDI | `RPR_MIDI_*` (note add, delete, insert) | `reaper_midi_*` |
| Instrument/Plugin | `RPR_TrackFX_AddByChunk`, `RPR_TrackFX_SetParam` | `reaper_plugin_*` |
| Automation | `RPR_SetTrackSendInfo`, `RPR_GetTrackEnvelope` | `reaper_automation_*` |
| Render/Mix | `RPR_Render`, `RPR_ShowConsoleMsg` | `reaper_render_*` |

## Next Step
This plan establishes that a REAPER MCP bridge is technically feasible via Python ReaScript. **Do NOT build the MCP server yet** — wait for canonical decisions on ATLAS/FORGE structure and the Phase 1 stabilization tasks.
