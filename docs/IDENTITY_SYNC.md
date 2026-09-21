# Identity Sync Protocol
Status: DONE (files identical, sync procedure defined)
Date: 2026-09-12

## Verification

### Files Compared
- **Runtime authority**: `/Users/ultraviollett/.hermes/SOUL.md` (8,872 bytes, 225 lines)
- **Repository mirror**: `/Users/ultraviollett/projectSHURA/docs/shura/SOUL.md` (8,872 bytes, 225 lines)

### Result: IDENTICAL

```bash
$ md5 ~/.hermes/SOUL.md
6aabb046958ddedaf0bd62b14ad6fe18

$ md5 projectSHURA/docs/shura/SOUL.md
6aabb046958ddedaf0bd62b14ad6fe18

$ diff ~/.hermes/SOUL.md projectSHURA/docs/shura/SOUL.md
(empty — no differences)
```

The files are byte-for-byte identical (MD5: `6aabb046958ddedaf0bd62b14ad6fe18`).

## Authority Designation

| Role | File | Location | Reason |
|---|---|---|---|
| **Runtime authority** | `~/.hermes/SOUL.md` | Hermes config directory | This is the file Hermes loads at startup; changes here take effect on next session reset |
| **Repository mirror** | `projectSHURA/docs/shura/SOUL.md` | ProjectSHURA repo | Version-controlled copy; track changes via git; serves as the canonical source for rebuilding the runtime |
| **Skill layer** | `~/.hermes/skills/shura/SKILL.md` | Hermes skills directory | Defines routing behavior (not identity content) |
| **Operating layer** | `projectSHURA/docs/shura/OPERATING.md` | ProjectSHURA repo | Behavior interpreter (how identity translates to action) |
| **Manifest** | `projectSHURA/docs/shura/IDENTITY_MANIFEST.md` | ProjectSHURA repo | Layer stack definition |

## Synchronization Procedure

### Runtime → Repository (when SOUL.md is edited at runtime)

There is no automatic sync. The runtime file must be manually mirrored:

```bash
cp ~/.hermes/SOUL.md projectSHURA/docs/shura/SOUL.md
cd projectSHURA
git add docs/shura/SOUL.md
git commit -m "chore(identity): sync SOUL.md from runtime"
```

### Repository → Runtime (when SOUL.md is edited in the repo)

```bash
cp projectSHURA/docs/shura/SOUL.md ~/.hermes/SOUL.md
```
Then restart Hermes or run `/reset` to reload identity.

### Automated Sync (recommended future state)

Create a script `scripts/sync_soul.sh`:
```bash
#!/bin/bash
# Syncs SOUL.md between runtime and repository
# Run when either copy changes

RUNTIME=~/.hermes/SOUL.md
REPO=~/projectSHURA/docs/shura/SOUL.md

if diff -q "$RUNTIME" "$REPO" > /dev/null 2>&1; then
    echo "✓ SOUL.md is in sync"
else
    cp "$RUNTIME" "$REPO"
    echo "↻ Runtime → Repository sync applied"
    # Optional: git commit
    # cd ~/projectSHURA
    # git add docs/shura/SOUL.md
    # git commit -m "chore(identity): sync SOUL.md from runtime"
fi
```

Add to cron (Phase 5.2 continuity audit):
```bash
# Every 6 hours, check SOUL.md sync
0 */6 * * * /Users/ultraviollett/projectSHURA/scripts/sync_soul.sh
```

## Superseded Identity Files

### Shura/ directory (retirement candidate)
- Path: `/Users/ultraviollett/Shura/` (not a git repository)
- Contents: `OPERATING_MANUAL.md`, `PROJECTS.md`
- Status: Superseded by `projectSHURA/docs/shura/OPERATING.md` and `projectSHURA/docs/shura/IDENTITY_MANIFEST.md`
- Content overlap: Conceptual (operating manual principles) and navigational (project registry), not identity content
- Recommendation: Archive with a `SUPERSEDED` note pointing to `projectSHURA/docs/shura/`

### SOUL.md.shura-preflight backup
- Path: `/Users/ultraviollett/.hermes/SOUL.md.shura-preflight-2026-08-14`
- Status: Pre-flight backup from identity draft phase
- Recommendation: Retain as historical artifact; not part of active sync

## Divergence Protocol

If `diff` shows differences between the two SOUL.md files:

1. **Do NOT automatically choose a winner**
2. **Classify as HUMAN DECISION REQUIRED**
3. Document the diff:
   ```bash
   diff ~/.hermes/SOUL.md projectSHURA/docs/shura/SOUL.md > docs/identity_divergence_$(date +%Y%m%d).diff
   ```
4. Present the diff to Viollett with recommendation for which version is canonical
5. After human decision, sync the chosen version to both locations
