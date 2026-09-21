# Phase 2 Preparation Note — ACE Studio MCP
Status: READY (not yet executed — requires GUI enablement)
Date: 2026-09-12

## Evidence Confirmed
- **Binary**: `/Applications/ACE Studio.app/Contents/Helpers/ace-mcp-server`
- **Executable**: Mode `0o100755` (full execution permissions)
- **Transport**: STDIO (confirmed via `--help` output)
- **Server name**: Not yet verified (requires initialization call against running instance)
- **Tool set**: Not yet verified (requires `tools/list` from running server with valid session)

## What Must Happen Before Integration
1. **Enable MCP in ACE Studio GUI** — Toggle the MCP server option in ACE Studio's preferences (the `.plist` does not expose this setting; it's GUI-controlled)
2. **Determine credentials file path** — Once enabled, ACE Studio writes a per-user credentials file; the `ACE_MCP_CREDS_FILE` env variable points to it
3. **Configure in Hermes** — Add `ace-studio` entry under `mcp_servers` in `~/.hermes/config.yaml`
4. **Restart Hermes** — MCP discovery runs at startup; hot-reload is not supported
5. **Verify** — Call `mcp_ace_studio_*` tools in a session and verify responses

## Configuration Template (NOT YET APPLIED)
See `docs/ACE_STUDIO_CAPABILITY_REPORT.md` for full details.

## Blocker
The ACE Studio app is installed but not running in this session. The MCP server binary requires the ACE Studio parent process (or its authorization mechanism) to provide valid credentials. Without running the ACE Studio GUI and enabling MCP, no valid session can be established.

## Decision
This step is **safe to execute** (non-destructive — adds an MCP entry to config, starts a server process). It requires no identity changes, no architecture rewrites, and no ATLAS content modification. It is the logical next step once the canonical repo decisions (0.6, 0.7) have been executed.
