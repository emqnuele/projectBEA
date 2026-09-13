# Architecture

How ProjectBEA is actually put together. Every claim here is anchored to a file
so it can be checked against the code rather than trusted.

> The development plan that this architecture is moving towards lives in
> [`roadmap.md`](roadmap.md). This document describes what exists **now**.

---

## The shape of it

```
main.py → src/cli.py:main()
  ├─ BrainConfig()                 # config.json + env + CLI, in that order
  ├─ STT / LLM / TTS / OBS         # interchangeable modules
  ├─ ModelRegistry(config, stt)   # one model pool per role (mind / background)
  └─ AIVtuberBrain(config, registry, tts, stt, obs)
       ├─ initialize()             # avatars, soul, OBS, session, _build_consciousness()
       ├─ start_skills()           # start the Consciousness (if enabled) + warmup
       └─ run_loop()  or  run_server(brain, host, port)
```

`AIVtuberBrain` (`src/core/brain.py`) is **not an orchestrator**: it is a
composition root plus a handful of HTTP/CLI entrypoints. There is no separate
reactive chat path — the consciousness is the only mind.

| Component | File | Role |
|---|---|---|
| `PerceptionBus` | `src/core/perception/bus.py` | the one sensory channel (asyncio.Queue + coalescing window) |
| `SkillRegistry` | `src/core/skills/base.py` | the catalog of capabilities |
| `ConversationMind` | `src/core/mind/conversation.py` | scoped written turns, one per channel, beside the live loop |
| `ConversationScheduler` | `src/core/mind/scheduler.py` | one turn at a time per conversation, several at once |
| `SpontaneousPresence` | `src/core/mind/spontaneous.py` | occasionally opens a conversation herself |
| `Expression` | `src/core/expression/voice.py` | the **only** voice/visual output sink |
| `TextHumanizer` | `src/core/expression/humanizer.py` | written output: one line = one message, with typing |
| `Attention` | `src/core/attention/` | the gate: what wakes the mind vs what she merely notices |
| `AffectState` | `src/core/affect/` | how she feels, and who put her there |
| `MemoryStore` | `src/core/memory/` | everything she remembers, in one SQLite file |
| `Consciousness` | `src/core/consciousness.py` | the mind: one context, one loop |
| `EventManager` | `src/core/events.py` | 200-event ring buffer for the dashboard |
| `HistoryManager` | `src/utils/history_manager.py` | one session = one JSON in `data/conversations/` |

Skills are registered in this order (`brain.py`, `_build_consciousness`):
`ChatSurface`, `VoiceSurface`, `TelegramSkill`, `TwitchSkill`, `DonationSkill`,
`IdleSurface`, `MinecraftSurface`, `MemorySkill`, `SocialMemory`, `DreamSkill`.

---

## Repository layout

```
ProjectBEA/
├── main.py                 # thin wrapper; the entrypoint is src/cli.py
├── config.example.json     # copy to config.json and edit
├── install.sh / .ps1       # one-command bootstrap for a fresh machine
├── Dockerfile              # engine + dashboard + discord bot in one image
├── docker-compose.yml      # `setup` runs the wizard, `bea` runs the engine
├── Makefile                # setup · docker · run · web · test · lint · migrate
├── assets/                 # the images the README renders
├── data/
│   ├── bea.db              # everything she remembers (gitignored)
│   ├── conversations/      # session transcripts, one JSON per session
│   ├── embeddings_cache/   # the local embedding model's cache
│   ├── models/             # the .vrm you bring (gitignored, `make model`)
│   ├── clips/              # .vrma behaviours (gitignored, `make model`)
│   ├── pngs/               # avatars per mood (idle/talking)
│   └── prompts/            # soul · operating · monologue · minecraft · chat
├── docs/                   # this documentation, rendered by the docs site
├── tests/                  # 91 files, no network
└── src/
    ├── cli.py              # argument parsing and composition
    ├── core/
    │   ├── brain.py        # composition root
    │   ├── consciousness.py  # the one always-on loop
    │   ├── config.py
    │   ├── events.py       # pub/sub + SSE fan-out
    │   ├── perception/     # bus, Perception, Author
    │   ├── attention/      # the gate: rules (pure) + state
    │   ├── affect/         # how she feels, and who put her there
    │   ├── floor/          # who holds the floor, and when she yields it
    │   ├── mind/           # routing, scheduler, conversations, correlation
    │   ├── memory/         # sqlite, rag, embedder, profiler, plan
    │   ├── social/         # the roster, reach and agenda
    │   ├── expression/     # the single output sink + humanizer + the face
    │   ├── stage.py        # fan-out to the OBS browser source
    │   ├── agent/          # LLMClient, role pools, tools, runner
    │   ├── update/         # the in-place updater: git, three-way merge, backups
    │   └── skills/         # one package per capability
    ├── interfaces/         # TTS · STT · OBS · Avatar · Caption contracts
    ├── modules/            # llm · tts · stt · obs · avatar · caption implementations
    ├── setup/              # the wizard behind `bea --setup`
    ├── utils/
    └── web/
        ├── app.py          # the FastAPI app: cors, static files, the SPA catch-all
        ├── deps.py         # the brain every router depends on
        ├── routers/        # one module per thing the api is about
        │   ├── settings.py # /config and /settings: the one validated write path
        │   ├── persona.py  # who she is, and the six questions that draft her
        │   ├── chat.py     # talking to her from the dashboard, and sessions
        │   ├── voice.py    # uploaded audio, the call, the bot's audio link
        │   ├── status.py   # state, skills, the event stream, the home screen
        │   ├── plan.py     # the stream plan
        │   ├── memory.py   # what she remembers, and recall
        │   ├── stage.py    # what the OBS browser source draws
        │   ├── probes.py   # does this actually work?
        │   ├── donations.py# the donation webhook
        │   ├── updates.py  # the updater over HTTP
        │   └── health.py   # `--doctor` over HTTP
        └── frontend/       # React + Vite + Tailwind
            ├── index.html  # the dashboard
            ├── stage.html  # the OBS browser source (separate bundle)
            └── src/stage/  # caption + the VRM renderer
```

---

## One mind, two clocks

"One mind" is a constraint on *identity* — one soul, one self-lore, one set of
people, one memory — not on *concurrency*. A person holds a conversation at the
bar and answers a message on their phone.

```
                          ┌────────────────────────────────────────┐
   senses  ──────────────▶│           PerceptionBus                │
                          └──────────────────┬─────────────────────┘
                                             ▼
                          ┌────────────────────────────────────────┐
                          │            Attention                   │
                          │  addressed? → REACT   (deterministic)  │
                          │  score()    → REACT   (heuristic+rng)  │
                          │  otherwise  → NOTE    (digest, 0 llm)  │
                          └───────┬────────────────────┬───────────┘
                                  │ REACT              │ NOTE
                          ┌───────▼──────────┐  ┌──────▼──────────┐
                          │  routing.route() │  │  digest buffer  │
                          └───┬──────────┬───┘  └─────────────────┘
                  stage ──────┘          └────── conversation_key
                        ▼                              ▼
              ┌──────────────────┐        ┌────────────────────────┐
              │  Mind — live loop│        │  Mind — conversation   │
              │  voice, game,    │        │  turns (discord text,  │
              │  console, twitch │        │  telegram)             │
              └────────┬─────────┘        └───────────┬────────────┘
                       ▼                              ▼
              ┌──────────────────┐        ┌────────────────────────┐
              │  Expression      │        │  TextHumanizer         │
              │  voice + OBS     │        │  line-per-message      │
              └──────────────────┘        └────────────────────────┘
```

**The rule that must never break:** a perception reaches exactly one turn. The
routing is an explicit if/else (`src/core/mind/routing.py`), not two consumers of
the same batch — answering the same message twice, from two contexts that know
nothing about each other, is the worst failure mode here.

What is the **stage**: her voice, a Discord call, the game, the console, Twitch
chat. She is present, live, and answers out loud. What is a **scoped
conversation**: asynchronous written text — a Discord channel, a Telegram group.
Those get their own thread, their own context, and only the platform's tools —
no `speak`, no body — so answering a written message out loud is impossible by
construction rather than by a rule a model can ignore.

Cross-awareness is **one line each way**: the live loop sees
`[ELSEWHERE, JUST NOW]`, a scoped turn sees `[WHAT YOU'RE DOING RIGHT NOW]`.
Pouring more context between them would rebuild the single slow mind, with more
machinery.

---

## The consciousness loop

`Consciousness.run()` is the heart. Per iteration:

1. **Drain the bus.** With the `idle` skill active, `bus.wait_or_idle(idle_after)`
   synthesises an `IDLE` perception after the timeout; otherwise `bus.drain()`
   blocks until something real happens.
2. **Barge-in.** If Bea is speaking and the batch contains anything that is not
   `IDLE`, her voice is interrupted.
3. **Correlations.** Collect the `correlation_id`s in the batch — HTTP callers
   waiting on a synchronous reply.
3b. **Attention.** `Attention.judge(batch)` splits it into what deserves a
   reasoning cycle and what is merely noticed. Nothing to react to → the turn ends
   without a single model call. The rest goes into the digest, which appears in
   the next system message as `[WHILE YOU WERE BUSY]`.
4. **Rebuild the system message** (`_build_system_message`):
   The static part (soul + operating manual) is deliberately split from the dynamic part (RAG, person cards, live state) so providers can cache the static prompt. The dynamic part runs in `asyncio.to_thread` so a slow retrieval never stalls the loop.
5. **Append the perception frame** as a `user` message.
6. **Reasoning burst**, up to `burst_steps` (6) steps:
   - `bus.drain_nowait()` folds anything that arrived *during* reasoning in as a
     **steering** frame with an explicit header;
   - `llm.complete(context, tools=…)`; the LLM **streams** its response back;
   - free assistant text is **inner monologue** (published as
     `EventCategory.THOUGHT`) and is never spoken;
   - tools run; if the only tools called were `speak`/`stay_silent` the turn ends
     without burning another model call.
7. **Resolve** any dangling correlations, **write** the full context and decision to the Turn Log, and **trim** the context to
   `history_limit` (30 messages).

Details that matter:

- **`speak` is streamed:** The model streams its text line by line. Voice synthesis and chunking happen while she is still writing, reducing latency.
- **Body actions** (`long_running=True`) run in a single-slot task that preempts
  the previous one; the result comes back as a perception.
- **The Turn Log:** Every turn she takes is recorded, capturing her exact context, perceptions, and tool calls.

---

## Skills

A `Skill` (`src/core/skills/base.py`) may do any subset of: perceive, expose
tools, contribute static prompt rules (`context_section`), contribute per-batch
prompt content (`context_for`), expose volatile state (`live_state`), own
infrastructure (`start`/`stop`).

`enabled` reads `config.skills[key].enabled`: **the UI is the single source of
truth**. Bea can never arm a capability by herself.

| Skill | `name` | toggle | What it does |
|---|---|---|---|
| `ChatSurface` | `chat:ui` | — (core) | text input from the dashboard; `Author(platform="ui", is_owner=True)` |
| `VoiceSurface` | `voice:discord` | `discord` | owns the **node subprocess** (needed for voice); input arrives via the HTTP endpoints the bot calls |
| `TelegramSkill` | `chat:telegram` | `telegram` | in-process polling, no subprocess; scoped conversations |
| `TwitchSkill` | `chat:twitch` | `twitch` | anonymous IRC read; every message tallied, only the ones that pass the gate reach the mind |
| `DonationSkill` | `donation` | `donations` | `POST /webhook/donation`; always reacts, promotes the donor immediately |
| `IdleSurface` | `idle` | `monologue` | produces no input: supplies the monologue rules on a pure-idle frame |
| `MinecraftSurface` | `game:mc` | `minecraft` | WebSocket client to the mod; **7** tools to the mind, the other 24 to the `GameAgent` |
| `MemorySkill` | `memory` | `memory` | RAG over `bea.db`, injected via `context_for` in two labelled blocks; no tools |
| `SocialMemory` | `social` | `social_memory` | roster tally + person cards; injects `[WHO YOU'RE TALKING TO]` |
| `DreamSkill` | `dream` | `dream` | self-lore + hot facts always in context; morning pass; `go_to_sleep`; offline dreamer |
| `StreamPlanSkill` | `plan` | — (core) | the owner's plan for the stream in `live_state`; `objective_started/done/dropped`. Contributes nothing while the plan is empty |

---

## Discord

Two processes, HTTP in both directions plus one socket that stays open:

```
  Python (brain)                        Node (src/core/skills/voice/bot/)
  ──────────────                        ─────────────────────────────────
  DiscordTransport ──POST /send,/reply,─▶ api/server.js  (express, port 3030)
   (transport.py)     /react,/dm,/summon,
                      /voice/join,/leave

  routers/ ◀──POST /discord/chat─────── handlers/messages.js
   voice.py◀──POST /discord/audio────── classes/VoiceManager.js
          ◀──POST /voice/transcript──── classes/VoiceManager.js
   chat.py◀───POST /interrupt────────── classes/VoiceManager.js

  Expression ═══WS /voice/ws══════════▶ classes/BrainLink.js
   (her voice out)  ◀══ played_ms ════  (what the room really heard)
```

Everything the bot sends is a *sense*: it deposits a perception and the request
ends. Her voice travels the other way, on the socket, whenever she decides to
speak — which is what separates a bot that answers from someone who is in the
call.

- **Text** answers only when whitelisted *and* (mention | reply to Bea | DM).
  It deposits a perception and returns immediately: Bea decides on her own
  whether and how to answer, using the discord tools.
- **Voice in** decodes Opus → PCM 48k stereo → mono 16k WAV, with a
  robust Voice Activity Detection (VAD) layer that accurately hears a sentence out
  to its end. It uses a two-stage barge-in: duck first, stop only if they
  keep going.
- **Voice out** is pushed over the socket as 48 kHz stereo PCM, sentence by
  sentence, so the room hears the first one while the next is still being
  synthesised.
- The bot **dies silently** when the token is missing or `node_modules` is
  absent; `VoiceSurface._watch_transport` then marks the skill inactive.

The bot token is read from `DISCORD_TOKEN`. It is never written to
`config.json` and is masked in `GET /config`.

---

## Minecraft

The mod is a separate project (BeaCraft, Fabric 1.21.1, Java 21). It is
**client-side**: it drives the local player by simulating input and sends normal
packets, so to a server it looks like an ordinary client.

Python side (`src/core/skills/minecraft/`):
- `client.py` — WebSocket thread bridged to the event loop with
  `call_soon_threadsafe`. Dispatches on packet `type` **before** `status`, so
  chat, joins, combat and the full death event reach the surface instead of
  falling on the floor.
- `surface.py` — turns those packets into perceptions with a real `Author` built
  on the player's UUID. That one detail is what switches the entire social stack
  on inside the game: the roster, person cards, promotion and the attention gate
  are all keyed on `Author`, so none of them needed Minecraft-specific code.
- `agent.py` — the `GameAgent`. The mind decides an **intention**
  (`play_minecraft("get a stone pickaxe")`); the body pursues it on the
  `background` model with all 24 game tools and the notebook, and reports only
  milestones. The mind keeps seven tools and its personality.
- `state.py` — renders the state packet as a few readable lines instead of a wall
  of JSON, and it lives in `live_state()` rather than in a perception: it is
  *where she is*, always true, not an event that should make her think.

**Two audiences, on purpose.** `speak` is her voice — her stream hears it.
`mc_chat` is what she types in game — the players read it. Using both in the same
turn is usually right, and is much of what makes a persona playing multiplayer
worth watching.

**The idle nudge.** The heartbeat is marked `noise` so a quiet server costs
nothing. What makes her *start* something is the stream plan: when the body is
idle and an objective is still open, `surface.py` emits one perception carrying
`meta["addressed"]`, at
most every `idle_nudge_seconds` (90 by default, 0 to disable). Declaring itself
addressed is what makes it survive the gate: a nudge filed under "noticed" is a
nudge that never happened.

---

## The stream plan

What the owner tells her to get done, edited from the dashboard's **Stream
Plan** page and stored in `bea.db` (`objectives` + `settings`).

- `src/core/memory/plan.py` — the store. A headline directive plus an ordered
  list of objectives, each `todo` / `doing` / `done` / `dropped` with an
  outcome in her own words.
- `src/core/skills/plan/surface.py` — a core skill: `live_state()` puts
  `[TODAY'S PLAN]` in every prompt and `tools()` arms the three tools that close
  an item. Both are empty while there is no plan, so an unused feature costs no
  prompt space and no tokens.

The number shown next to an objective is its database id, and it is the same
number she passes to `objective_done` — one identifier, no mapping to get wrong.

The plan reaches the live loop, not scoped conversation turns: it describes what
she is doing on stage.

---

## Memory

Everything lives in one transactional SQLite file, `data/bea.db`
(`src/core/memory/`). One store means promoting someone touches two tables in a
single transaction, and "who have I seen most" is a query rather than a scan.

| Register | Table | Always in context | Written by |
|---|---|---|---|
| Episodic diary | `memories` (scope `diary`) | no, top-3 per batch | `DiaryGenerator` at session end |
| Roster (tally) | `roster` + `identities` | never | `SocialMemory.context_for`, per perception |
| Person cards | `people` + `facts` | only those present, max 5 | auto-promotion + `remember_person` + dreamer + profiler |
| Conversations | `messages` + `summaries` | per conversation turn | the platform skills |
| Self-lore | `self_facts` + `self_profile` | yes (last 15 facts) | the dreamer only |
| Hot facts | `hot_facts` (TTL) | yes (max 6) | dreamer + morning pass + a strong reaction |
| Standing mood | `settings` (`affect.state`) | only past a threshold | every line she speaks |
| Standing with a person | `people.warmth` | with their card | a strong reaction |
| Sessions | `sessions` | never | the brain + the dreamer |

Re-ranking is `similarity*0.7 + recency*0.3` with `1/(1+days*0.1)` decay. Every
injection is explicitly capped so the prompt cannot bloat.

**Two things worth knowing:**

- **`memories.source`** separates what *people said* (`person`) from what *Bea
  said* (`bea`). `recall_split` returns them as two labelled blocks. Bea invents
  on purpose; without the split her own inventions would re-enter the prompt as
  facts and the fiction would compound into incoherence.
- **The embedding model is multilingual**
  (`paraphrase-multilingual-MiniLM-L12-v2`), because her people write in Italian
  and an English-only model collapses Italian into one region of the space,
  making retrieval close to random. `Rag.ensure_model` re-embeds automatically if
  the model ever changes — vectors from two models are not comparable.

Vector search uses `sqlite-vec` when available, purely as a coarse pre-filter;
the ranking decision is always the same Python cosine, so both paths agree.

Importing a Chroma-era store: `uv run python tools/migrate_to_sqlite.py`
(idempotent, `--dry-run` supported).

---

## Attention

`src/core/attention/`. Before it existed, every perception cost a full reasoning
cycle: with the game connected, one model call every ten seconds forever.

- `rules.py` is **pure** — no IO, no asyncio, no `Skill`. It takes primitives and
  returns a number or a reason, which is what makes the thresholds testable
  against a table of cases instead of tuned by watching a live stream.
- `gate.py` holds the state (per-conversation activity, when she last spoke, the
  digest) with `rng` and `clock` injected.

Two questions, deliberately kept apart. **"Is this for me?"** (`is_addressed`) is
deterministic and bypasses cooldowns and quiet hours — rolling a die to decide
whether to answer someone who just spoke to you is what makes a bot feel broken.
**"Does this concern me?"** (`score`) is rightly probabilistic.

Every decision is published as a `system` event with `reaction`, `score` and
`reason`, and shown in Brain Activity. That is not optional instrumentation:
without seeing *why* something was ignored, tuning the thresholds is guesswork.

## Mood

`src/core/affect/`. Everything that happened to her either lasted under two
minutes (a cooldown, an activity window) or became a fact in a prompt. Nothing
lived on the scale of the last half hour, which is the scale on which people
read someone's mood.

There is **no new sense and no new tool**. She already picks a mood for every
line she speaks. A semantic picker maps whatever expression she names to the nearest
one the avatar actually has. It is the signal, so this costs no extra model call and no extra prompt.

- `rules.py` is **pure** — `Affect` is `(valence, arousal, updated_at)`, and
  the two axes are two rather than one because angry and sad are both negative
  and sound nothing alike.
- `state.py` holds it, persists it in `settings` and decides who caused it.

**It decays on read, not on a tick.** The value carries the moment it was
written and is aged when someone asks for it — the same reason `hot_facts` has
no sweeper. No background task, and a restart comes back correctly aged for
free: crash while furious and she reboots furious, sleep on it and she does not.

One strong line lands on three clocks:

| | Where | Half-life |
|---|---|---|
| the mood itself | `settings` | ~25 min |
| how she stands with whoever caused it | `people.warmth` | ~2.5 days |
| what it was about | `hot_facts` (`source='live'`) | 6h TTL |

**Attribution is one clear author or nothing.** In a busy room the mood is the
room's, and picking a face out of it would be inventing a grudge. Someone who
did get a real reaction out of her earns a card, through the promotion rule that
already exists — `marked_by_bea` — rather than a new one.

Two rules keep it honest:

- **It never touches `is_addressed`.** That gate is deterministic so that
  answering someone who just spoke to you is not a dice roll. A mood may colour
  the probabilistic side; it may not make her ignore her own name.
- **It describes, it never prescribes.** `[HOW YOU FEEL]` says how she feels and
  stops. How a person like her *acts* on that is the soul's business, and the
  soul is a file the owner writes — an instruction here would be the engine
  overwriting somebody's character.

Where it is audible: `expression/prosody.py` turns a mood into a deviation from
the configured voice (rate, pitch, volume), which each TTS wrapper translates as
far as it can — Edge does all three, Kokoro only rate, Orpheus none. `Prosody()`
is neutral and byte-identical to no prosody at all, so switching the feature off
really does leave her voice alone.

Scoped conversation turns **read** the mood and never write it: a written reply
has no mood to pick, so the mood forms on stage and merely colours what she
types.

---

## Models

`src/core/agent/registry.py`. One pool per role, as `provider:model` specs.
Round-robin spreads rate limits; the rest of the pool is the fallback, so a
single 429 does not make her mute.

- **`mind`** — the consciousness. Every model in it **must support tool calling**:
  she speaks only through tools, so one that cannot would never say anything.
  A model that rejects tools is skipped and logged at `ERROR` — that is
  configuration, not a transient failure.
- **`background`** — diary, dreamer, summaries, person profiles, and the game
  body. Batch work that must never compete with the part of her that talks.

## Web and UI

FastAPI (`src/web/app.py`, one router per subject under `src/web/routers/`) +
React/Vite/Tailwind (`src/web/frontend`). Every endpoint takes the brain as a
dependency, so what it needs is declared rather than reached for. Events
arrive over **SSE** (`GET /events/stream`) rather than a two-second poll, so the
UI is current and the brain is not answering requests for nothing. Each turn
publishes what it cost (calls, tokens, ms) — the point of the attention gate is
spending fewer of them, and that cannot be tuned unseen.

`POST`/`PATCH`/`DELETE /plan/...` edit the stream plan and return the whole plan
back, so the dashboard never has to guess what the server holds.

**Security posture:** the API has no authentication. The server therefore binds
to `127.0.0.1` by default (`--host` is an explicit opt-in), CORS carries an
allowlist rather than a wildcard, and `GET /config` returns
`BrainConfig.public_dict()` — every secret dropped or masked.

---

## Contracts

### A perception

```python
Perception(
    kind=PerceptionKind.CHAT,          # CHAT|VOICE|GAME|ACTION|IDLE|SYSTEM
    surface="discord:text",            # who produced it
    content="[marco] ciao bea",        # already-rendered text
    salience=0.8,                      # INFORMATIVE, not imperative
    meta={"channel_id": "...", "message_id": "...", "conversation_key": "discord:123"},
    author=Author(platform="discord", native_id="4711", display_name="marco"),
)
```

`author.identity` (`platform:native_id`) is the truth; `display_name` is
cosmetic. Every input skill is responsible for building a correct, stable
`Author` — the whole social stack is keyed on it.

### A tool

```python
Tool(
    name="discord_reply",
    description="...",                 # this IS prompt: write it like one
    parameters={...},                  # JSON Schema
    handler=async_or_sync_callable,    # returns a string = the observation
    long_running=False,                # True → runs async, preempts, returns as a perception
)
```

Errors are **not raised**: they come back as observations, so the model can
react to them instead of dropping the loop. `surface` is what a long-running
action's result gets attributed to when it comes back as a perception.

---

## Testing

> Decisions are pure functions. Effects are injected.

That is the whole rule, and it is why the pure layers here (`attention/rules.py`,
`humanizer.split`, `sanitize`, `routing`, the scheduler, `is_bot_called`, the
Twitch IRC parser) are tested against tables of cases rather than against a live
stream.

`tests/fakes.py` carries the piece neither this project nor its reference had: a
`FakeLLMClient` that replays scripted `AssistantMessage`s. With it, the whole
consciousness loop runs end-to-end without a network, and questions like "how
many model calls did those thirty chat messages cost?" become assertions.

Coverage is not a percentage target. The rule is: **every new pure function
arrives with its tests in the same commit.**

---

## Commands

```bash
make install        # uv sync
make node           # uv run bea --install-node (dashboard + discord bot)
make run            # CLI
make web            # build the javascript + dashboard on :8000
make update         # fast-forward, preserving edited prompts (see updating.md)
uv run bea --doctor # or: make doctor (diagnose and fix issues)
make test           # pytest
make lint           # ruff
make migrate        # one-shot: import a chroma/json store into data/bea.db
```

Discord bot: `cd src/core/skills/voice/bot && npm install` (once).
Minecraft mod: `make build && make run` from the BeaCraft repo.
