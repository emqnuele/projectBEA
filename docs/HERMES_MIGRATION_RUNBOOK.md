# Hermes Command-Center Migration Runbook

Status: active execution plan
Target: Hermes as primary SHURA command center, Zed as IDE cockpit

## 0. Principle

Do not migrate everything at once.

The target state is:

```text
YOU
 |
 v
HERMES
 |
 +-- model/provider routing
 +-- tools/skills
 +-- repository work
 +-- shell/terminal work
 +-- task context
 +-- Git workflow
 |
 +--> ZED (primary coding cockpit)
 |
 +--> REAPER / MAJIK (creative cockpit)
 |
 +--> PROJECTSHURA (SHURA runtime)
```

Hermes is the command center, not the replacement for every application.

## 1. Current known state

Based on the current SHURA work:

- Project repository: `ultraviollettnympho/projectSHURA`
- active development branch: `shura-foundation`
- Hermes is already installed and has successfully completed an OpenRouter smoke test
- Hermes has been configured with AIHubMix and can select free models
- a local MLX model is available in the environment
- Zed is intended to remain the primary IDE/coding cockpit
- SHURA's repository already contains a unified consciousness/skill architecture

## 2. Migration rule

Keep the number of moving parts low until the command loop is reliable.

For the first usable configuration:

- Hermes = orchestrator/command center
- Zed = interactive editor + terminal cockpit
- ProjectSHURA = runtime/application
- GitHub = source of truth for versioned code
- one primary Hermes model/provider = default
- one fallback model/provider = secondary
- local MLX = fallback/offline coding option

Crush, JCode, Pi, OpenCode and additional providers are secondary tools until the base Hermes loop is stable.

## 3. Phase A: verify local state

Run from the terminal:

```bash
cd ~/path/to/projectSHURA
pwd
git status --short
git branch --show-current
git remote -v
```

Expected:

- repository is the intended ProjectSHURA clone
- branch is `shura-foundation` for active foundation work
- working tree is understood before changes are made
- origin points to the fork

Then verify Hermes:

```bash
hermes --version
hermes -h
```

Run the known smoke test:

```bash
hermes -z "Respond with exactly: HERMES OPENROUTER TEST PASSED"
```

The previous successful result means this is a regression check, not a setup experiment.

## 4. Phase B: establish one Hermes default

Use the provider/model that is currently most reliable and inexpensive for routine work.

Recommended hierarchy for this stage:

```text
PRIMARY: AIHubMix free coding model or other already-working free route
SECONDARY: OpenRouter free route
OFFLINE FALLBACK: local MLX model
```

Do not optimize for theoretical model quality yet. Optimize for:

1. predictable tool use
2. stable context
3. low cost
4. low latency
5. ability to recover when the primary route fails

## 5. Phase C: make ProjectSHURA a first-class Hermes workspace

From the ProjectSHURA repository, create a small workspace contract for Hermes.

The contract should tell an agent:

```text
PROJECT: ProjectSHURA
ROLE: development collaborator
PRIMARY BRANCH: shura-foundation until release branch policy changes
SOURCE OF TRUTH: git repository
READ BEFORE MODIFYING: architecture + relevant source files
AFTER CODE CHANGES: test -> review -> security review -> summarize
NEVER: commit secrets, bypass tests, or push unreviewed release changes
```

Keep this contract small. Detailed personality belongs in SHURA's own prompt/system files, not in every coding command.

## 6. Phase D: prove the development loop

Do one deliberately boring task before attempting architecture work.

Example:

```text
Inspect the skill registration path.
Identify one missing validation or documentation gap.
Implement the smallest safe improvement.
Run the relevant tests/checks.
Review the diff.
Perform a defensive security pass.
Summarize the change without pushing.
```

This proves:

```text
Hermes -> repo -> inspect -> edit -> execute -> test -> review
```

Only after this passes should additional coding agents be layered in.

## 7. Phase E: introduce the release gate

Create a standard release sequence:

```text
WORKTREE CHECK
-> TESTS
-> STATIC/TYPE CHECKS where applicable
-> DIFF REVIEW
-> FUNCTIONAL REVIEW
-> SECURITY REVIEW
-> RED-TEAM QUESTIONS
-> REMEDIATION
-> RETEST
-> RELEASE SUMMARY
-> HUMAN APPROVAL
-> COMMIT/PUSH
```

Human approval remains the final authority for an external push.

The defensive security pass should inspect at minimum:

- secrets accidentally included in changed files
- unsafe shell/command construction
- path traversal/file-write risks
- unvalidated external input
- unsafe subprocess handling
- network requests and credentials
- insecure default configuration
- permission/authorization assumptions
- dependency changes with security implications

## 8. Phase F: add the other coding agents

Once the base loop is stable, assign agents by strength rather than creating a swarm for its own sake.

Suggested conceptual roles:

```text
Hermes = orchestrator
Zed = human/agent coding cockpit
JCode = coding-focused execution
Crush = alternate coding agent
Pi = lightweight/interactive agent
OpenCode = additional coding/runtime path
```

A task should use the fewest agents necessary.

## 9. Phase G: connect SHURA runtime

Do not move the SHURA runtime itself into Hermes.

Instead:

```text
Hermes
  |
  +--> inspect/configure ProjectSHURA
  +--> launch/restart runtime
  +--> inspect logs
  +--> modify source
  +--> test
```

SHURA remains the application being developed.

## 10. Phase H: first creative bridge

After the coding loop is reliable, stop adding infrastructure for a moment.

Create one music workspace:

```text
Song project
 |
 +-- concept notes
 +-- prompts
 +-- generated ACESTEP/Majik material
 +-- stems
 +-- MIDI
 +-- REAPER project
 +-- renders
 +-- mix/master versions
 +-- release metadata
```

Hermes should initially help coordinate this workspace rather than trying to control the entire DAW immediately.

The first creative milestone is simply:

```text
idea -> Majik generation -> export -> REAPER import -> arrangement -> render
```

Then build MCP control incrementally.

## 11. Phase I: reader skill comes after the first creative loop

The Reader/Living Audiobook skill is important, but it should not delay the first return to creative work.

Implement it against the stable TTS/output architecture after the development and creative control paths are proven.

## 12. One-command daily startup target

The final ergonomics goal is a single predictable startup sequence.

Conceptually:

```bash
# command center
hermes

# project cockpit
zed ~/path/to/projectSHURA

# when creating music
open "~/Music/SHURA/<project>"
```

Later, create a small launcher that opens the chosen workspaces and checks status. Avoid making the launcher itself a new orchestration framework.

## 13. What not to do during migration

Do not:

- migrate personality/memory by copying every historical conversation into prompts
- add every provider at once
- add every coding agent before one path works
- build the universal MCP first
- rewrite ProjectSHURA architecture merely to fit Hermes
- create a complex launcher before the manual workflow is proven
- make git push autonomous

## 14. Shortest path to creative flow

The minimal sequence is:

```text
1. verify Hermes + repo state
2. choose primary/default model
3. make ProjectSHURA the standard Hermes workspace
4. complete one edit/test/review cycle
5. make release gating habitual
6. connect Zed as the visual coding cockpit
7. stop infrastructure work temporarily
8. open a real music project
9. generate material in Majik/ACESTEP
10. move it into REAPER
11. create something you actually want to hear
12. resume MCP development based on real friction encountered
```

This is intentionally asymmetric: build only enough infrastructure to remove the next real bottleneck, then create.

## 15. Migration acceptance checklist

Command center:

- [ ] Hermes launches reliably
- [ ] primary model/provider works
- [ ] fallback route works
- [ ] ProjectSHURA opens as the known workspace
- [ ] repository inspection works
- [ ] shell/tool execution works
- [ ] edit/test/review loop works
- [ ] release gate exists

Creative bridge:

- [ ] Majik/ACESTEP generation path works
- [ ] stems/material can be exported
- [ ] REAPER project receives generated material
- [ ] first end-to-end musical sketch is rendered

Only after these boxes are checked should we spend a major block of time expanding the MCP ecosystem.
