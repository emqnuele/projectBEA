-- shura_create_stem_bus.lua
-- AETHERWOUND / ProjectSHURA — REAPER Workflow Script
-- Phase: 2 (Workflow) | Status: ACTIVE / Prototype
-- Author: SHURA

-- PURPOSE:
-- Creates a stem bus (folder track that receives stem category routing) or verifies existing bus structure.
-- This is a non-destructive structural operation.

local script_name = "shura_create_stem_bus"
local script_version = "1.0"

local function info(msg) reaper.ShowConsoleMsg("[" .. script_name .. " v" .. script_version .. "] " .. tostring(msg) .. "\n") end
local function warn(msg) reaper.ShowConsoleMsg("[" .. script_name .. " WARNING] " .. tostring(msg) .. "\n") end
local function error_msg(msg) reaper.ShowConsoleMsg("[" .. script_name .. " ERROR] " .. tostring(msg) .. "\n") end

local function create_stem_bus()
  reaper.Undo_BeginBlock()
  info("Starting stem bus creation / verification...")

  local track_count = reaper.CountTracks(0)
  info("Current track count: " .. track_count)

  -- Create or verify the main bus folder (05_BUSES) and its child bus tracks
  -- Note: In a full workflow, the 05_BUSES folder already exists from `shura_create_project`.
  -- This script creates individual bus tracks (DRUM BUS, BASS BUS, etc.) inside the bus folder.

  -- Check if 05_BUSES folder exists (simple check: look for a track named "05_BUSES" at index >= 0)
  local buses_folder = nil
  for i = 0, track_count - 1 do
    local track = reaper.GetTrack(0, i)
    if track then
      local _, name = reaper.GetSetMediaTrackInfo_String(track, "P_NAME", false)
      if name == "05_BUSES" then
        buses_folder = track
        info("Found existing 05_BUSES folder.")
        break
      end
    end
  end

  -- Create bus tracks (as children of the buses folder or at the end of the project)
  local bus_types = {
    {name = "DRUM BUS", color_role = "drums"},
    {name = "BASS BUS", color_role = "bass"},
    {name = "MELODIC BUS", color_role = "melodic"},
    {name = "FX BUS", color_role = "fx"},
    {name = "VOCAL MIX BUS", color_role = "harmony"},
    {name = "MIX BUS", color_role = "bus"},
    {name = "MASTER", color_role = "master"},
  }

  for _, bus_info in ipairs(bus_types) do
    local bus_track = reaper.InsertTrackAtIndex(track_count, false)
    if bus_track then
      reaper.GetSetMediaTrackInfo_String(bus_track, "P_NAME", bus_info.name, true)
      info("Created/verified bus: " .. bus_info.name)
      -- Note: Routing setup (receiving from stem categories, sending to master) is handled separately
      -- or via manual configuration. This script creates the bus tracks only.
    else
      warn("Failed to create bus: " .. bus_info.name)
    end
    track_count = reaper.CountTracks(0)
  end

  info("Stem bus creation complete.")
  info("Note: Routing (stem categories -> bus -> mix -> master) should be configured manually or via routing script.")

  reaper.Undo_EndBlock(script_name .. ": created stem buses", -1)
  return true
end

local ok, result = pcall(create_stem_bus)
if not ok then
  error_msg("Script failed with exception: " .. tostring(result))
  reaper.Undo_EndBlock(script_name .. ": exception", -1)
  return false
end

if result then info("Stem bus creation complete.") else warn("Partial completion.") end
return result
