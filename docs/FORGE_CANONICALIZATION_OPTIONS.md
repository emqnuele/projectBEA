# FORGE Canonicalization Options
Status: DONE (recommendation provided, human approval required)
Date: 2026-09-12

## Current State of Candidate Repositories

### ~/FORGE.project/
- **Status**: Git repository (initialized, no commits on `master` branch)
- **Files**: `README.md` (8 bytes: `# FORGE`), `AGENTS.md` (0 bytes)
- **Content**: Empty scaffold — no substantive content
- **Git**: `fatal: your current branch 'master' does not have any commits yet`
- **Conclusion**: Uninitialized scaffold with placeholder content

### ~/Projects/shura-forge/
- **Status**: Git repository (1 commit: "Initial Forge structure")
- **Structure**: Contains `SHURA-ATLAS/` subdirectory with FSI, capability ledger, Vol.I/Vol.II, references, scripts, and assets
- **Content**:
  - `SHURA-ATLAS/FSI.md` — Forge Status Indicator (heartbeat)
  - `SHURA-ATLAS/FORGE-CAPABILITIES.md` — Capability ledger with backlog and wishlist
  - `SHURA-ATLAS/CONTRIBUTING.md` — Contribution guidelines
  - `SHURA-ATLAS/Vol.I/` — Constitution, philosophy, principle markers, first milestone
  - `SHURA-ATLAS/Vol.II/Sys.*` — System map (10 subsystems)
  - `SHURA-ATLAS/references/` — Knowledge artifacts (chatlog summaries, knowledge triplet schema)
  - `SHURA-ATLAS/scripts/` — `audit-fsi.sh`, `bootstrap.sh`
  - `SHURA-ATLAS/assets/` — `day-6-aesthetic.json`
- **Conclusion**: The active Forge content lives in `shura-forge/SHURA-ATLAS/`, not in `FORGE.project/`

### ~/shura-forge/shura-forgev1/ (duplicate)
- **Status**: Separate copy of `SHURA-ATLAS/` content at `shura-forge/shura-forgev1/`
- **Content**: Identical structure to `SHURA-ATLAS/` (FSI, capabilities, Vol.I/Vol.II, etc.)
- **Conclusion**: **Redundant duplicate** — likely a backup or earlier iteration

### ~/projectSHURA/
- **Forge-related files**:
  - `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` — defines FORGE as the "synthesis, conflict-resolution, auditing, evaluation, and canonization layer"
  - No dedicated FORGE content directory

## Analysis

### Key Finding: shura-forge vs FORGE.project

The name "shura-forge" suggests this was intended as the Forge implementation. However:

- `FORGE.project/` is an empty scaffold (no commits)
- `shura-forge/SHURA-ATLAS/` contains the actual Forge content (FSI, capability ledger, constitution, system map)
- The content in `shura-forge/SHURA-ATLAS/` is conceptually split: some documents belong to ATLAS (Vol.II system map, references) and some belong to FORGE (FSI, capability ledger, constitution, scripts)

This suggests the `shura-forge` repository was a combined workspace that was later split into separate `ATLAS.project` and `FORGE.project` repositories, but the migration was never completed.

### Redundancy: shura-forge/SHURA-ATLAS/ vs shura-forge/shura-forgev1/

Two copies of the same content exist at:
- `/Projects/shura-forge/SHURA-ATLAS/`
- `/Projects/shura-forge/shura-forgev1/`

These should be reconciled regardless of which canonical structure is chosen.

## Options

### Option A: FORGE.project becomes canonical FORGE repository
Populate `FORGE.project` with the Forge-specific content from `shura-forge`:

```
FORGE.project/
├── README.md              (actual content)
├── AGENTS.md              (FORGE-specific rules)
├── docs/
│   ├── FSI.md             (from shura-forge/SHURA-ATLAS/)
│   ├── FORGE-CAPABILITIES.md (from shura-forge/SHURA-ATLAS/)
│   └── CONTRIBUTING.md    (from shura-forge/SHURA-ATLAS/)
├── archive/
│   ├── constitution.md    (Vol.I/00-constitution.md)
│   ├── philosophy.md      (Vol.I/01-philosophy.md)
│   └── ...
└── scripts/
    ├── audit-fsi.sh       (from shura-forge/SHURA-ATLAS/)
    └── bootstrap.sh       (from shura-forge/SHURA-ATLAS/)
```

**Pros**:
- Clean, dedicated repository for Forge
- Clear separation from ATLAS (which gets its own repo per Atlas Canonicalization Options)
- Git-ready

**Cons**:
- All Forge content must be migrated from `shura-forge`
- Requires deciding what is "Forge" vs "Atlas" content (currently mixed in `shura-forge/SHURA-ATLAS/`)

### Option B: FORGE.project remains subordinate to ProjectSHURA
Keep Forge documentation inside `projectSHURA/docs/`:

```
projectSHURA/docs/
├── SHURA_V1_ARCHITECTURE_AND_ROADMAP.md
├── forge/
│   ├── FSI.md
│   ├── FORGE-CAPABILITIES.md
│   └── ...
```

**Pros**:
- No migration needed
- Single repository for all SHURA-related work
- Simpler CI/CD

**Cons**:
- Blurs the architecture/runtime separation
- The V1 spec explicitly defines FORGE as a separate "layer"
- Makes it harder to develop FORGE tools (audit scripts, capability ledger) independently

### Option C: shura-forge becomes canonical, FORGE.project is archived
Retain `Projects/shura-forge` as the active repository and treat `FORGE.project` as a superseded scaffold.

**Pros**:
- No content migration — just rename/repurpose
- Preserves existing git history

**Cons**:
- Poor naming (`shura-forge` is less discoverable than `FORGE.project`)
- Contains mixed ATLAS/FORGE content
- Duplicate `shura-forgev1/` needs cleanup

## Recommendation

**Option A: FORGE.project becomes canonical FORGE repository.**

### Rationale
1. **Separation of concerns**: The V1 architecture spec defines FORGE as a distinct layer ("synthesis, conflict-resolution, auditing, evaluation, and canonization layer"). A dedicated repository enforces this.

2. **Naming consistency**: `FORGE.project` follows the same naming convention as `ATLAS.project` — both are canonical, purpose-built repositories.

3. **Clean separation**: Content from `shura-forge/SHURA-ATLAS/` that belongs to ATLAS (Vol.II system map, some references) migrates to `ATLAS.project`. Content that belongs to Forge (FSI, capability ledger, scripts, constitution) migrates to `FORGE.project`.

4. **Duplication elimination**: The `shura-forge/shura-forgev1/` duplicate can be archived alongside the `shura-forge/SHURA-ATLAS/` directory.

### Content Allocation (FORGE.project)
| Source (shura-forge/SHURA-ATLAS/) | Destination (FORGE.project) | Reasoning |
|---|---|---|
| `FSI.md` | `docs/FSI.md` | Forge Status Indicator — Forge's heartbeat |
| `FORGE-CAPABILITIES.md` | `docs/FORGE-CAPABILITIES.md` | Capability ledger — Forge's audit function |
| `CONTRIBUTING.md` | `CONTRIBUTING.md` | Contribution guidelines for Forge |
| `Vol.I/00-constitution.md` | `archive/constitution.md` | Foundational document for the ecosystem |
| `Vol.I/01-philosophy.md` | `archive/philosophy.md` | Philosophical foundation |
| `Vol.I/02-principle-markers.md` | `archive/principle-markers.md` | Principle markers |
| `Vol.I/03-first-major-milestone.md` | `archive/first-milestone.md` | Milestone definition |
| `scripts/audit-fsi.sh` | `scripts/audit-fsi.sh` | Forge audit tooling |
| `scripts/bootstrap.sh` | `scripts/bootstrap.sh` | Forge bootstrap tooling |

### Content Allocation (ATLAS.project)
| Source (shura-forge/SHURA-ATLAS/) | Destination (ATLAS.project) | Reasoning |
|---|---|---|
| `Vol.II/SYSTEM-MAP.md` | `docs/system-map.md` | System architecture map |
| `Vol.II/Sys.*/` | `docs/sys.*/` | System definitions |
| `references/knowledge-triplet.md` | `references/knowledge-triplet.md` | Knowledge schema |
| `references/chatlog-summaries/` | `references/chatlog-summaries/` | Historical record |
| `assets/day-6-aesthetic.json` | `assets/day-6-aesthetic.json` | Aesthetic corpus |

### Migration Plan (requires human approval)
1. Initialize `FORGE.project` git repo with first commit
2. Migrate Forge-specific content from `shura-forge/SHURA-ATLAS/`
3. Archive `shura-forge/` with `SUPERSEDED.md` note
4. Clean up `shura-forge/shura-forgev1/` duplicate

### Do NOT execute without explicit human approval.
