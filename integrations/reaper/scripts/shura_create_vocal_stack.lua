-- shura_create_vocal_stack.lua
-- AETHERWOUND / ProjectSHURA — REAPER Workflow Script
-- Phase: 2 (Workflow) | Status: ACTIVE / Prototype
-- Author: SHURA

-- PURPOSE:
-- Creates the standard vocal stack structure inside an AETHERWOUND project.
-- Creates folders and empty tracks for LEAD, DOUBLES, HARMONIES, ADLIBS, and VOCAL FX.
-- Non-destructive operation.

local script_name = "shura_create_vocal_stack"
local script_version = "1.0"

local function info(msg) reaper.ShowConsoleMsg("[" .. script_name .. " v" .. script_version .. "] " .. tostring(msg) .. "\n") end
local function warn(msg) reaper.ShowConsoleMsg("[" .. script_name .. " WARNING] " .. tostring(msg) .. "\n") end
local function error_msg(msg) reaper.ShowConsoleMsg("[" .. script_name .. " ERROR] " .. tostring(msg) .. "\n") end

local function create_vocal_stack()
  reaper.Undo_BeginBlock()
  info("Starting vocal stack creation...")

  local track_count = reaper.CountTracks(0)
  info("Current track count: " .. track_count)

  -- LEAD folder + track
  local lead_folder = reaper.InsertTrackAtIndex(track_count, true)
  if lead_folder then
    reaper.GetSetMediaTrackInfo_String(lead_folder, "P_NAME", "03_VOCALS / LEAD", true)
  else warn("Failed to create LEAD folder.") end

  local lead_track = reaper.InsertTrackAtIndex(track_count + 1, false)
  if lead_track then reaper.GetSetMediaTrackInfo_String(lead_track, "P_NAME", "VOC_LEAD_Main", true) else warn("Failed to create lead vocal track.") end

  -- DOUBLES folder + L/R tracks
  local doubles_folder = reaper.InsertTrackAtIndex(track_count + 2, true)
  if doubles_folder then reaper.GetSetMediaTrackInfo_String(doubles_folder, "P_NAME", "03_VOCALS / DOUBLES", true) end

  local double_l = reaper.InsertTrackAtIndex(track_count + 3, false)
  if double_l then reaper.GetSetMediaTrackInfo_String(double_l, "P_NAME", "VOC_DBL_L", true) else warn("Failed to create double L.") end

  local double_r = reaper.InsertTrackAtIndex(track_count + 4, false)
  if double_r then reaper.GetSetMediaTrackInfo_String(double_r, "P_NAME", "VOC_DBL_R", true) else warn("Failed to create double R.") end

  -- HARMONIES folder + Upper/Lower
  local harmony_folder = reaper.InsertTrackAtIndex(track_count + 5, true)
  if harmony_folder then reaper.GetSetMediaTrackInfo_String(harmony_folder, "P_NAME", "03_VOCALS / HARMONIES", true) end

  local harmony_upper = reaper.InsertTrackAtIndex(track_count + 6, false)
  if harmony_upper then reaper.GetSetMediaTrackInfo_String(harmony_upper, "P_NAME", "VOC_HRM_Upper", true) else warn("Failed to create harmony upper.") end

  local harmony_lower = reaper.InsertTrackAtIndex(track_count + 7, false)
  if harmony_lower then reaper.GetSetMediaTrackInfo_String(harmony_lower, "P_NAME", "VOC_HRM_Lower", true) else warn("Failed to create harmony lower.") end

  -- ADLIBS folder + track
  local adlib_folder = reaper.InsertTrackAtIndex(track_count + 8, true)
  if adlib_folder then reaper.GetSetMediaTrackInfo_String(adlib_folder, "P_NAME", "03_VOCALS / ADLIBS", true) end

  local adlib_track = reaper.InsertTrackAtIndex(track_count + 9, false)
  if adlib_track then reaper.GetSetMediaTrackInfo_String(adlib_track, "P_NAME", "VOC_ADL_Spoken", true) else warn("Failed to create adlib.") end

  -- VOCAL FX folder + ReverbSend + Delay
  local vocalfx_folder = reaper.InsertTrackAtIndex(track_count + 10, true)
  if vocalfx_folder then reaper.GetSetMediaTrackInfo_String(vocalfx_folder, "P_NAME", "03_VOCALS / VOCAL FX", true) end

  local reverb_send = reaper.InsertTrackAtIndex(track_count + 11, false)
  if reverb_send then reaper.GetSetMediaTrackInfo_String(reverb_send, "P_NAME", "VOC_FX_ReverbSend", true) else warn("Failed to create vocal FX reverb send.") end

  local delay_track = reaper.InsertTrackAtIndex(track_count + 12, false)
  if delay_track then reaper.GetSetMediaTrackInfo_String(delay_track, "P_NAME", "VOC_FX_Delay", true) else warn("Failed to create vocal FX delay.") end

  info("Vocal stack created: LEAD, DOUBLES (L/R), HARMONIES (Upper/Lower), ADLIBS, VOCAL FX (Reverb/Delay).")
  info("These are empty tracks. Add media items or routing as needed.")

  reaper.Undo_EndBlock(script_name .. ": created vocal stack", -1)
  return true
end

local ok, result = pcall(create_vocal_stack)
if not ok then
  error_msg("Script failed with exception: " .. tostring(result))
  reaper.Undo_EndBlock(script_name .. ": exception", -1)
  return false
end

if result then info("Vocal stack creation complete.") else warn("Partial completion.") end
return result
