#!/usr/bin/env python3
"""
reaper_mcp_client.py — ProjectSHURA / AETHERWOUND
Python bridge to the existing REAPER MCP server (file-based IPC).

Protocol: writes command.json to TMPDIR/reaper_mcp/, reads response.json.
Matches the existing reaper_mcp_server.lua (line 5310 handler table).

Usage (from SHURA / Hermes):
    from reaper_mcp_client import send_command
    result = send_command("transport_play", {"play_state": 1})

References:
- docs/MCP.md (existing server evaluation, strategy A sketch)
- ~/Library/Application Support/REAPER/Scripts/reaper_mcp_server.lua
"""

import os
import json
import time
import tempfile
from pathlib import Path

# The existing server uses TMPDIR/reaper_mcp/; match exactly.
_tmpdir = os.getenv("TMPDIR", tempfile.gettempdir())
if _tmpdir.endswith("/"):
    _tmpdir = _tmpdir[:-1]

IPC_DIR = Path(_tmpdir) / "reaper_mcp"
COMMAND_FILE = IPC_DIR / "command.json"
RESPONSE_FILE = IPC_DIR / "response.json"
LOCK_FILE = IPC_DIR / "server.lock"

HEARTBEAT_INTERVAL = 10  # matches server


def ensure_ipc_dir():
    """Ensure the IPC directory exists (same defensive approach as server)."""
    IPC_DIR.mkdir(parents=True, exist_ok=True)


def is_server_alive() -> bool:
    """Check server heartbeat (lock file updated within interval)."""
    try:
        if not LOCK_FILE.exists():
            return False
        stat = LOCK_FILE.stat()
        return (time.time() - stat.st_mtime) < (HEARTBEAT_INTERVAL * 2)
    except Exception:
        return False


def send_command(command: str, params: dict | None = None, timeout: float = 5.0) -> dict:
    """Send a command to the existing REAPER MCP server via file-based IPC."""
    ensure_ipc_dir()

    req_id = f"req-{time.time():.3f}-{os.getpid()}"
    cmd = {
        "command": command,
        "params": params or {},
        "id": req_id,
    }

    # Write atomically (write to temp then rename, or direct — server reads continuously)
    # For simplicity and matching server behavior (polling loop), direct write is sufficient.
    with open(COMMAND_FILE, "w", encoding="utf-8") as f:
        json.dump(cmd, f)
        f.flush()

    # Poll for response with correlation check (id echo)
    start = time.time()
    while time.time() - start < timeout:
        if RESPONSE_FILE.exists():
            try:
                with open(RESPONSE_FILE, "r", encoding="utf-8") as f:
                    resp_text = f.read()
                if resp_text.strip():
                    resp = json.loads(resp_text)
                    if resp.get("id") == req_id:
                        return resp
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(0.05)

    return {
        "success": False,
        "error": "Timeout waiting for REAPER response",
        "id": req_id,
        "note": "Verify REAPER is running and reaper_mcp_server.lua is loaded.",
    }


# Common high-value semantic operations (map SHURA concepts to existing server commands)
SEMANTIC_COMMANDS = {
    "inspect_project": lambda: send_command("project_get_info"),
    "transport_play": lambda: send_command("transport_play", {"play_state": 1}),
    "transport_stop": lambda: send_command("transport_stop"),
    "track_list": lambda: send_command("track_get_all"),
    "marker_list": lambda: send_command("marker_get_all"),
    "create_project_snapshot_reference": lambda: send_command("project_save", {}),
}

if __name__ == "__main__":
    # Quick health check
    alive = is_server_alive()
    print(f"REAPER MCP server alive: {alive}")
    print(f"IPC dir: {IPC_DIR}")
    if alive:
        # Safe read-only test
        result = send_command("transport_play", {"play_state": 0}, timeout=2.0)
        print(f"Safe test result: {result.get('success')}")
    else:
        print("Server not detected. Verify REAPER is running and script is loaded.")
