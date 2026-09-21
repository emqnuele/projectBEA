# Integration Map — V1 Architecture (VERIFIED + PROPOSED)

Verified relationships confirmed by file inspection (`brain.py` imports, `events.py` interfaces, `skills/` surfaces, `expression.py` adapter, `projection.py` boundary, `docs/EVENT_CONTRACT.md` contract):

```
                          ATLAS (PROPOSED operational layer)
                     durable context / architecture / decisions
                                   │
                                   │ consumes / provides
                                   ▼
                          FORGE (PROPOSED workspace layer)
                workspace / observation / tasks / agents / UI shell
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
         PROJECTSHURA CORE     SESSION STATE      TASK / AGENT STATE
              │                    │                    │
    ┌─────────┼─────────┐        │                    │
    ▼         ▼         ▼        ▼                    ▼
CONSCIOUSNESS  DREAM  MEMORY  EVENT MANAGER     AGENT / TOOL
(loop)         (domain)  (durable) (subscribe/replay) (execution)
    │            │        │            │                 │
    │            │        │            ▼                 │
    │            │        │      PERSISTENT JOURNAL      │
    │            │        │      data/events/events.jsonl │
    │            │        │            │                 │
    │            │        ▼            │                 │
    │            │      MEMORY         │                 │
    │            │      STORAGE        │                 │
    │            │      (ChromaDB)     │                 │
    │            │                     │                 │
    │            ▼                     ▼                 ▼
    │      PROJECTION LAYER      FORGE EVENT SUBSCRIPTION  TOOL RESULTS
    │      (projection.py)        (subscribe/replay)       (agent output)
    │            │                          │                 │
    │            ▼                          ▼                 ▼
    │      READ-ONLY STATE         UI OBSERVATION        AGENT OUTPUT
    │      DreamStateProjection     live feed / audit      results / errors
    │            │                          │                 │
    ▼            ▼                          ▼                 ▼
EXPRESSION (downstream adapter) ──► AVATAR STATE ──► USER OBSERVATION
(expression.py → OBS + TTS + avatar poses + text bubbles; identity layer independent of avatar assets)
```

Verified boundary rules (from `docs/AGENTS.md`, `docs/ARCHITECTURE_AUDIT.md`, `docs/DREAM_ENGINE.md`, source code):

1. ATLAS does not absorb brain logic. ATLAS holds architecture, context, session continuity, design specs, reference mappings. ProjectSHURA holds identity, cognition, skills, memory runtime. FORGE holds workspace/task observation.
2. ProjectSHURA brain/consciousness does NOT import ATLAS directly (currently verified: `brain.py` imports `config`, `events`, `expression`, `skills`, `agent`, `resources`, `history_manager` — no `docs/` import). The autonomous loop reads ATLAS context (`docs/operations/LOOP_STATE.md`, `docs/tasks/V1_TASK_GRAPH.md`) through file-based context retrieval, not through runtime import of design documents into brain logic.
3. ProjectSHURA Dream domain (`domain.py`, `events.py`, `transaction.py`) does NOT import `projection.py` (verified by source inspection: projection imports domain and events; domain does not import projection). The projection layer reads domain; domain does not write to projection.
4. ProjectSHURA event emission (`EventManager.publish()`) is the only event creation mechanism (verified: `brain.py` creates `EventManager()`, `consciousness.py` uses `self.events.publish()`, `expression.py` uses `self.event_manager`). FORGE observes through `subscribe()` / replay; it does not create a new event bus.
5. FORGE workspace UI observes ProjectSHURA state through the projection layer (`/dream/projection`) and event replay/subscription (`/events`). It does NOT reach directly into `DreamRun` internals except through the projection builder. The projection builder (`build_projection()`) creates a `DreamStateProjection` from domain objects and replay data; it never modifies `DreamRun` (verified by `tests/test_dream_projection.py` test `test_projection_does_not_mutate_domain`).
6. Mutation of Dream state happens through `/dream/run` endpoint (`run_dream()` calls `brain.run_dream()` which activates `DreamSkill`). This is the explicit application/service command boundary. The projection endpoint (`/dream/projection`) is read-only.
7. Memory mutations (durable) flow through `MemoryStorage` via reconciliation/commit framework (`MemoryConsolidationTransaction`, `ConsolidationEngine`) — framework verified present (`transaction.py`, `consolidation.py`, `memory.py`), full pipeline integration deferred. UI/project layer does not directly write to `MemoryStorage`; it uses `MemorySkill` interfaces (`/memory/save` endpoint) or future service-layer commands.
8. Identity (`data/prompts/soul.md`, `operating.md`) remains independent of model/provider (`omniroute_llm.py`, `openai_compat.py`, `groq_llm.py`, `openrouter_llm.py` exist; identity files contain no provider references — verified by reading identity files in previous steps). Changing providers does not change identity. Changing identity requires explicit governed review.
9. Embodiment (`expression.py` → OBS + TTS + avatar poses + text bubbles) remains a downstream adapter of brain state. The identity layer (`soul.md`) defines persona; the embodiment layer (`expression.py`) renders it. They are separate. The UI/project layer does not drive embodiment directly; it observes through event emission and projection.
10. Legacy mood IDs preserved (`normal`, `shock`, `love`, `cry`, `angry`, `ew`, `bored`) — load-bearing for current OBS/embodiment until Live2D abstraction replaces them. Any future embodiment upgrade must preserve backward compatibility with these IDs or provide an explicit migration path.
