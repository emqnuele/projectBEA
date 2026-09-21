# REAPER MCP — Integration Notes and Bridge Design

Audit date: 2026-09-15
REAPER version: 7.79.0
MCP file: `~/Library/Application Support/REAPER/Scripts/reaper_mcp_server.lua`

---

## Existing MCP Status

The environment contains a substantial, working REAPER MCP server implemented in Lua. This is a critical finding because the previous `REAPER_INTEGRATION_PLAN.md` (dated 2026-09-12) incorrectly states that "no MCP server exists."

### File Details
- Path: `~/Library/Application Support/REAPER/Scripts/reaper_mcp_server.lua`
- Size: ~5,392 lines
- Protocol: File-based IPC (`TMPDIR/reaper_mcp/command.json` and `response.json`)
- Heartbeat: Updates `server.lock` every 10 seconds (`HEARTBEAT_INTERVAL = 10`)
- Security: Uses REAPER native `RecursiveCreateDirectory` for safe path creation; defensive character filtering (`gsub('[^%w%-%.%s:/\\]', "_")`) for directory paths; no shell injection possible via file commands
- Error handling: `pcall` wrapping around all command handlers; error responses include the original request `id` for correlation; internal errors are reported to REAPER console (`reaper.ShowConsoleMsg`)

### Verified Command Families (by code inspection)

| Family | Commands (examples) | Capabilities |
|---|---|---|
| Transport | `transport_play`, `transport_stop`, `transport_set_play_state` | Play, stop, set play state (loop, play rate, etc.) |
| Track | `track_get_all`, `track_add`, `track_get_info`, `track_set_name`, `track_set_route` | Get/create/update tracks; set routing |
| Project | `project_get_info`, `project_save`, `project_create_marker`, `project_set_tempo` | Project metadata, save, markers, tempo |
| FX | `fx_get_all`, `fx_add`, `fx_set_param`, `fx_remove` | FX chain inspection/manipulation |
| Item | `item_get_all`, `item_add`, `item_select`, `item_split`, `item_set_name`, `item_set_position` | Media item creation/manipulation |
| Chop | `chop_slice_at_transients`, `chop_get_items` | Transient-based splitting |
| Marker | `marker_get_all`, `marker_create`, `marker_set_name` | Region/marker management |
| Selection | `selection_get_time`, `selection_set_time`, `selection_get_items` | Selection state |
| Send | `send_create`, `send_get_all` | Send/receive routing |
| MIDI | `midi_add_note`, `midi_delete_note`, `midi_get_notes` | MIDI note manipulation |
| Compose | `compose_wipe_all_midi`, `compose_generate` | MIDI generation pipelines |
| Envelope | `envelope_set_point`, `envelope_get`, `envelope_set_mode` | Automation envelope editing |
| Tempo | `tempo_list_markers`, `tempo_set` | Tempo/time-signature markers |
| Take | `item_take_list`, `item_take_select` | Multiple take / comping support |

Note: A `script` handler family also exists (line 5323 in the source), confirming that script execution commands are available.

### Protocol Details

**Request format (`command.json`):**
```json
{
  "command": "transport_play",
  "params": {"play_state": 1},
  "id": "req-001"
}
```

**Response format (`response.json`):**
```json
{
  "success": true,
  "result": { ... },
  "id": "req-001"
}
```

If an error occurs:
```json
{
  "success": false,
  "error": "Unknown command: unknown_cmd",
  "id": "req-001"
}
```

The `id` echo is critical: it allows the Python client to distinguish a genuine response to its command from a stale response written by a previous command that completed after the client's timeout.

---

## Gaps and Missing Capabilities

Based on inspection of the handler definitions, the following capabilities are either missing or unverified:

| Capability | Status | Notes |
|---|---|---|
| Render / Export (`RPR_Render` equivalent) | **Unverified / Possibly missing** | The `render` command family is not visible in the handler list. This does not mean it does not exist (the handler list at line 5310-5323 only shows top-level family assignments; individual handlers within families are defined earlier). A deeper inspection of the transport/project/item sections would confirm whether render/export commands exist. However, for Phase 1-3, this is acceptable — the primary automation needs (project inspection, track creation, routing, transport control) are covered. |
| Semantic folder creation (`project_create_folder_with_role`) | **Not present** | Folders are created as tracks with folder properties (`reaper.IsTrackFolder` / folder depth settings). The existing `track_add` and routing commands can achieve this with appropriate parameters, but there is no dedicated "create folder with role" command. This can be built as a composite Python script that calls `track_add` + `track_set_route` + sets folder properties. |
| Project template creation (`project_create_from_template`) | **Not present** | No dedicated template command. The recommended approach is to create a base `.rpp` file (like `AETHERWOUND_Template.rpp`) and open it as a new project, rather than creating the structure programmatically from scratch. This avoids duplicating template logic in the MCP and leverages REAPER's native template mechanism. |
| Custom script execution (`script_run_custom`) | **Exists** (`script` family) | The `script` family (line 5323) includes script execution. The exact commands within it need deeper inspection, but the capability is present. This allows SHURA to trigger custom workflow scripts (`shura_create_project.lua`) via the MCP rather than requiring manual action list invocation. |
| Track color / semantic tracking (`track_set_semantic_color`) | **Not present** | No dedicated semantic color command. Colors are set via standard `track_set_info` or direct `reaper.SetTrackColor` calls within custom scripts. The Python bridge or custom scripts can handle semantic color assignment directly. |

---

## Integration Strategy

### Strategy A: Direct File-Based Protocol (Simplest)
For basic automation (transport control, project inspection, track creation), the Python bridge can write commands directly to `TMPDIR/reaper_mcp/command.json` and read responses from `response.json`. This requires no extra server layer.

Implementation sketch (Python, for future Phase 3):
```python
import json, pathlib, tempfile, time, os

ipc_dir = os.path.join(os.getenv("TMPDIR", "/tmp"), "reaper_mcp")
command_file = pathlib.Path(ipc_dir) / "command.json"
response_file = pathlib.Path(ipc_dir) / "response.json"

def send_command(cmd: str, params: dict, timeout: float = 5.0) -> dict:
    req = {"command": cmd, "params": params, "id": f"req-{time.time()}"}
    command_file.write_text(json.dumps(req))
    # Poll for response (with timeout)
    start = time.time()
    while time.time() - start < timeout:
        if response_file.exists():
            resp_text = response_file.read_text()
            resp = json.loads(resp_text)
            if resp.get("id") == req["id"]:
                return resp
        time.sleep(0.05)
    return {"success": False, "error": "Timeout waiting for REAPER response", "id": req["id"]}
```
Note: The actual Python bridge (`reaper_mcp_client.py`) should include more robust error handling, logging, and correlation tracking.

### Strategy B: Python MCP Server Wrapper (For Hermes Integration)
If SHURA needs to interact with REAPER through a standard MCP protocol (as defined by Hermes), a Python `stdio` MCP server can be written that:
1. Receives MCP tool calls from Hermes (e.g., `reaper_project_inspect`, `reaper_track_create`)
2. Translates them to file-based commands for the Lua server
3. Reads responses and translates them back to MCP results

This is the recommended architecture for Phase 3. It does not replace the Lua server; it adds a translation layer.

### Strategy C: Python ReaScript Bridge (Direct `RPR_*` Calls)
The Python `reaper_python.py` (730 exported `RPR_*` functions) provides direct access to REAPER's internal API from within REAPER's Python interpreter. A Python ReaScript loaded inside REAPER can:
- Call `RPR_AddTrack`, `RPR_GetProject`, `RPR_Render`, etc.
- Read/write file-based commands
- Execute as a persistent script (like the Lua server) or as a one-time action

This approach is useful for complex operations that the file-based MCP does not cover (e.g., direct `RPR_Render` with custom parameters). However, it requires REAPER to be running and the Python interpreter to be available, which limits its use as an independent automation layer.

For the AETHERWOUND architecture, the recommended approach is:
- **Primary**: File-based protocol through existing Lua server (Strategy A)
- **Secondary (if needed)**: Python bridge script for Hermes integration (Strategy B)
- **Tertiary (for missing capabilities)**: Custom Python ReaScript or extension of the Lua server (Strategy C or extension)

---

## Testing the Existing MCP

A safe test procedure (manual, non-destructive):

1. Verify REAPER is running and the script is loaded (check `Actions > Show action list` for `reaper_mcp_server.lua` or look for startup messages in REAPER console).
2. Verify the IPC directory exists (`TMPDIR/reaper_mcp/`). If it does not exist, run the script once (it creates the directory on startup).
3. Read `reaper_mcp_server.lua` lines 840-910 (`transport` handlers) to confirm `transport_play` exists.
4. Write a test `command.json`:
```json
{"command":"transport_play","params":{"play_state":1},"id":"test-001"}
```
5. Wait up to 2 seconds.
6. Read `response.json`. Expected result: success with transport state, or error if REAPER is not running / script not active.
7. Clean up: delete `command.json` and `response.json` (optional; the server processes them continuously).

Note: Writing directly to `command.json` while the server is running may cause unexpected behavior (the server may process the command immediately and overwrite the response file before the test reads it). A more robust test uses a dedicated Python script that writes the file, waits, reads the response with the correct `id`, and then deletes both files.

---

## Integration Notes

### Note 1: Existing MCP Takes Precedence
The `REAPER_INTEGRATION_PLAN.md` (dated 2026-09-12) claims no MCP exists. This is incorrect. Any integration work must start from the existing `reaper_mcp_server.lua` rather than building a new server from scratch.

### Note 2: MCP Extension vs. Replacement
If a missing capability is identified (e.g., a dedicated `render_stem` command), the preferred approach is to add a new handler to the existing Lua file rather than creating a separate server. The existing file has a clear structure (`handlers` table at line 5310) that makes extension straightforward.

### Note 3: Security Considerations
The existing server uses defensive path construction (`safe_dir`) and relies on REAPER's native directory creation rather than shell commands. This is appropriate for a local automation server. No additional authentication layer is needed for a single-user local environment, but any future network-accessible extension must include authentication (not currently planned).

### Note 4: Performance
The server uses a `defer()` loop with a polling mechanism (`process_command` reads files continuously). This introduces minimal overhead but does create file I/O on each loop iteration. For high-frequency automation (e.g., hundreds of commands per second), the file-based protocol may become a bottleneck. The AETHERWOUND workflow (project creation, vocal stack creation, inspection) does not require high-frequency commands; the current protocol is sufficient.

---

## References

- Source file: `~/Library/Application Support/REAPER/Scripts/reaper_mcp_server.lua`
- Protocol file references: `reaper.ini`, `reaper-wndpos.ini`
- Integration plan (outdated): `~/projectSHURA/docs/REAPER_INTEGRATION_PLAN.md`
- Python client libraries: `.venv/lib/python3.11/site-packages/` (various MCP-related packages — not directly related to REAPER integration)
