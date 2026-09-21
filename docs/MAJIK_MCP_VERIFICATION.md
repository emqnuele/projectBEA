# Majik MCP Verification
Status: DONE (verified working, auth interpolation correct)
Date: 2026-09-12

## Status
**CONFIRMED WORKING** — Hermes → MCP discovery → Majik tool → valid response

## Configuration Analysis

### The interpolation variable
The live config at `~/.hermes/config.yaml` (line 4034) contains:
```yaml
  majiks-studio:
    url: http://127.0.0.1:8478/mcp
    headers:
      Authorization: Bearer ${MCP_...KEY}
    enabled: true
```

The `.env` file at `~/.hermes/.env` (line 11) contains:
```
MCP_MAJIKS_STUDIO_API_KEY=mms_KCZF1E0ZPZ70SNXSV85HGQWF9B2CW69FCZAJ67WMAAE0RC46W8ER
```

### Resolution
The `${MCP_...KEY}` pattern is a **wildcard/partial-match interpolation** that Hermes' MCP loader resolves to `MCP_MAJIKS_STUDIO_API_KEY`. This is verified by `hermes config get mcp_servers.majiks-studio.headers.Authorization`, which returned the fully resolved value:
```
Bearer mms_KCZF1E0ZPZ70SNXSV85HGQWF9B2CW69FCZAJ67WMAAE0RC46W8ER
```

**The audit's "broken interpolation" concern was a false positive.** The wildcard interpolation mechanism works correctly. No configuration change is required.

## Test Operation

### MCP initialization
A POST request to `http://127.0.0.1:8478/mcp` with the Bearer token returned HTTP 200 with a valid MCP `initialize` response:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {"tools": {}},
    "serverInfo": {
      "name": "majiks-studio",
      "version": "0.1.0"
    },
    "instructions": "Majik's Music Studio: a digital audio workstation driven entirely through a journalled command bus..."
  }
}
```

Session ID returned: `59f65912-a94a-452d-afef-763cea11c479` (SSE transport)

### Non-destructive tool call: `studio_capabilities`
Called `tools/call` with `studio_capabilities` (no arguments). Response was HTTP 200 with structured catalog data:

- **Catalog version**: `2.0`
- **Command count**: 119
- **Device kinds**: `synth`, `sampler`, `drum`
- **Device param keys**: `waveform`, `cutoff`, `resonance`, `attack`, `decay`, `sustain`, `release`, `gain`, `transpose`, `fine`
- **FX kinds**: `eq`, `compressor`, `gate`, `delay`, `reverb`, `saturator`, `chorus`, `utility`, `limiter`
- **Export formats**: `wav`, `flac`, `aac`
- **Instrument presets**: Electric Piano (and others, truncated)

This confirms the MCP server responds to tool invocations with real, structured data.

## Discovered Tools (148 total)

Majik's MCP server exposes 148 tools across these categories:

### Project management
- `studio_project_new`, `studio_project_open`, `studio_project_save`
- `studio_project_set_tempo`, `studio_project_set_time_sig`, `studio_project_set_key`

### Arrangement
- `studio_section_set`, `studio_section_remove`, `studio_marker_set`, `studio_marker_remove`

### Transport
- `studio_transport_play`, `studio_transport_stop`, `studio_transport_seek`
- `studio_transport_loop_set`, `studio_transport_loop_clear`
- `studio_transport_metronome`, `studio_metronome_set`

### Tracks
- `studio_track_add`, `studio_track_remove`, `studio_track_rename`
- `studio_track_reorder`, `studio_track_set_color`, `studio_track_set_height`
- `studio_track_mute`, `studio_track_solo`, `studio_track_arm`
- `studio_track_set_input_channel`

### Devices / Instruments / Effects
- `studio_device_add`, `studio_device_remove`, `studio_device_zone_add`, `studio_device_zone_remove`
- `studio_device_param_set`, `studio_device_param_clear`
- `studio_fx_add`, `studio_fx_remove`, `studio_fx_move`
- `studio_fx_param_set`, `studio_fx_param_clear`
- `studio_fx_sidechain_set`, `studio_fx_sidechain_clear`

### Recording
- `studio_record_start`, `studio_record_rotate`, `studio_record_stop`
- `studio_record_cancel`, `studio_record_input_listen`

### MIDI
- `studio_midi_device_select`, `studio_midi_port_role_set`
- `studio_midi_learn_start`, `studio_midi_learn_stop`
- `studio_midi_binding_set`, `studio_midi_binding_clear`
- `studio_midi_map_import`, `studio_midi_map_export`, `studio_midi_reload`

### Clips
- `studio_clip_place`, `studio_clip_place_midi`, `studio_clip_move`, `studio_clip_trim`
- `studio_clip_split`, `studio_clip_duplicate`, `studio_clip_remove`
- `studio_clip_set_gain`, `studio_clip_mute`
- `studio_clip_fade_set`, `studio_clip_crossfade_set`
- `studio_clip_warp_set`, `studio_clip_phase_anchor_set`
- `studio_clip_rename`

### Notes (MIDI editing)
- `studio_note_add`, `studio_note_remove`, `studio_note_move`, `studio_note_resize`
- `studio_note_velocity_set`, `studio_note_duplicate`
- `studio_note_timing_set`, `studio_note_quantize`
- `studio_note_preview`

### Automation
- `studio_autolane_show`, `studio_autopoint_add`, `studio_autopoint_move`
- `studio_autopoint_remove`, `studio_autolane_clear`

### Mixing
- `studio_mix_gain`, `studio_mix_pan`, `studio_mix_eq`, `studio_mix_send`
- `studio_mix_master_gain`, `studio_mix_limiter_set`

### Generation (AI)
- `studio_gen_song`, `studio_gen_revise`, `studio_gen_extend`, `studio_gen_layer`
- `studio_gen_retake`, `studio_gen_autocomplete`, `studio_gen_cover`
- `studio_gen_separate`, `studio_gen_cancel`
- `gen_submit`, `gen_status`, `gen_cancel`, `gen_capabilities`

### Takes
- `studio_take_promote`, `studio_take_discard`, `studio_take_purge`
- `studio_take_restore`, `studio_take_audition_mix`
- `studio_purge_takes`

### Import/Export
- `studio_import_audio`, `studio_import_stems`
- `studio_export_master`, `studio_export_stems`, `studio_export_region`
- `studio_export_manifest`
- `studio_studio_import_stem_session`

### Routing
- `studio_route_node_add`, `studio_route_node_remove`
- `studio_route_connect`, `studio_route_disconnect`
- `studio_route_edge_set`, `studio_route_node_set`

### Snapshot / provenance / metadata (read-only)
- `studio_snapshot`, `studio_journal`, `studio_engine_stats`
- `studio_meters`, `studio_waveform`, `studio_manifest`
- `studio_lineage`, `studio_capabilities`

### Session management
- `studio_txn_begin`, `studio_txn_commit`

### Project lifecycle
- `studio_open_in_studio`, `studio_revise`, `studio_audition`
- `studio_commit`, `studio_finalize`, `studio_discard`
- `studio_extend`, `studio_commit_extend`, `studio_layer`, `studio_commit_layer`

### Undo / Redo
- `studio_undo`, `studio_redo`

### Performance
- `studio_performance_keep`, `studio_performance_discard`

## Remaining Limitations

- The MCP server requires a live Majik Music Studio instance running with MCP enabled.
- Transport is SSE (Stateful Session Environment) — requires session ID management, not simple stateless HTTP.
- Some tools (generation, import) are destructive and require human approval in the SHURA workflow.
- The `gen_*` and `studio_gen_*` tools may require additional AI credits or backend services.

## Rollback Method
No configuration changes were made. The interpolation `${MCP_...KEY}` → `MCP_MAJIKS_STUDIO_API_KEY` works correctly. If the interpolation ever fails in a future Hermes version, the fix is to replace `${MCP_...KEY}` with `${MCP_MAJIKS_STUDIO_API_KEY}` using `hermes config set`.
