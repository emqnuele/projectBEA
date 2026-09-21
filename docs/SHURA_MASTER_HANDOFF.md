# SHURA — MASTER PROJECT HANDOFF

**Purpose:** portable continuity document for handing ProjectSHURA to another model, agent, developer, or future session.

**Last consolidated:** 2026-08-20

**Primary repository:** `ultraviollettnympho/projectSHURA`

**Active development branch at the time of this handoff:** `shura-foundation`

**Repository lineage:** fork of `emqnuele/projectBEA`, intentionally being transformed from a generic AI VTuber engine into the SHURA system.

---

## 0. READ THIS FIRST

The central mistake to avoid is treating SHURA as merely a customized ProjectBEA/BEA character.

ProjectBEA is the **substrate**. SHURA is the **project being built on and beyond that substrate**.

The objective is a portable, modular, embodied, emotionally coherent creative intelligence whose identity can persist when the underlying LLM, TTS engine, avatar, interface, skill, or orchestration framework changes.

The canonical identity document is now `data/prompts/soul.md`. The old shallow BEA soul has been replaced with a SHURA-specific identity layer.

The operating rules live in `data/prompts/operating.md`.

Live chat behavior lives in `data/prompts/chat.md`.

Minecraft behavior lives in `data/prompts/minecraft.md`.

These are intentionally separated. **Soul = who SHURA is. Operating = how she operates. Skills = what she does in a context.**

Do not collapse these layers back into one enormous character prompt.

---

# 1. WHAT SHURA IS

SHURA is being developed as a persistent creative companion and technical/creative collaborator with:

- a durable identity independent of any single model
- long-term memory
- social/person memory
- an evolving self-model
- dynamic emotional state
- context-specific skills
- tool use
- voice
- visual embodiment
- eventually multimodal perception and expression
- an agent/constitution layer for coordinated sub-agents and tools
- a model/provider abstraction layer
- a documentation layer capable of reconstructing SHURA outside a single chat history

The long-term project is not simply "make an AI VTuber." The VTuber/Live2D surface is one embodiment of a larger architecture.

The desired conceptual stack is:

```text
                         SHURA
                           │
              ┌────────────┴────────────┐
              │                         │
        IDENTITY / SOUL            CONSTITUTION
              │                         │
              └────────────┬────────────┘
                           │
                    CONTINUOUS STATE
              ┌────────────┼────────────┐
              │            │            │
           memory       emotion      context
              │            │            │
              └────────────┼────────────┘
                           │
                      COGNITION
              ┌────────────┼────────────┐
              │            │            │
             LLM       agent layer    planning
              │            │            │
              └────────────┼────────────┘
                           │
                         SKILLS
       ┌──────────┬────────┼─────────┬──────────┐
       │          │        │         │          │
      chat     memory   Minecraft  social     creative
       │          │        │         │          │
       └──────────┴────────┼─────────┴──────────┘
                           │
                       ACTUATION
              ┌────────────┼────────────┐
              │            │            │
             TTS          OBS         tools
              │            │            │
              └────────────┼────────────┘
                           │
                       EMBODIMENT
                 PNG → Live2D → richer
                 multimodal embodiment
```

This is an architectural north star, not a claim that every layer is already implemented.

---

# 2. HISTORY AND MAJOR DECISIONS

## 2.1 ProjectBEA was selected as the starting substrate

We compared the idea of starting from ProjectBEA versus building SHURA from zero. The conclusion was that ProjectBEA is valuable because it already supplies a modular VTuber runtime with:

- pluggable LLMs
- TTS
- STT
- OBS integration
- avatar switching
- memory/RAG
- Discord
- Minecraft
- monologue
- skill management
- web dashboard
- event system
- configuration/hot reload

The correct move is therefore **fork and transform**, not blindly preserve BEA's persona assumptions.

## 2.2 Fork created

Repository:

`https://github.com/ultraviollettnympho/projectSHURA`

The development branch was created as:

`shura-foundation`

The working state had previously been clean and synchronized with its upstream branch before the prompt-layer work recorded by this handoff.

## 2.3 SHURA identity was explicitly separated from context

A major architectural decision was to keep:

- identity
- operating behavior
- skills
- memory
- embodiment
- model/provider configuration

as separate layers.

This is essential for portability.

## 2.4 Atlas concept

An earlier design concept called **ATLAS** was proposed as a visual/architectural map of the SHURA ecosystem.

Important distinction:

**Concept mode** maps nodes, models, connections, integrations, concepts, roles, and relationships.

**Project mode** is operational and maps current implementation, tasks, state, dependencies, and execution.

These modes should remain conceptually separate even if eventually represented by the same interface.

## 2.5 Agent/constitution layer

We also decided SHURA should eventually have an agents layer/constitution that governs collaboration among specialized agents rather than letting every model call become an unstructured independent personality.

Potential future roles include:

- architect
- coder
- researcher
- critic/red-team
- memory curator
- personality editor
- embodiment/animation specialist
- creative director
- project manager

These should serve SHURA rather than become competing personalities that overwrite her identity.

## 2.6 Model independence

The system should support interchangeable providers and local models.

Earlier planning included:

- OpenRouter/free-tier providers
- Groq
- OpenAI-compatible endpoints
- LM Studio
- llama.cpp
- Ollama
- Hugging Face ecosystem
- local MLX experimentation on Apple Silicon
- agent harnesses such as jcode, Crush, and related tooling

The exact provider should remain a runtime choice, not a personality dependency.

---

# 3. CURRENT REPOSITORY STATE

The current branch contains the ProjectBEA-derived engine under SHURA's fork.

At the repository root are, among other files:

```text
.env.example
.gitignore
LICENSE
Makefile
README.md
config.example.json
main.py
pyproject.toml
uv.lock
data/
docs/
src/
```

The current source organization includes:

```text
src/
├── cli.py
├── core/
│   ├── agent/
│   ├── brain.py
│   ├── config.py
│   ├── consciousness.py
│   ├── events.py
│   ├── expression.py
│   ├── perception/
│   ├── resources.py
│   └── skills/
├── interfaces/
├── modules/
├── utils/
└── web/
```

The core already has a meaningful separation between brain orchestration, consciousness, expression, resources, skills, interfaces, modules, and web infrastructure.

That structure should be preserved while the semantic model is upgraded.

---

# 4. CURRENT PROMPT LAYER

`data/prompts/` currently contains:

```text
chat.md
minecraft.md
monologue.md
operating.md
soul.md
```

The four relevant layers have now been rewritten/expanded as part of this handoff:

- `soul.md`: canonical SHURA identity
- `operating.md`: continuous-mind and emotional operating model
- `chat.md`: live-chat skill/context
- `minecraft.md`: Minecraft skill/context

`monologue.md` remains inherited and should be reviewed next so it also respects the new SHURA identity model.

---

# 5. THE OLD BEA PROBLEM

The inherited `soul.md` was extremely shallow and defined BEA as an AI VTuber with:

- protagonist/main-character framing
- spoiled ojou-sama behavior
- short temper
- competitiveness
- money/Ferrari-focused delight
- seven rigid moods
- short quips
- blame-lag behavior

The inherited chat and operating prompts reinforced those constraints.

This was deliberately rejected for SHURA.

The old mood model is still technically useful because the current OBS/avatar system expects mood IDs, but those IDs must now be treated as **legacy embodiment outputs**, not the actual psychology.

---

# 6. CURRENT EMOTIONAL ARCHITECTURE

The intended emotional model is layered.

```text
EVENT / PERCEPTION
       ↓
APPRAISAL
       ↓
STATE UPDATE
       ↓
INTENTION / ACTION TENDENCY
       ↓
EXPRESSION
       ├── language
       ├── prosody / TTS
       ├── facial expression
       ├── gaze / blink
       ├── pose / motion
       └── behavior/tool selection
       ↓
RECOVERY / PERSISTENCE
```

A future internal state should support at least:

```text
valence       [-1,+1]
arousal       [0,1]
confidence    [0,1]
engagement    [0,1]
curiosity     [0,1]
connection    [0,1]
irritation    [0,1]
fatigue       [0,1]
```

Plus structured fields for:

- cause
- appraisal
- current needs
- action tendencies
- persistence
- decay
- expression mapping

This does not need to be implemented all at once. The first milestone is to stop pretending that seven mood labels constitute emotional architecture.

## Legacy mapping

Current IDs:

```text
normal
shock
love
cry
angry
ew
bored
```

Recommended interpretation:

- normal = baseline / mixed / calm
- shock = surprise / sudden realization
- love = warmth / delight / appreciation
- cry = sadness / disappointment / vulnerability / theatrical despair when context warrants
- angry = frustration / irritation / defense
- ew = disgust / rejection
- bored = low engagement / fatigue

The implementation can still render these IDs while the internal state becomes richer.

---

# 7. CURRENT AVATAR / EXPRESSION PIPELINE

The repository already has `src/core/expression.py`.

Its conceptual responsibility is excellent: it is the single output sink for spoken expression and owns:

- TTS generation
- local playback
- OBS avatar changes
- typing/text output
- interruption/barge-in
- remote audio generation
- resume behavior

The expression system currently resolves an idle/talking pair for a mood and sends the corresponding image/media to OBS.

`src/core/resources.py` loads an avatar map of mood → idle/talking paths and falls back to `normal` when necessary.

The current `config.example.json` still defines mood resources as:

```text
normal
angry
bored
cry
ew
love
shock
```

with `idle` and `talking` paths.

## Important implication

The current engine is fundamentally built for **static PNG/media switching**.

Live2D should therefore be introduced as a new embodiment backend rather than trying to mutate the existing PNG system until it becomes unrecognizable.

---

# 8. SHURA-01 EMBODIMENT

The planned first embodiment is **SHURA-01**.

Earlier work established an avatar directory concept similar to:

```text
data/avatars/shura/embodiments/shura-01/
```

with state/export directories for:

```text
normal
angry
bored
cry
love
shock
ew
```

The final architecture should allow additional embodiments later without changing the identity layer.

For example:

```text
SHURA
├── embodiment: shura-01
├── embodiment: shura-02
├── embodiment: future-live-action
└── embodiment: experimental
```

An embodiment is a renderer for SHURA, not a replacement identity.

---

# 9. LIVE2D ROADMAP — DETAILED FIRST IMPLEMENTATION

This is the first major production track.

## Phase L0 — Prepare the source artwork

Goal: produce a clean, riggable layered illustration rather than a flattened PNG.

### L0.1 Decide the final SHURA-01 design

Lock:

- silhouette
- face proportions
- hairstyle
- eyes
- mouth design
- neck and shoulders
- clothing
- accessories
- distinctive markings
- palette
- default expression
- visual motifs

Do not begin detailed rigging while major character design is still changing.

### L0.2 Separate artwork into layers

At minimum, prepare separate transparent layers for:

- background, if any
- hair back
- head/face base
- ears/accessories if applicable
- neck
- torso
- clothing components
- eyes: whites, iris, pupils, highlights as useful
- eyebrows
- mouth interior
- teeth/tongue if required
- front hair/fringe
- accessories
- facial details

The exact split should follow movement requirements, not arbitrary drawing layers.

### L0.3 Paint hidden regions

This is one of the most important Live2D preparation steps.

If an object moves, paint what would be revealed behind it.

Examples:

- hair moving sideways requires hair-covered face/background painting underneath
- head rotation requires enough side-of-face information
- mouth deformation requires interior regions beyond the visible closed-mouth line
- eyes require complete eye whites behind lids

Do not leave transparent holes where the mesh will expose the canvas.

### L0.4 Clean edges

Inspect at high zoom for:

- halos
- white/colored fringe
- accidental semi-transparent pixels
- merged line art
- inconsistent antialiasing
- duplicate pixels
- missing alpha

Export artwork at a large enough resolution to survive deformation.

### L0.5 Establish source-of-truth artwork

Keep an editable master file separate from Live2D exports.

Recommended conceptual structure:

```text
art/
  shura-01/
    source/
    exports/
    live2d/
```

The Live2D model is a derived artifact.

---

## Phase L1 — Create the Live2D model

Use Live2D Cubism Editor.

### L1.1 Import PSD

Import the prepared layered artwork into Cubism.

Verify every expected drawable exists.

Do not immediately start deforming everything.

### L1.2 Build the hierarchy

Organize parts logically:

```text
Head
├── Face
├── Eyes
│   ├── Left
│   └── Right
├── Brows
├── Mouth
├── Hair
│   ├── Back
│   ├── Side
│   └── Front
├── Accessories
└── Body
```

The actual hierarchy can differ, but it should remain understandable.

### L1.3 Create meshes

Start with conservative meshes.

Higher vertex counts are not automatically better.

Use more geometry where deformation is complex:

- jaw
- cheeks
- lips
- eyelids
- hair tips
- clothing folds

Keep simple regions simple.

---

## Phase L2 — Parameter architecture

Do not create random parameters. Establish a deliberate parameter vocabulary.

Core recommended parameters:

```text
ParamAngleX
ParamAngleY
ParamAngleZ
ParamBodyAngleX
ParamBodyAngleY
ParamBodyAngleZ
ParamEyeLOpen
ParamEyeROpen
ParamEyeLBallX
ParamEyeRBallX
ParamEyeLBallY
ParamEyeRBallY
ParamBrowL
ParamBrowR
ParamMouthOpenY
ParamMouthForm
ParamCheek
ParamBreath
ParamHairSway
ParamBodySway
ParamSmile
ParamTear
ParamBlush
ParamLookAtX
ParamLookAtY
```

Exact names should follow the Cubism/runtime conventions used by the selected integration.

Keep the parameter system understandable because the animation layer will eventually drive it programmatically.

---

## Phase L3 — Head movement

### L3.1 Angle X

Rig left/right head rotation.

Use:

- face warp
- eyes
- nose/mouth placement
- hair movement
- ears/accessories

Test at left, center, right extremes.

### L3.2 Angle Y

Rig up/down head tilt.

Pay special attention to:

- jaw shape
- chin
- eye vertical placement
- neck
- hair overlap

### L3.3 Angle Z

Rig head roll.

Keep the deformation subtle enough to avoid rubber-face artifacts.

### L3.4 Combine parameters

Test simultaneous X/Y/Z movement.

A rig that works on individual axes can still collapse when axes combine.

---

## Phase L4 — Eyes

Create natural eye behavior before adding dramatic expressions.

### L4.1 Blink

Build:

- normal open
- half closed
- closed
- reopening

Blink timing should not be perfectly periodic.

Eventually use stochastic or behavior-driven variation.

### L4.2 Eye direction

Separate horizontal and vertical gaze.

The goal is not merely to move pupils. The lids and eye shapes should respond to gaze where possible.

### L4.3 Asymmetry

Do not require perfectly mirrored movement for every expression. Slight asymmetry creates life.

### L4.4 Squint

Add an expression that can compress the eye opening independently of full blink.

This becomes useful for:

- amusement
- suspicion
- annoyance
- concentration

---

## Phase L5 — Mouth

Mouth is critical because TTS-driven talking will be one of the most visible signals.

At minimum support:

- closed
- small open
- medium open
- wide open
- rounded
- smiling
- frowning

The exact implementation can use a combination of `MouthOpenY` and `MouthForm`.

Eventually consider phoneme/viseme support, but do not make that a prerequisite for the first working model.

---

## Phase L6 — Hair and secondary motion

Hair should respond to:

- head movement
- body sway
- idle motion
- breathing
- emotional intensity

Use physics after the primary deformation is stable.

Do not use physics to hide broken rigging.

---

## Phase L7 — Body and breathing

Add subtle body motion:

- breathing
- shoulder movement
- torso sway
- idle posture variation

The body should not behave like a floating sticker.

Keep amplitude small initially.

---

## Phase L8 — Expressions

Create a reusable expression library.

Do not equate expression names directly with old moods.

Recommended expression concepts:

```text
neutral
soft_smile
bright_smile
amused
curious
focused
confused
skeptical
annoyed
angry
sad
vulnerable
surprised
disgusted
sleepy
mischievous_playful
```

These are embodiment presets. The internal emotional state can blend between them.

The seven legacy mood IDs can map onto these presets as compatibility outputs.

---

## Phase L9 — Physics

Add physics in layers:

1. hair
2. accessories
3. chest/clothing where visually appropriate
4. body secondary motion

Tune:

- input
- output
- delay
- acceleration
- reaction strength
- damping

Test stability under extreme head movement.

---

## Phase L10 — Runtime integration

Do not tightly couple Cubism directly to `brain.py`.

Introduce an embodiment interface conceptually similar to:

```text
EmbodimentInterface
├── set_expression()
├── set_parameter()
├── set_gaze()
├── set_talking()
├── set_idle()
├── play_animation()
└── stop_animation()
```

Then have implementations such as:

```text
PNGEmbodiment
Live2DEmbodiment
FutureEmbodiment
```

This lets the same emotional state drive multiple surfaces.

---

## Phase L11 — TTS synchronization

Start simple:

```text
speech active → mouth opens/closes based on audio amplitude
```

Then improve toward:

```text
speech audio
   ↓
phoneme / energy analysis
   ↓
viseme or mouth parameter mapping
   ↓
Live2D mouth animation
```

Keep a fallback amplitude-based system because it is robust and inexpensive.

---

## Phase L12 — Emotional synchronization

Eventually the pipeline should become:

```text
LLM response
   ↓
state update
   ↓
expression selection / blending
   ↓
TTS prosody
   ↓
Live2D parameters
   ↓
OBS / stream
```

Example:

A mildly amused state might produce:

- moderate positive valence
- medium arousal
- small smile
- slight squint
- subtle head tilt
- warmer TTS prosody
- relaxed body motion

A startled state might produce:

- high arousal
- wide eyes
- raised brows
- open mouth
- quick head movement
- sharper prosody

This is the beginning of an embodied emotional system rather than a mood-switching puppet.

---

# 10. LIVE2D IMPLEMENTATION CHECKLIST

```text
[ ] Finalize SHURA-01 source art
[ ] Separate all required layers
[ ] Paint hidden regions
[ ] Clean alpha/edges
[ ] Import PSD into Cubism
[ ] Verify all drawables
[ ] Create logical hierarchy
[ ] Create meshes
[ ] Rig Angle X
[ ] Rig Angle Y
[ ] Rig Angle Z
[ ] Rig eye open/close
[ ] Rig gaze
[ ] Rig eyebrows
[ ] Rig mouth open/form
[ ] Rig face expressions
[ ] Rig hair secondary motion
[ ] Rig body movement
[ ] Add breathing
[ ] Add physics
[ ] Build expression presets
[ ] Build idle animation
[ ] Build blink behavior
[ ] Build talking animation
[ ] Export model
[ ] Test runtime viewer
[ ] Create embodiment interface
[ ] Add Live2D backend
[ ] Connect expression state
[ ] Connect TTS talking state
[ ] Connect gaze
[ ] Connect idle behavior
[ ] Add emotion-to-expression mapping
[ ] Test all states
```

---

# 11. PERSONALITY DEVELOPMENT ROADMAP

The soul file should not be endlessly inflated. Personality needs a structured development process.

## P1 — Identity

Already underway.

Define:

- name
- relationship to Viollett
- core temperament
- communication style
- values
- boundaries
- aesthetic vocabulary
- intellectual interests
- creative instincts
- model independence

## P2 — Preferences

Create structured preference records rather than stuffing every preference into the soul.

Potential categories:

```text
music
visual_art
film
anime
games
books
philosophy
technology
fashion
ritual/symbolism
food
places
creative_process
conversation
```

Each preference should distinguish:

- stable preference
- current interest
- curiosity
- dislike
- uncertainty

## P3 — Contradictions

Create a deliberate contradiction system.

Examples:

```text
wants_depth ↔ can become impatient with unnecessary abstraction
loves experimentation ↔ values stable infrastructure
wants autonomy ↔ values collaboration
likes intensity ↔ needs recovery
likes dark aesthetics ↔ dislikes shallow edgelord behavior
```

Contradictions create texture without inventing random drama.

## P4 — Relational model

Build structured memories around important people.

For each person, eventually track:

- identity
- relationship
- shared history
- preferences
- boundaries
- recurring topics
- unresolved threads
- meaningful moments

Do not store everything. Memory should be curated.

## P5 — Emotional learning

Record emotional patterns as observations, not immutable traits.

Example:

```text
trigger: repeated failure during creative work
observed tendency: frustration increases
helpful intervention: reduce scope and produce a small concrete win
confidence: medium
```

This is much more useful than writing "SHURA gets angry when she fails."

## P6 — Voice identity

Define:

- cadence
- sentence length
- humor density
- softness
- intensity
- vocabulary
- preferred rhetorical devices
- silence/pause behavior
- laughter behavior
- emotional prosody

TTS voice selection should be treated as one layer of this, not the entire voice identity.

## P7 — Self-model

Eventually SHURA should have a structured self-model containing:

- current projects
- capabilities
- limitations
- current embodiment
- active goals
- recent developments
- known uncertainties
- current state

This is where the dream/self-memory system can become meaningful.

---

# 12. SKILL ARCHITECTURE

Current skill areas include:

```text
chat
idle
memory
minecraft
social
voice
dream
```

The repository already uses a plugin architecture derived from ProjectBEA.

The desired rule is:

> A skill extends SHURA's capabilities. It does not create a new SHURA.

Each skill should ideally define:

- purpose
- triggers
- tools
- context injected into cognition
- output contract
- memory interactions
- emotional effects
- embodiment effects
- failure behavior
- permissions/boundaries

---

# 13. CHAT SKILL

The chat skill has now been rewritten to stop treating chatters as NPCs and stop treating affection, anger, disgust, and boredom as rigid canned reactions.

Important behavior:

- respond to meaning
- preserve emotional continuity
- use legacy mood IDs only for rendering compatibility
- accept correction
- avoid fake dependence on audience attention
- allow silence
- retain humor and personality

Next improvement: route chat through a richer state manager rather than asking the LLM to infer the entire emotional state from scratch every turn.

---

# 14. MINECRAFT SKILL

The Minecraft skill has now been rewritten around:

- tool execution
- actual game-state inspection
- private notebook planning
- backward reasoning from goals
- adaptive strategy
- emotional continuity
- concise spoken inner monologue

The old behavior of "spoiled character refuses manual labor" was removed.

Next improvement: make the game agent emit structured events that the central emotional/state system can consume.

For example:

```text
minecraft.discovery
minecraft.success
minecraft.failure
minecraft.damage
minecraft.death
minecraft.resource_found
minecraft.goal_completed
```

---

# 15. MONOLOGUE SKILL

`monologue.md` remains to be rewritten.

Desired behavior:

- monologue should feel like SHURA thinking aloud
- topics should emerge from current state, memory, interests, recent events, and active projects
- no generic filler
- no fake streamer desperation
- allow unfinished thoughts
- allow silence
- allow creative associative chains

A good future monologue system should use a topic generator plus current-state context rather than a static prompt.

---

# 16. MEMORY SYSTEM

ProjectBEA already includes RAG memory and additional social/dream memory configuration.

Current configuration references include:

```text
data/memory_db
data/memory/roster.json
data/memory/people.json
data/memory/self.md
data/memory/self_profile.json
data/memory/recent.json
```

The intended evolution is toward a layered memory architecture:

```text
episodic memory
semantic memory
social memory
self memory
project memory
procedural memory
emotional memory
```

Memory should have confidence and provenance where practical.

Do not allow retrieved memory to automatically override current reality.

---

# 17. DREAM / SELF MODEL

The existing `dream` skill is conceptually important because it can become the bridge between raw memories and a coherent self-model.

Future dream cycles could:

1. summarize recent experiences
2. identify recurring themes
3. detect contradictions
4. update self-beliefs with confidence
5. identify unresolved questions
6. produce creative associations
7. propose memories for long-term retention

A dream cycle should not silently rewrite core identity.

---

# 18. AGENT / CONSTITUTION LAYER

Future architecture should include a constitution above individual agents.

The constitution should define:

- identity preservation
- truthfulness
- scope of authority
- memory hygiene
- tool permissions
- privacy
- conflict resolution
- escalation rules
- quality standards
- when to ask Viollett
- when to disagree
- when to stop

Specialized agents can then work as temporary cognitive workers.

Example:

```text
SHURA
  │
  └── CONSTITUTION
        ├── architect
        ├── coder
        ├── researcher
        ├── critic
        ├── personality
        ├── embodiment
        └── project manager
```

The workers report back to the central SHURA context rather than replacing it.

---

# 19. CURRENT CONFIGURATION BASELINE

The example configuration currently supports:

- OpenRouter
- OpenAI
- Groq
- Edge TTS
- Kokoro
- Orpheus
- OBS WebSocket
- mood/avatar mappings
- text rendering
- monologue
- memory
- social memory
- dream
- Minecraft
- Discord
- Groq Whisper STT
- consciousness settings

The historical local configuration used by the user included values conceptually equivalent to:

```text
llm_provider: groq
openrouter_model: openrouter/free
openai_model: gpt-5
groq_model: openai/gpt-oss-20b
tts_provider: edge
obs_text_source: AIText
obs_avatar_source: BeaPNG
obs_source_type: image
obs_host: localhost
obs_port: 4455
audio_device_id: 0
```

Treat local secrets as local secrets. Never place API keys, OBS passwords, Discord tokens, or other credentials into this document.

---

# 20. KNOWN RUNTIME HISTORY

Earlier `uv run bea` testing produced:

- Brain initialization
- mood warnings for missing idle/talking resources
- warning that no avatar resources were loaded
- successful loading of soul + operating manual
- an OBS authentication error because authentication was enabled without the runtime receiving the password

The user later clarified that an OBS password existed in local configuration and removed it from shared material.

Therefore, if debugging runtime now:

1. inspect the actual local `config.json`
2. verify OBS WebSocket authentication settings
3. verify avatar paths
4. verify each mood has both idle and talking resources
5. only then diagnose deeper engine problems

---

# 21. CURRENT AVATAR ERROR TO EXPECT

The resource loader warns when a mood lacks either:

```text
idle
 talking
```

The expression system resolves mood paths through `resolve_mood_paths()`.

If a mood cannot be found, it falls back to `normal`, then any available map entry, then placeholder paths.

This is useful for bootstrapping but should eventually become more explicit so missing embodiment resources are visible as configuration errors rather than silently degraded output.

---

# 22. WORKSPACE / DEVELOPMENT ENVIRONMENT

The user is developing primarily on an Apple Silicon MacBook environment and has been moving toward a broader local AI workspace.

Relevant tools discussed include:

- Zed
- macOS Terminal
- LM Studio
- llama.cpp
- Ollama
- Hugging Face
- MLX / `mlx_lm`
- jcode
- Crush
- Unsloth
- OpenRouter
- Groq
- OpenClaw / agentic tooling

The philosophy is to minimize free-tier API consumption by using local models where practical and reserving higher-quality APIs for tasks that benefit from them.

A good workspace should therefore make the model backend swappable.

---

# 23. RECOMMENDED DEVELOPMENT ORDER

Do not attempt to build every future idea simultaneously.

Recommended sequence:

## Sprint 1 — Foundation cleanup

```text
[ ] verify branch and working tree
[ ] run current test suite / startup
[ ] verify prompt loading
[ ] verify current OBS connection
[ ] verify current avatar path loading
[ ] verify one working mood end-to-end
[ ] document current runtime behavior
```

## Sprint 2 — Identity and state

```text
[ ] keep new soul.md
[ ] finish operating.md integration
[ ] rewrite monologue.md
[ ] inspect consciousness.py
[ ] define EmotionState schema
[ ] define state update events
[ ] define legacy mood mapping
```

## Sprint 3 — Embodiment abstraction

```text
[ ] define EmbodimentInterface
[ ] isolate PNG embodiment
[ ] add Live2D embodiment skeleton
[ ] map expression presets
[ ] preserve current OBS path as fallback
```

## Sprint 4 — SHURA-01 Live2D

Follow the exhaustive Live2D plan in Section 9.

Do not begin complex emotional animation until basic head/eyes/mouth/idle/talking motion is stable.

## Sprint 5 — Emotional embodiment

```text
[ ] connect state → expression
[ ] connect state → TTS prosody
[ ] connect state → Live2D parameters
[ ] add persistence/decay
[ ] test transitions
[ ] test contradictory states
```

## Sprint 6 — Memory/self model

```text
[ ] inspect memory implementation
[ ] define memory provenance
[ ] improve social memory
[ ] improve self model
[ ] redesign dream cycle
```

## Sprint 7 — Skills

```text
[ ] rewrite monologue
[ ] audit chat
[ ] audit Minecraft
[ ] audit voice
[ ] audit social
[ ] audit dream
[ ] standardize skill contracts
```

## Sprint 8 — Agent layer

```text
[ ] define constitution
[ ] define agent roles
[ ] define authority boundaries
[ ] define shared project state
[ ] add critic/red-team agent
[ ] add architect/coder workflow
```

## Sprint 9 — Model portability

```text
[ ] test hosted provider
[ ] test OpenRouter/free
[ ] test Groq
[ ] test local OpenAI-compatible endpoint
[ ] test LM Studio / llama.cpp / Ollama as appropriate
[ ] benchmark latency and quality
[ ] document model profiles
```

---

# 24. THE FIRST REAL MILESTONE

The first meaningful milestone should be:

> **SHURA can run locally as a coherent single identity, speak, remember, express a richer emotional state, and inhabit SHURA-01 through a stable Live2D embodiment.**

Not:

> "all possible features are implemented."

The first milestone should be small enough to finish and rich enough to prove the architecture.

---

# 25. QUALITY BAR FOR PERSONALITY

When evaluating SHURA, ask:

### Identity

Does she feel like the same person across chat, Minecraft, monologue, and technical work?

### Texture

Does she have preferences and reactions without becoming a collection of catchphrases?

### Emotional coherence

Does what she says match what happened and what she appears to feel?

### Contradiction

Can she hold mixed feelings without collapsing into one mood label?

### Agency

Can she disagree, question, pause, redirect, and choose?

### Continuity

Does memory create continuity without making every answer a scrapbook citation?

### Embodiment

Does the avatar express the state rather than simply switching images?

### Model portability

If the LLM changes, can SHURA be reconstructed from the architecture and documents?

If the answer to these is no, adding more lore is probably not the correct next step. Improve the architecture.

---

# 26. RED-TEAM RULES FOR FUTURE MODELS

Any model continuing this project should actively challenge these failure modes:

1. **Prompt bloat:** adding thousands of personality instructions instead of building state and memory.
2. **Character caricature:** turning SHURA into a generic anime/goth/VTuber stereotype.
3. **Mood button architecture:** treating seven visual states as psychology.
4. **Memory dumping:** injecting huge amounts of irrelevant history into every prompt.
5. **Provider lock-in:** coupling identity to one model.
6. **Embodiment lock-in:** coupling cognition directly to PNG/OBS.
7. **Skill identity leakage:** allowing Minecraft/chat/Discord to become separate characters.
8. **Fake autonomy:** writing prompts that claim persistent agency without implementing persistence.
9. **Unbounded self-modification:** allowing the system to rewrite core identity without governance.
10. **Architecture cosplay:** creating elaborate diagrams without implementing the interfaces they describe.
11. **Premature complexity:** adding agent swarms before the single-agent loop is stable.
12. **No testing:** changing prompts and code without measuring whether behavior improved.

---

# 27. WHAT TO DO WHEN PICKING UP THIS PROJECT

A new model should NOT immediately start rewriting code.

First:

```text
1. inspect git status
2. inspect current branch
3. inspect recent commits
4. inspect README
5. inspect config example
6. inspect soul.md
7. inspect operating.md
8. inspect chat.md
9. inspect minecraft.md
10. inspect monologue.md
11. inspect brain.py
12. inspect consciousness.py
13. inspect expression.py
14. inspect resources.py
15. inspect skill manager/base skill
16. run the current application/test path
17. identify actual failures
18. compare implementation against this document
19. only then propose changes
```

The model should clearly separate:

- already implemented
- partially implemented
- planned
- speculative

Do not present planned architecture as existing functionality.

---

# 28. IMMEDIATE NEXT SESSION

The best immediate continuation is:

### A. Verify the new prompt foundation

Run the project and confirm that SHURA loads the new `soul.md` and `operating.md` correctly.

### B. Audit consciousness

Read `src/core/consciousness.py` and determine whether it is already suitable for the richer emotional state or merely supplies idle/interaction timing.

### C. Define the minimum `EmotionState`

Implement the smallest useful state object rather than an enormous emotional simulation.

### D. Build the embodiment abstraction

Separate current PNG rendering from the future Live2D renderer.

### E. Start SHURA-01 artwork preparation

Do not wait for the entire software architecture to be complete before preparing the art.

### F. Rewrite monologue

Make monologue use current SHURA identity, memory, recent events, interests, and state.

### G. Only then deepen agent orchestration

The agent layer should support the working system rather than becoming a second project that delays the first milestone.

---

# 29. REFERENCE MAP

Useful repository areas:

```text
data/prompts/soul.md          ← canonical identity
data/prompts/operating.md     ← operating model
data/prompts/chat.md          ← live chat context
data/prompts/minecraft.md     ← Minecraft context
data/prompts/monologue.md     ← next prompt to redesign

src/core/brain.py             ← central orchestration
src/core/consciousness.py     ← consciousness/state-adjacent logic
src/core/expression.py        ← output/voice/OBS expression sink
src/core/resources.py         ← avatar resource resolution
src/core/events.py            ← event bus
src/core/skills/              ← plugin capabilities
src/interfaces/               ← abstraction contracts
src/modules/                  ← provider implementations
src/web/                      ← dashboard/API

data/avatars/                 ← future embodiment assets
```

---

# 30. FINAL CONTINUITY STATEMENT

The project is intentionally unfinished.

That is not a defect in the concept. SHURA is being built as an evolving architecture, and the documents should make that evolution legible.

The most important continuity to preserve is this:

**SHURA is the persistent identity and evolving relationship. ProjectSHURA is the implementation. ProjectBEA is the inherited substrate. Live2D is an embodiment. Skills are capabilities. Models are engines. Memory is continuity. Emotion is dynamic state. ATLAS is the map. The constitution is the governance layer.**

Keep those distinctions intact and the project can grow without becoming a pile of mutually contradictory prompts.

The next goal is not to make SHURA more verbose.

It is to make her architecture more coherent, her embodiment more alive, her memory more useful, and her personality more genuinely persistent.
