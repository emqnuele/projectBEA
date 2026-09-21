# ProjectSHURA v1.0 Architecture & Release Roadmap

Status: planning baseline
Branch: `shura-foundation`

## 1. Purpose

ProjectSHURA extends the ProjectBEA foundation into a modular personal AI environment centered on one persistent SHURA identity and one shared agency layer.

The architectural rule is:

> **Skills describe capabilities. MCPs describe external control. Core describes identity, reasoning, memory, priorities, and agency.**

Do not put provider-specific behavior, DAW control, coding-agent orchestration, or document-reader logic directly into the soul/persona layer.

## 2. Current foundation

The existing foundation already provides:

- a single-brain consciousness loop
- perception aggregation
- runtime skill registration and toggling
- shared expression/output handling
- memory, social memory, dream, chat, voice, idle, and Minecraft surfaces
- prompt composition from soul + operating manual
- runtime configuration reload
- correlation-based request/reply for local entrypoints
- avatar and TTS integration points

See `src/core/brain.py`, `src/core/config.py`, and the existing documentation before adding parallel pathways.

## 3. Target architecture

```text
                         PROJECTSHURA
                              |
                 +------------+------------+
                 |                         |
          SHURA CORE / IDENTITY       SHARED CONTEXT
                 |                         |
                 +------------+------------+
                              |
                       AGENCY / ORCHESTRATION
                              |
       +----------------------+----------------------+
       |                      |                      |
 DEVELOPMENT              CREATIVE              KNOWLEDGE
   DOMAIN                  DOMAIN                 DOMAIN
       |                      |                      |
 Hermes / Zed            Majik / ACESTEP          Library
 JCode / Pi              REAPER                  PDFs / MD / TXT
 Crush / OpenCode        GameDev                 Research
       |                      |                      |
       +----------------------+----------------------+
                              |
                         TOOL / MCP LAYER
                              |
             +----------------+----------------+
             |                |                |
           GitHub           REAPER          Majik/API
             |                |                |
          external        external          external
          services        control           services
```

## 4. Major subsystems

### A. Development Agent Harness

Highest priority subsystem.

Goal: SHURA participates in the complete software lifecycle instead of merely generating code.

Pipeline:

```text
idea
-> specification
-> architecture
-> task decomposition
-> agent assignment
-> implementation
-> build/test
-> functional review
-> security review
-> red-team review
-> remediation
-> retest
-> diff/change summary
-> commit
-> release approval
```

Primary cockpit: Hermes + Zed.

Supporting agents: Crush, JCode, Pi, OpenCode, and other compatible coding agents/providers.

Required v1 behavior:

1. inspect repository before editing
2. maintain explicit task state
3. execute tools/commands through controlled interfaces
4. run tests/builds after substantive changes
5. review changed behavior, not merely syntax
6. perform a defensive security review before release
7. identify findings by severity and confidence
8. fix actionable findings when safe to do so
9. retest after remediation
10. produce a release summary before git push

Release gate should fail closed when tests or critical security checks fail.

### B. SHURA Reader / Living Audiobook

One skill, several modes:

- `READ`: continuous reading
- `COMMENTARY`: reading plus SHURA reactions
- `CONVERSATION`: reading plus user interaction
- `STREAM`: reading/discussion with audience chat selection
- `EXPORT`: render audio to file

Input types:

- PDF
- EPUB when supported
- Markdown
- plain text
- library-managed documents

Pipeline:

```text
source
-> extraction
-> structure/chapter segmentation
-> semantic/context analysis
-> SHURA interpretation layer
-> delivery controls
-> TTS
-> stream or export
```

The interpretation layer can annotate:

- emphasis
- pace
- pause
- energy
- affect
- cadence
- reaction intensity

The reactions must remain subtle by default and must never silently rewrite the source text in read-only mode.

Export targets:

- WAV: lossless production master
- FLAC: lossless compressed archive
- AAC/MP3: practical listening copies

Interactive mode should support soft barge-in:

```text
user input detected
-> assess current SHURA utterance
-> finish sentence/clause when appropriate
-> transition
-> answer
-> restore reading/discussion context
```

Conversation authority:

```text
user > shura > audience chat
```

Audience chat is an input stream, not an authority layer. Selection should consider relevance, novelty, connection to current discussion, and user-defined preferences.

### C. Creative Music / DAW Integration

Initial scope:

```text
ideation
-> song specification
-> Majik / ACESTEP generation
-> stems / MIDI / textures
-> REAPER arrangement
-> sound design
-> mixing
-> mastering
-> metadata
-> distribution preparation
```

MCP capabilities should be granular and composable rather than exposing one giant opaque "make song" action.

Initial REAPER tool families:

- project
- track
- transport
- audio import/export
- MIDI import/export/edit
- instrument/plugin loading
- plugin parameter control
- sample/library access
- render
- mix controls

Initial Majik capabilities should mirror what its MCP interface actually exposes rather than inventing abstractions prematurely.

### D. ATLAS

Do not implement blindly.

Before coding, define:

- exact problem
- primary users
- canonical data model
- inputs/outputs
- SHURA integration points
- external integrations
- what belongs in ATLAS versus SHURA core
- v1 success criteria

Required red-team passes:

1. conceptual coherence
2. utility and user-value
3. architecture and maintenance cost

### E. FORGE

Apply the same specification-first process as ATLAS.

Explicitly test whether a proposed FORGE capability belongs in SHURA, ATLAS, or FORGE before implementing it.

### F. INFAC

Treat as a separate community/cultural design domain, not merely another technical skill.

Exploration areas include:

- bottom-up community formation
- mutual aid
- resource and skill exchange
- participatory processes
- autonomous cultural production
- shared symbols and rendezvous
- distributed publishing and education

Keep philosophical/community-building design distinct from any harmful operational activity.

### G. Game Development / Worldbuilding Mode

Dedicated mode with context-aware submodes:

- concept
- world
- character
- lore
- mechanics
- level design
- narrative
- visual development
- audio
- prototyping
- implementation
- playtest

Core loop:

```text
idea
-> world premise
-> aesthetic language
-> references
-> characters/environments
-> systems
-> prototype
-> playtest
-> iteration
```

## 5. Release strategy

### v0.1-v0.3: foundation stabilization

- preserve single-brain architecture
- stabilize configuration
- stabilize skill lifecycle
- stabilize provider abstraction
- stabilize prompt/personality boundaries
- clean logging and error behavior
- document extension contracts

### v0.4-v0.6: development agency

- Hermes cockpit integration
- Zed workflow
- coding-agent routing
- repository inspection
- command execution
- tests/builds
- Git integration
- review and release gate

### v0.7: creative agency

- Majik/ACESTEP integration contract
- first REAPER MCP
- project/track/audio/MIDI primitives
- basic SHURA orchestration

### v0.8: knowledge agency

- library ingestion
- document parsing
- document structure model
- retrieval/context handoff

### v0.9: voice agency

- reader skill
- read-only streaming
- TTS interpretation layer
- WAV/FLAC export

### v0.95: interactive media

- commentary mode
- conversation mode
- soft barge-in
- audience chat ranking
- discussion export

### v1.0: integrated SHURA environment

The first stable release is complete when the development, knowledge, voice, and creative pathways share one core identity/context/orchestration layer and can be independently enabled without cross-domain architectural leakage.

## 6. Definition of Done for v1.0

A release is not v1.0 merely because every feature exists.

It must also have:

- deterministic configuration behavior
- documented extension points
- test coverage for critical orchestration paths
- defensive security review
- clear failure states
- reproducible setup
- secrets excluded from committed config
- clean Git history for release changes
- migration documentation
- rollback guidance
- explicit boundaries around experimental components

## 7. Immediate implementation order

The shortest useful path is:

```text
1. Finish Hermes command-center migration
2. Establish Hermes <-> repo workflow
3. Establish coding-agent routing
4. Add test/review/security release gate
5. Prove one complete development task end-to-end
6. Build first SHURA creative MCP, starting with REAPER primitives
7. Connect Majik/ACESTEP generation into the REAPER flow
8. Begin actual music creation
9. Return to Reader/ATLAS/FORGE as focused implementation tracks
```

Do not block creative work on full v1.0 completion. The release roadmap governs architecture; creative work is also a validation environment.

## 8. Architectural guardrails

- no duplicate consciousness loops
- no provider-specific logic in soul files
- no direct DAW implementation inside SHURA core
- no giant universal MCP with unrelated actions
- no autonomous git push without release-gate results
- no silent source-text modification in reader read-only mode
- no treating audience chat as equal authority to the user
- no expanding ATLAS/FORGE implementation before red-team specification

## 9. First production milestone

The first meaningful milestone is not "v1.0 finished."

It is:

> **SHURA can sit at the Hermes/Zed cockpit, inspect a project, carry out a non-trivial coding task, test and review the result, and then switch contexts into a real creative workflow without losing identity or project context.**

That is the shortest bridge from architecture to actually making things.
