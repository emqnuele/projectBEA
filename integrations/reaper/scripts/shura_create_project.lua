-- shura_create_project.lua
-- AETHERWOUND / ProjectSHURA — REAPER Workflow Script
-- Phase: 2 (Workflow) | Status: ACTIVE / Prototype
-- Author: SHURA

-- PURPOSE:
-- Creates a new AETHERWOUND project structure with standard folder architecture.
-- This script creates a new REAPER project (or applies structure to current project)
-- using the canonical folder hierarchy defined in ARCHITECTURE.md and WORKFLOW.md.

-- SAFETY RULES:
-- - Does NOT delete existing tracks or media items (non-destructive)
-- - Creates empty folder/track structures only
-- - Fails gracefully (pcall wrapped) with clear console messages
-- - Does not hardcode machine-specific paths (uses relative/repository paths only)

-- USAGE:
-- Load via REAPER Actions > Show action list > ReaScript: Load
-- Or install to ~/Library/Application Support/REAPER/Scripts/AETHERWOUND/
-- Then run via action list or custom toolbar/shortcut.

-- REFERENCES:
-- docs/ARCHITECTURE.md — folder architecture and routing
-- docs/WORKFLOW.md — naming conventions and production flow
-- docs/COLOR_SEMANTICS.md — semantic color mapping

local script_name = "shura_create_project"
local script_version = "1.0"

-- ============================================================
-- Helper Functions
-- ============================================================

local function info(msg)
  reaper.ShowConsoleMsg("[" .. script_name .. " v" .. script_version .. "] " .. tostring(msg) .. "\n")
end

local function warn(msg)
  reaper.ShowConsoleMsg("[" .. script_name .. " WARNING] " .. tostring(msg) .. "\n")
end

local function error_msg(msg)
  reaper.ShowConsoleMsg("[" .. script_name .. " ERROR] " .. tostring(msg) .. "\n")
end

-- ============================================================
-- Main Function: Create AETHERWOUND Project Structure
-- ============================================================

local function create_aetherwound_project()
  -- Start undo block for all changes
  reaper.Undo_BeginBlock()

  info("Starting AETHERWOUND project structure creation...")

  -- Note: This script creates the folder/track structure in the CURRENT project.
  -- To create a completely NEW project file (with a new name), the user should:
  --   1. Create a new project manually (File > New Project) or use a template
  --   2. Run this script to apply the folder structure
  -- Alternatively, this script could be extended to save the current state as a new file,
  -- but that is deferred to avoid accidental file creation.

  -- Check if REAPER project exists (current project is always 0 in REAPER Lua)
  local proj_exists = pcall(function() return reaper.CountTracks(0) end)
  if not proj_exists then
    error_msg("No active REAPER project found. Please create or open a project first.")
    reaper.Undo_EndBlock(script_name .. ": error — no project", -1)
    return false
  end

  info("Active project detected. Applying folder structure...")

  -- Define the folder/track names based on canonical architecture
  -- The structure is: 00_REFERENCE, 01_GENERATION, 02_STEMS, 03_VOCALS, 04_PROCESSING, 05_BUSES, 99_EXPORTS
  -- Note: Some of these are folder tracks; others are standard tracks with folder properties.

  local folders = {
    {name = "00_REFERENCE", color_hex = "#6A6A7A", role = "reference"},
    {name = "01_GENERATION", color_hex = "#C8A8E8", role = "generated"},
    {name = "02_STEMS", color_hex = "#A070E0", role = "melodic"},  -- Folder for all stems
    {name = "03_VOCALS", color_hex = "#F8F0F8", role = "vocal"},
    {name = "04_PROCESSING", color_hex = "#A070E0", role = "melodic"},
    {name = "05_BUSES", color_hex = "#B0A070", role = "bus"},
  }

  -- Note: The 02_STEMS folder should contain sub-folders (DRUMS, BASS, MELODIC, FX, OTHER)
  -- The 03_VOCALS folder should contain sub-folders (LEAD, DOUBLES, HARMONIES, ADLIBS, VOCAL FX)
  -- The 05_BUSES folder contains bus tracks (DRUM BUS, BASS BUS, etc.)

  -- For Phase 2 prototype, we create the top-level folders and a minimal set of standard tracks.
  -- Full sub-structure creation is available via sub-scripts (`create_stem_bus`, `create_vocal_stack`).

  -- Get track count to know where to insert
  local track_count = reaper.CountTracks(0)

  info("Current track count: " .. track_count)
  info("Creating standard AETHERWOUND folder structure (top-level only for prototype)...")

  -- Create reference folder (top-level folder)
  local ref_track = reaper.InsertTrackAtIndex(track_count, true)
  if ref_track then
    reaper.GetSetMediaTrackInfo_String(ref_track, "P_NAME", "00_REFERENCE", true)
    -- Note: Full theme customization (color) requires theme settings; this script applies naming only.
    -- Color customization is handled by the theme customization script (`AETHERWOUND_Theme_Apply.lua`).
  end

  -- Create generation folder
  local gen_track = reaper.InsertTrackAtIndex(track_count + 1, true)
  if gen_track then
    reaper.GetSetMediaTrackInfo_String(gen_track, "P_NAME", "01_GENERATION", true)
  end

  -- Create stems folder
  local stems_track = reaper.InsertTrackAtIndex(track_count + 2, true)
  if stems_track then
    reaper.GetSetMediaTrackInfo_String(stems_track, "P_NAME", "02_STEMS", true)
  end

  -- Create vocals folder
  local vocals_track = reaper.InsertTrackAtIndex(track_count + 3, true)
  if vocals_track then
    reaper.GetSetMediaTrackInfo_String(vocals_track, "P_NAME", "03_VOCALS", true)
  end

  -- Create processing folder
  local proc_track = reaper.InsertTrackAtIndex(track_count + 4, true)
  if proc_track then
    reaper.GetSetMediaTrackInfo_String(proc_track, "P_NAME", "04_PROCESSING", true)
  end

  -- Create buses folder (folder for bus tracks)
  local buses_track = reaper.InsertTrackAtIndex(track_count + 5, true)
  if buses_track then
    reaper.GetSetMediaTrackInfo_String(buses_track, "P_NAME", "05_BUSES", true)
  end

  info("Top-level folder structure created.")
  info("Note: Full stem sub-structure (DRUMS, BASS, MELODIC, etc.) requires additional setup.")
  info("Use 'Create Stem Bus' and 'Create Vocal Stack' actions for detailed structure.")

  -- Create initial markers for full mix and stem exports
  -- Note: Markers are added to the project timeline
  -- For prototype, we add basic markers at time 0
  local marker_idx = reaper.AddProjectMarker(0, false, 0, 0, "FULL_MIX", -1)
  if marker_idx >= 0 then info("Created FULL_MIX marker.") end

  info("Project structure creation complete.")
  info("Remember: This script creates structure only — it does not create new audio files.")

  -- End undo block
  reaper.Undo_EndBlock(script_name .. ": created AETHERWOUND structure (prototype)", -1)

  return true
end

-- ============================================================
-- Execute with error handling
-- ============================================================

local ok, result = pcall(create_aetherwound_project)
if not ok then
  error_msg("Script failed with exception: " .. tostring(result))
  reaper.Undo_EndBlock(script_name .. ": failed with exception", -1)
  return false
end

if result then
  info("Project structure created successfully.")
else
  warn("Project structure creation completed with warnings or partial success.")
end

return result
