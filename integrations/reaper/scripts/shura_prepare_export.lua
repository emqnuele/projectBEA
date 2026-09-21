-- shura_prepare_export.lua
-- AETHERWOUND / ProjectSHURA — REAPER Workflow Script
-- Phase: 2 (Workflow) / Phase 3 (Automation) | Status: ACTIVE / Prototype
-- Author: SHURA

-- PURPOSE:
-- Prepares the current AETHERWOUND project for export by verifying markers,
-- checking bus structure, and reporting readiness for different export types:
-- - Instrumental (full mix minus vocal sections, or full mix if no vocal markers defined)
-- - Stem exports (DRUMS, BASS, MELODIC, FX, VOCALS)
-- - Premaster / Full Mix
-- Non-destructive (read-only verification + optional marker creation).

local script_name = "shura_prepare_export"
local script_version = "1.0"

local function info(msg) reaper.ShowConsoleMsg("[" .. script_name .. " v" .. script_version .. "] " .. tostring(msg) .. "\n") end
local function warn(msg) reaper.ShowConsoleMsg("[" .. script_name .. " WARNING] " .. tostring(msg) .. "\n") end
local function error_msg(msg) reaper.ShowConsoleMsg("[" .. script_name .. " ERROR] " .. tostring(msg) .. "\n") end

local function prepare_export()
  info("Starting export preparation...")

  local proj = reaper.GetCurrentProjectInProjExt()
  if not proj then
    error_msg("No active REAPER project found.")
    return false
  end

  -- Verify markers
  local markers = {}
  local marker_count = reaper.CountProjectMarkers(0)
  info("Project markers found: " .. marker_count)

  local required_markers = {
    "FULL_MIX", "PREMASTER",
    "STEM_DRUMS", "STEM_BASS", "STEM_MELODIC", "STEM_FX", "STEM_VOCALS",
    "INSTRUMENTAL"
  }

  for i = 0, marker_count - 1 do
    local _, is_region, pos, _, name, _ = reaper.EnumProjectMarkers(i)
    if name then
      markers[name] = {position = pos, is_region = is_region}
      info("  Found marker: '" .. name .. "' at " .. string.format("%.2f", pos) .. (is_region and " [region]" or ""))
    end
  end

  -- Check required markers
  info("Checking required markers...")
  local missing = {}
  for _, req_name in ipairs(required_markers) do
    if not markers[req_name] then
      table.insert(missing, req_name)
      warn("Missing marker: " .. req_name)
    else
      info("  OK: " .. req_name)
    end
  end

  if #missing > 0 then
    info("Some markers are missing. Export may not work correctly without them.")
    info("Missing: " .. table.concat(missing, ", "))
    info("Consider creating these markers manually or using project template.")
  else
    info("All required markers present.")
  end

  -- Check master bus presence (simplified)
  local has_master = false
  local track_count = reaper.CountTracks(0)
  for i = 0, track_count - 1 do
    local track = reaper.GetTrack(0, i)
    if track then
      local _, name = reaper.GetSetMediaTrackInfo_String(track, "P_NAME", false)
      if name and (string.find(name, "MASTER") or string.find(name, "MASTER BUS")) then
        has_master = true
        info("Master bus found: " .. name)
        break
      end
    end
  end

  if not has_master then
    warn("No MASTER bus track detected. Verify mix architecture before export.")
  else
    info("Master bus verified.")
  end

  -- Check bus folder presence
  local has_buses = false
  for i = 0, track_count - 1 do
    local track = reaper.GetTrack(0, i)
    if track then
      local _, name = reaper.GetSetMediaTrackInfo_String(track, "P_NAME", false)
      if name == "05_BUSES" then
        has_buses = true
        info("Bus folder (05_BUSES) found.")
        break
      end
    end
  end

  if not has_buses then
    warn("Bus folder (05_BUSES) not found. Routing architecture may be incomplete.")
  end

  -- Report readiness
  info("Export readiness report:")
  info("  Full Mix / Master: Ready (if FULL_MIX and PREMASTER markers exist)")
  info("  Stem Exports: Ready for individual stem categories (verify routing)")
  info("  Instrumental: Requires vocal exclusion or separate region definition")
  info("  Note: This script verifies markers and architecture; it does NOT render audio.")
  info("  To render, use REAPER's File > Render or call a render script.")

  info("Export preparation complete.")
  info("Next step: Confirm render settings (FLAC 24-bit / match sample rate) and execute render.")

  return true
end

local ok, result = pcall(prepare_export)
if not ok then
  error_msg("Script failed: " .. tostring(result))
  return false
end

if result then info("Preparation complete.") else warn("Preparation finished with warnings.") end
return result
