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
| `Expression` | `src/core/expression/voice.py` | the **only** voice/visual output sink |
| `TextHumanizer` | `src/core/expression/humanizer.py` | written output: one line = one message, with typing |
| `Attention` | `src/core/attention/` | the gate: what wakes the mind vs what she merely notices |
| `MemoryStore` | `src/core/memory/` | everything she remembers, in one SQLite file |
| `Consciousness` | `src/core/consciousness.py` | the mind: one context, one loop |
| `EventManager` | `src/core/events.py` | 200-event ring buffer for the dashboard |
| `HistoryManager` | `src/utils/history_manager.py` | one session = one JSON in `data/conversations/` |

Skills are registered in this order (`brain.py`, `_build_consciousness`):
`ChatSurface`, `VoiceSurface`, `IdleSurface`, `MinecraftSurface`, `MemorySkill`,
`SocialMemory`, `DreamSkill`.

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
   `CURRENT DATE + soul + operating manual + context_section of every active
   skill + live_state + dynamic_context(batch)`. The dynamic part (RAG, person
   cards) runs in `asyncio.to_thread` so a slow retrieval never stalls the loop.
5. **Append the perception frame** as a `user` message.
6. **Reasoning burst**, up to `burst_steps` (6) steps:
   - `bus.drain_nowait()` folds anything that arrived *during* reasoning in as a
     **steering** frame with an explicit header;
   - `llm.complete(context, tools=…)`;
   - free assistant text is **inner monologue** (published as
     `EventCategory.THOUGHT`) and is never spoken;
   - tools run; if the only tools called were `speak`/`stay_silent` the turn ends
     without burning another model call.
7. **Resolve** any dangling correlations and **trim** the context to
   `history_limit` (30 messages).

Details that matter:

- **`speak` is non-blocking** locally (`create_task`), and blocking on the
  `discord` route because it must hand back the WAV bytes.
- **Body actions** (`long_running=True`) run in a single-slot task that preempts
  the previous one; the result comes back as a perception.

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
| `VoiceSurface` | `voice:discord` | `discord` | owns the **node subprocess**; 7 tools; input arrives via the HTTP endpoints the bot calls |
| `IdleSurface` | `idle` | `monologue` | produces no input: supplies the monologue rules on a pure-idle frame |
| `MinecraftSurface` | `game:mc` | `minecraft` | WebSocket client to the mod; 24 tools + `update_notebook`; perception loop |
| `MemorySkill` | `memory` | `memory` | RAG over `bea.db`, injected via `context_for` in two labelled blocks; no tools |
| `SocialMemory` | `social` | `social_memory` | roster tally + person cards; injects `[WHO YOU'RE TALKING TO]` |
| `DreamSkill` | `dream` | `dream` | self-lore + hot facts always in context; morning pass; `go_to_sleep`; offline dreamer |

---

## Discord

Two processes talking HTTP in both directions:

```
  Python (brain)                        Node (src/core/skills/voice/bot/)
  ──────────────                        ─────────────────────────────────
  DiscordTransport ──POST /send,/reply,─▶ api/server.js  (express, port 3030)
   (transport.py)     /react,/dm,/summon,
                      /voice/join,/leave

  app.py  ◀──POST /discord/chat──────── handlers/messages.js
          ◀──POST /discord/audio─────── classes/VoiceManager.js
          ◀──POST /voice/transcript──── classes/VoiceManager.js
          ◀──POST /interrupt─────────── classes/VoiceManager.js
```

- **Text** answers only when whitelisted *and* (mention | reply to Bea | DM).
  It deposits a perception and returns immediately: Bea decides on her own
  whether and how to answer, using the discord tools.
- **Voice** decodes Opus → PCM 48k stereo → mono 16k WAV, with an RMS-threshold
  VAD and a sustained-speech interrupt.
- The bot **dies silently** when the token is missing or `node_modules` is
  absent; `VoiceSurface._watch_transport` then marks the skill inactive.

The bot token is read from `DISCORD_TOKEN`. It is never written to
`config.json` and is masked in `GET /config`.

---

## Minecraft

The mod is a separate project (`../beacraft`, Fabric 1.21.1, Java 21). It is
**client-side**: it drives the local player by simulating input and sends normal
packets, so to a server it looks like an ordinary client.

Python side (`src/core/skills/minecraft/`):
- `client.py` — WebSocket thread bridged to the event loop with
  `call_soon_threadsafe`. `execute()` turns the mod's async protocol into
  "call a tool → get an observation" by awaiting `FINISHED`/`IDLE`.
- `tools.py` — 24 declarative tools + `update_notebook`.
- `surface.py` — the perception loop pushes a snapshot at least every 10s.

---

## Memory

Everything lives in one transactional SQLite file, `data/bea.db`
(`src/core/memory/`). It replaced five stores that could not stay in sync — a
Chroma collection plus four JSON files, each rewritten whole on every write, with
no atomicity across them.

| Register | Table | Always in context | Written by |
|---|---|---|---|
| Episodic diary | `memories` (scope `diary`) | no, top-3 per batch | `DiaryGenerator` at session end |
| Roster (tally) | `roster` + `identities` | never | `SocialMemory.context_for`, per perception |
| Person cards | `people` + `facts` | only those present, max 5 | auto-promotion + `remember_person` + dreamer + profiler |
| Conversations | `messages` + `summaries` | per conversation turn | the platform skills |
| Self-lore | `self_facts` + `self_profile` | yes (last 15 facts) | the dreamer only |
| Hot facts | `hot_facts` (TTL) | yes (max 6) | dreamer + morning pass |
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

Migration from the old stores: `uv run python tools/migrate_to_sqlite.py`
(idempotent, `--dry-run` supported).

---

## Web and UI

FastAPI (`src/web/app.py`) + React/Vite/Tailwind (`src/web/frontend`). The
dashboard polls `/skills`, `/skills/logs` and `/events`. The built frontend is
served by the backend behind an SPA catch-all.

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
react to them instead of dropping the loop.

---

## Commands

```bash
make install        # uv sync
make run            # CLI
make web            # build the frontend + dashboard on :8000
make test           # pytest
make lint           # ruff
```

Discord bot: `cd src/core/skills/voice/bot && npm install` (once).
Minecraft mod: `cd ../beacraft && make build && make run`.
