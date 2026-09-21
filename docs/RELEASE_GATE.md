# Release Gate
Status: DONE (procedure defined)
Date: 2026-09-12

## Definition
The release gate is a defensive security review process applied before any external release, public publication, or durable architectural change.

## Procedure (Mandatory for All Releases)

### 1. Worktree Inspection
```bash
git -C /Users/ultraviollette/projectSHURA status --short
git -C /Users/ultraviollette/projectSHURA diff --stat
```
Verify only intended files changed.

### 2. Diff Review
```bash
git diff
```
Every change must be reviewable and explainable. Do not commit bulk auto-generated files.

### 3. Defensive Security Review
Check for:
- [ ] **Secrets** — No API keys, tokens, or credentials in source/code/docs
- [ ] **Config exposure** — No `.env` contents, `config.yaml` secrets, or auth tokens
- [ ] **Path traversal** — No hardcoded absolute paths that break on other machines
- [ ] **Dependency injection** — `pyproject.toml` / `uv.lock` only include verified packages
- [ ] **Identity drift** — SOUL.md content consistent with runtime (`IDENTITY_SYNC.md`)
- [ ] **No provider lock-in** — Config does not hardcode one provider/model
- [ ] **Rollback documented** — Every config change has a backup procedure

### 4. Testing
Run at minimum:
```bash
hermes --version
hermes config get model.default
# Verify MCP discovery (Majik):
# (verified via execute_code: initialize → list tools → call studio_capabilities)
```

### 5. Summary Report
Create/update `docs/RELEASE_REPORT.md`:
```markdown
# Release Report — <version>
- Changes: (list files)
- Security review: passed/failed (with notes)
- Identity consistency: verified
- Rollback method: documented
- Approval: Viollett (date)
```

### 6. Approval Gate
No release proceeds without explicit human (Viollett) approval.

## What This Gate Protects
- Identity integrity: NO hidden identity rewrites in commits
- Security: NO secrets in public repos or docs
- Reversibility: Every change must have rollback guidance
- Architecture: Every change must be explainable in context

## What This Does NOT Block
- Internal documentation updates (this audit)
- Configuration backups (already in `~/.hermes/`)
- Non-destructive verification tasks (MCP tool testing)
- Skill activation checks
- Migration of canonical repo content (when approved)
