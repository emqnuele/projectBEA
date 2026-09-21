# ATLAS Canonicalization Options
Status: DONE (recommendation provided, human approval required)
Date: 2026-09-12

## Current State of Candidate Repositories

### ~/ATLAS.project/
- **Status**: Git repository (initialized, no commits on `master` branch)
- **Files**: `README.md` (8 bytes: `# ATLAS`), `AGENTS.md` (0 bytes)
- **Content**: Empty scaffold — no substantive content
- **Git**: `fatal: your current branch 'master' does not have any commits yet`
- **Conclusion**: Uninitialized scaffold with placeholder content

### ~/projectSHURA/
- **Status**: Git repository (93 commits, branch: `shura-foundation`)
- **ATLAS-related files**:
  - `docs/shura/IDENTITY_MANIFEST.md` — defines ATLAS as the "architectural/knowledge representation layer"
  - `docs/SHURA_V1_ARCHITECTURE_AND_ROADMAP.md` — describes ATLAS as the historical/context corpus
  - `docs/architecture.md` — older architecture doc (superseded by V1 spec)
- **Content**: Detailed architecture, identity definitions, and documentation
- **Conclusion**: The authoritative definition of ATLAS's role exists here

### ~/Projects/shura-forge/SHURA-ATLAS/
- **Status**: Git repository (1 commit: "Initial Forge structure")
- **Content**:
  - `FSI.md` — Forge Status Indicator (heartbeat document)
  - `FORGE-CAPABILITIES.md` — Capability ledger
  - `CONTRIBUTING.md` — Contribution guidelines
  - `README.md` — Overview
  - `Vol.I/` — Constitution, philosophy, principle markers, first milestone
  - `Vol.II/Sys.*` — System map (10 subsystems: Philosophy through Evolution)
  - `references/` — Knowledge artifacts
  - `scripts/` — `audit-fsi.sh`, `bootstrap.sh`
  - `assets/` — Aesthetic definitions
- **Conclusion**: Active content repository with substantial architectural material

### ~/Shura/ (standalone directory)
- **Status**: Not a git repository
- **Content**: `OPERATING_MANUAL.md`, `PROJECTS.md`
- **Relevance**: References ATLAS conceptually; no direct content

## Options Analysis

### Option A: ATLAS.project becomes canonical ATLAS repository
**Pros**:
- Name clearly identifies it as ATLAS
- Clean, dedicated repository for knowledge/content
- Can be populated with the content from `shura-forge/SHURA-ATLAS/`
- Git-ready for version control

**Cons**:
- Currently empty — all content must be migrated
- Loses git history from `shura-forge` (only 1 commit, so low cost)
- Would need to decide whether to keep `shura-forge` as a working copy or archive it

**Migration needed**:
- `FSI.md` → ATLAS root or `docs/`
- `FORGE-CAPABILITIES.md` → `docs/`
- `CONTRIBUTING.md` → root
- `Vol.I/` and `Vol.II/` → `atlas/` or `docs/atlas/`
- `references/` → `references/`
- `scripts/` → `scripts/`
- `assets/` → `assets/`

### Option B: ATLAS remains subordinate to ProjectSHURA
**Pros**:
- Single repository, simpler management
- All architecture docs already exist in `projectSHURA/docs/`
- No migration needed
- Version control history preserved

**Cons**:
- Blurs the identity/runtime separation
- ProjectSHURA is meant to be the "runtime/identity implementation" — ATLAS is the "historical/context corpus" (per the architectural spec)
- Mixing canonical knowledge base with runtime code creates tight coupling
- Makes it harder to version ATLAS independently from SHURA's implementation

### Option C: Repository retained as historical source; ATLAS.project becomes active
**Pros**:
- Preserves `shura-forge/SHURA-ATLAS/` as historical reference
- Gives ATLAS a clean, purpose-built home
- Allows both to coexist: historical record + active implementation

**Cons**:
- Potential confusion about which is authoritative
- Requires clear documentation of the relationship
- More directories to manage

## Recommendation

**Option A: ATLAS.project becomes canonical ATLAS repository.**

### Rationale
1. **Separation of concerns**: The architectural spec explicitly defines ATLAS as the "historical/context corpus and retrieval layer" (distinct from ProjectSHURA which is the "runtime/identity implementation"). Using a dedicated repository enforces this separation.

2. **Clean state**: `ATLAS.project` is an empty scaffold — no content to preserve or conflict with. Migration is straightforward.

3. **Git readiness**: Starting commits in `ATLAS.project` gives ATLAS its own clean version history, independent of ProjectSHURA's development branch.

4. **Future retrieval layer**: ATLAS will eventually need a retrieval/search index. Having a dedicated repository makes it easier to add vector databases, search configurations, and retrieval infrastructure without coupling to ProjectSHURA's Python project structure.

### Migration Plan (requires human approval)
1. Initialize `ATLAS.project` with a commit
2. Migrate content from `Projects/shura-forge/SHURA-ATLAS/`:
   - `FSI.md` → `ATLAS.project/docs/FSI.md`
   - `FORGE-CAPABILITIES.md` → `ATLAS.project/docs/FORGE-CAPABILITIES.md`
   - `Vol.I/`, `Vol.II/` → `ATLAS.project/atlas/Vol.I/`, `atlas/Vol.II/`
   - `references/` → `ATLAS.project/references/`
   - `scripts/` → `ATLAS.project/scripts/`
   - `assets/` → `ATLAS.project/assets/`
3. Archive `shura-forge/SHURA-ATLAS/` with a `SUPERSEDED.md` note pointing to `ATLAS.project`
4. Add `.gitignore`, `README.md` with actual content, `AGENTS.md`

### Do NOT execute without explicit human approval.
