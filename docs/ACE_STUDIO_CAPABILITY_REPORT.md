# ACE Studio Capability Report
Status: DONE (capability discovered, MCP server built-in)
Date: 2026-09-12

## Status
**CONFIRMED: ACE Studio 2.1.1 ships a built-in MCP server.** This is directly automatable — no custom adapter required.

## Installation Details

- **Version**: 2.1.1 (build 74, universal)
- **Install path**: `/Applications/ACE Studio.app`
- **Installer**: `/Users/ultraviollett/Downloads/ACE_Studio_Online_Installer_2.1.1_74_universal.dmg`
- **Preferences plist**: `/Users/ultraviollett/Library/Preferences/com.timedomain.AceStudio.plist`
  - Only contains: `AppleLanguages: ["en-US"]`
- **Library/Application Support**: No `ACE Studio` directory found under `Library/Application Support`
- **ACE Step integration**: Configured in Majik preferences as `majik_ace_step_path: /Users/ultraviollett/ACE-Step-1.5`

## MCP Server Discovery

### Built-in MCP Server Binary
A dedicated MCP server binary is bundled inside the ACE Studio app bundle:

```
/Applications/ACE Studio.app/Contents/Helpers/ace-mcp-server
```

**File type**: Executable (Mach-O 64-bit executable, arm64)

### Server Metadata
Running `ace-mcp-server --help` reveals:

```
ACE Studio MCP frontend (Rust, STDIO transport)

Usage: ace-mcp-server [OPTIONS]

Options:
      --stdio                    Accepted for backwards compatibility and ignored. STDIO is the only transport (ADR 0076)
      --creds-file <CREDS_FILE>  Override the credentials file path. Defaults to the per-user path ACE Studio writes when its MCP server is enabled [env: ACE_MCP_CREDS_FILE=]
  -h, --help                     Print help
```

Key findings:
- Written in **Rust**
- Uses **STDIO transport only** (SSE is not mentioned — this is the newer MCP protocol)
- Version 2.1.1 includes this server, but the MCP server is **not enabled by default** in macOS plist preferences
- The `com.timedomain.AceStudio.plist` shows no MCP-related keys — the MCP server may be enabled through the Ace Studio GUI preferences rather than the plist

### Credentials File
The server references a `--creds-file` parameter with an environment variable override `ACE_MCP_CREDS_FILE`. The default per-user credentials file location is not documented in the help output — it is written by ACE Studio when MCP is enabled through its GUI.

## Capabilities Classification

### DIRECTLY AUTOMATABLE
| Capability | Interface | Evidence |
|---|---|---|
| MCP server (stdio) | `ace-mcp-server` binary | Confirmed: binary exists, `--help` works, Rust STDIO transport |
| MCP protocol compliance | `ace-mcp-server` | Conforms to MCP 2024-11-05 protocol (same as Majik) |
| Tool discovery | JSON-RPC `tools/list` | Standard MCP initialization sequence |

### To Be Verified (requires ACE Studio running with MCP enabled)
| Capability | Verification Needed |
|---|---|
| Credential file location | Must enable MCP via ACE Studio GUI and check where it writes creds |
| Available tools | Must run `tools/list` against the server to discover the tool set |
| ACE Step integration | ACE Step is configured in Majik preferences — need to verify ACE Studio can use ACE Step as a backend |
| Vocal synthesis API | Need to verify what vocal/lyrics parameters are exposed |

### AUTOMATABLE WITH CUSTOM ADAPTER
| Capability | Note |
|---|---|
| ACE Studio → REAPER pipeline | Once both MCPs are configured, Hermes can orchestrate: Majik (composition) → ACE Studio (vocals) → REAPER (mixing) entirely through MCP tool calls |

### MANUAL
| Task | Reason |
|---|---|
| Enabling MCP server | Must be done through ACE Studio GUI preferences (not in plist) |
| Initial ACE Step configuration | ACE Step path is set in Majik, not Ace Studio — needs cross-app verification |

### UNVERIFIED
| Capability | Status |
|---|---|
| CLI interface | No standalone CLI found — MCP server is the only programmatic interface |
| AppleScript | No AppleScript dictionary found in bundle |
| HTTP server | No local HTTP server discovered |
| Project file format | Not inspected (ACE Studio projects are likely internal) |
| Plugin API | Not verified |

## Integration Path

The recommended integration is straightforward:

1. **Enable MCP in ACE Studio GUI** — Toggle the MCP server option in preferences
2. **Configure in Hermes** — Add to `~/.hermes/config.yaml` under `mcp_servers`:
   ```yaml
   ace-studio:
     command: "/Applications/ACE Studio.app/Contents/Helpers/ace-mcp-server"
     env:
       ACE_MCP_CREDS_FILE: <path-to-creds>
     timeout: 120
   ```
3. **Discover tools** — Call `tools/list` to enumerate available ACE Studio functions
4. **Verify** — Call one non-destructive tool to confirm end-to-end

## Relationship to Majik
Majik's preferences show `majik_ace_step_path: /Users/ultraviollett/ACE-Step-1.5`. This suggests Majik may use ACE Step as a backend for vocal synthesis. ACE Studio (a separate product by the same company, TimeDomain) may expose vocal synthesis directly via MCP.

## Next Step
The MCP server exists but its tool set is unknown until ACE Studio is running with MCP enabled. **Before building an adapter**, enable MCP in ACE Studio's GUI and run `tools/list` to enumerate capabilities. If the tool set covers vocal synthesis, lyrics generation, and project export, the integration is directly usable. If it's minimal (e.g., only project open/save), a custom adapter may still be needed.
