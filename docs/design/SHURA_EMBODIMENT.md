# SHURA Embodiment Model — Design (VERIFIED + PROPOSED)

Status: Design document — V1 embodiment strategy.
Verified current state (from `src/core/expression.py`, `brain.py`, `docs/DREAM_ENGINE.md`, `docs/AGENTS.md`):
- Embodiment uses `Expression` adapter (`expression.py`) which connects `TTSInterface`, `OBSInterface`, and `png_map` (avatar resources loaded by `load_avatar_resources`).
- Avatar state is driven by `mood` strings (`normal`, `shock`, `love`, `cry`, `angry`, `ew`, `bored`, plus `neutral`, `excited`, `sad`, etc. — the legacy 7 mood IDs plus extended moods). These are preserved (`AGENTS.md` hard rule).
- `brain.py` creates `Expression(config, tts, obs, self.event_manager)`. `Expression` does not import identity (`soul.md`) or cognition (`consciousness.py`) directly; it uses `event_manager` for events and config for mood/text parameters.
- No Live2D model exists. No 3D model exists. No sprite animation framework exists. The current avatar is PNG-based (`avatar_map` file paths configured in `config.json`).
- The `expression.py` adapter manages typing (`type_text()`), TTS audio (`generate_audio()`), audio playback (`_play_audio()`), interrupt/resume, and OBS avatar pose switching (idle, talking, shocked, love, etc.).

---

## Embodiment-State Contract (PROPOSED — must be preserved for V1 and future upgrades)

This contract separates identity (who SHURA is) from presentation (how SHURA appears) from cognition (what SHURA is thinking). It must be preserved regardless of whether V1 uses PNG, Live2D, or 3D.

### Identity Layer (VERIFIED — exists, must not change except through governed review)
- Source: `data/prompts/soul.md` (personality, values, aesthetic sensibility, relationship with Viollett), `operating.md` (behavior rules, anti-sycophancy, intellectual posture, creative identity), `chat.md`, `monologue.md`.
- Must NOT include: model provider names, avatar file paths, OBS settings, current mood, temporary project names, session IDs.
- Changes require: identity-sync process (`docs/IDENTITY_SYNC.md` skeleton exists), human review, divergence confirmation (`docs/IDENTITY_SYNC.md`), MD5 identity check (`6aabb046958ddedaf0bd62b14ad6fe18` verified in previous audit).

### Presentation Layer (PROPOSED — design contract for V1, future upgrade path for Live2D/3D)
- Source: `Expression` adapter (`expression.py`), avatar resources (`avatar_map`), future Live2D/3D model files, future sprite/animation framework.
- State contract fields (must be observable for UI, but not owned by brain/consciousness):
  - `current_pose`: idle | talking | thinking | working | dreaming | error | attention | success | interrupted | resumed (derived from event states + brain state, not arbitrary internal variables).
  - `current_text`: message being spoken (derived from `Expression.set_text()` / `type_text()`; not identity).
  - `current_mood`: neutral | excited | sad | shocked | love | angry | bored | ew (derived from LLM response mood; identity-independent).
  - `current_state_indicator`: active | sleeping | interrupted | resumed (derived from brain/consciousness state; observable through projection, not identity).
  - `avatar_reference`: current PNG file / sprite index / Live2D model / 3D model (operational reference; identity-independent).
- Must NOT include: identity statements (`soul.md` content), system prompts (`operating.md` rules), memory contents, event payload details (those belong to projection/event layers, not embodiment).
- Must NOT directly import brain/consciousness internals; must use event/projection interfaces (`EventCategory.EMBODIMENT` events, `DreamStateProjection`, `expression.py` adapter interface).

### Projection → Embodiment Mapping (PROPOSED — interface design for V1)
The `DreamStateProjection` (`projection.py`, added in previous implementation pass) provides the read-only observable state. The embodiment adapter translates projection fields into visual states:

| Projection Field | Embodiment State | Visual Representation (V1: PNG/sprite; Future: Live2D/3D) |
|---|---|---|
| `run_state` = `created` / `started` | Working / active | Talking pose + typing animation |
| `run_state` = `snapshot_created` | Observing / reading | Thinking pose + subtle motion |
| `run_state` = `reconciliation_started` / `reconciliation_completed` | Processing / integrating | Working pose with glow/animation |
| `run_state` = `completed` | Completed / satisfied | Success pose + brief celebration animation |
| `run_state` = `failed` | Error / blocked | Error pose + red indicator + visible error message |
| `replay_sequence_count` > 0 | Active execution (event replay shows progress) | Active indicator in workspace rail |
| `transaction_status` = `rehearsed` / `validated` / `committed` | Task/progress stage visible | Progress bar / stage indicator |
| `metrics` (derived from `DreamSnapshot`) | System health / performance observation | Health/status panel in workspace |
| No `run_id` or `run_state` = `created` with no replay | Idle / available | Idle pose + ambient animation |

This mapping must be implemented as a presentation adapter (`FORGE` workspace layer or `Expression` extension), not as brain/consciousness logic. The brain/consciousness loop produces events; the projection layer reads events; the embodiment adapter translates projection to visual states.

---

## SHURA_01 / SHURA_02 Design (PROPOSED — future embodiment versions)

The reference name `Shura_01` / `Shura_02` appears in `docs/shura/IDENTITY_MANIFEST.md` and `SHURA_MASTER_HANDOFF.md` (verified file presence). The design must support multiple embodiment versions without identity divergence.

### SHURA_01 (Current / V1 reference)
- Form: 2D digital avatar (PNG/sprite-based) — current implementation (`png_map`, `avatar_map` in `config.json`).
- Expression: mood-based pose switching (`Expression.set_png_map()` uses `png_map` dictionary mapping mood strings to file paths). Text bubble output (`OBSInterface`). TTS audio synchronized with text animation (`Expression.perform_output_task()`).
- State: idle, talking, interrupted, resumed, working, thinking, error. Driven by event emission (`EventCategory.EMBODIMENT`) + brain state (sleep/awake, speaking status).
- Limitations: no continuous animation; discrete pose changes only. No real-time facial expression changes independent of mood. No body language beyond avatar pose.

### SHURA_02 (Future / Post-V1 target — PROPOSED)
- Form: Live2D model or 3D avatar (not implemented; must leave extension point).
- Requirements (derived from design target and identity preservation rules):
  1. Must preserve identity independence: model file references are in presentation/config layer (`avatar_map` or future `embodiment_config`), not `soul.md`.
  2. Must preserve mood ID compatibility: new model must support the legacy 7 mood IDs (`normal`, `shock`, `love`, `cry`, `angry`, `ew`, `bored`) or provide an explicit migration path (not silent removal).
  3. Must observe projection/state contract (`projection.py`): visual states derived from `DreamStateProjection` fields (run_state, replay_sequence, metrics, snapshot observations), not arbitrary brain internals.
  4. Must use event/projection interface: embodiment state changes must be observable through `EventCategory.EMBODIMENT` events (already defined in event taxonomy) or projection updates (`/dream/projection` endpoint), not hidden in model internals.
  5. Must not couple cognition directly to rendering: brain/consciousness must not import Live2D/3D libraries. The `Expression` adapter (or future `EmbodimentAdapter`) handles rendering independently.
- Implementation path: deferred to post-V1 milestone; architecture must leave extension points (`Expression` adapter interface, `avatar_map` config, `projection.py` embodiment-state mapping, `docs/design/SHURA_EMBODIMENT.md` contract document).

---

## Embodiment Design Rules (PROPOSED — must be preserved for V1 and future)

1. **No identity in avatar file names**: The `avatar_map` file references (`png` paths) must not include SHURA identity content (e.g., no `shura_soul_normal.png`). They are presentation assets.
2. **No brain import in rendering layer**: `Expression` adapter uses `event_manager`, `config`, `png_map`, `tts`, `obs` — not `brain.consciousness`, `brain.event_manager.replay()` internals, or `DreamEngine` internals (verified by `expression.py` import inspection). Any future `EmbodimentAdapter` must maintain this separation.
3. **Embodiment events are observable**: Any embodiment state change (pose change, text bubble, audio start/stop, error indicator) must emit an event through `EventCategory.EMBODIMENT` or be observable through the projection interface (`/dream/projection`, `DreamStateProjection`). The UI must observe, not create hidden state.
4. **Embodiment does not trigger cognition**: Changing avatar pose, text bubble, or audio playback does not trigger LLM calls, memory mutations, or event emission that affects cognition. The flow is one-directional: cognition → event/projection → embodiment rendering.
5. **Future Live2D/3D upgrade must respect the contract**: Any upgrade must read `DreamStateProjection` (or future expanded projection model) and map projection fields to model states using the embodiment-state mapping above, without importing brain internals.
