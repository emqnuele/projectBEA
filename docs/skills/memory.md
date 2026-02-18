# Memory Skill — RAG System

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What It Does

The Memory Skill gives Bea long-term memory across conversation sessions. At the end of each session, it uses the LLM to write a "diary entry" summarizing what happened. These entries are stored in a local ChromaDB vector database. On every new message, semantically relevant memories are retrieved and injected into the system prompt so Bea remembers past interactions.

This is a **RAG (Retrieval-Augmented Generation)** pattern applied to conversational memory.

---

## File Structure

```
src/modules/skills/memory/
├── memory_skill.py     Main skill — orchestrates storage + generation
├── storage.py          ChromaDB wrapper (MemoryStorage)
├── generator.py        Diary generation via LLM (DiaryGenerator)
└── diary_prompt.txt    System prompt used when generating diary entries
```

---

## Flow

### Session End → Memory Write

```
Brain.create_new_session()
    └─ memory_skill.process_previous_session(session_id, history)
            └─ [async] DiaryGenerator.generate_diary(history)
                    ├─ formats history as conversation text
                    ├─ calls LLM.generate_json() with diary_prompt.txt
                    └─ returns JSON: { diary_content, tags, user_id }
            └─ MemoryStorage.add_entry(content, metadata, id)
                    └─ ChromaDB collection.add(...)
```

A guard checks if the diary for the session already exists (`entry_exists()`) before writing, so replaying or reloading does not create duplicates.

### Every Message → Memory Read (RAG injection)

```
Brain.generate_response(user_text)
    └─ memory_skill.retrieve_context(user_text, limit=3)   # limit is optional, default 3
            └─ MemoryStorage.query_similar(user_text, fetch_limit=limit*3)
                    └─ ChromaDB cosine similarity search (over-fetches 3× candidates)
            └─ re-rank by weighted score:
                    similarity_score  = 1 - cosine_distance        (weight: 70%)
                    recency_score     = 1 / (1 + age_days × 0.1)  (weight: 30%)
                    final_score       = similarity×0.7 + recency×0.3
            └─ top `limit` (default `3`) results returned
            └─ returns formatted context string
    └─ injects into system_prompt:
            "[LONG TERM MEMORY]\n{context}\n"
```

**`retrieve_context()` signature:**
```python
def retrieve_context(query: str, limit: int = 3) -> str
```

> The over-fetch + re-rank ensures that very recent memories are not completely crowded out by slightly higher-similarity older entries.

---

## Diary Entry Format

The LLM is instructed by `diary_prompt.txt` to return:

```json
{
  "diary_content": "Today I talked with [user] about ...",
  "tags": ["gaming", "minecraft", "user_emanu"],
  "user_id": "emanu"
}
```

Metadata stored alongside each entry:
- `timestamp` (unix)
- `date` (ISO string)
- `user_id`
- `tags` (comma-separated)
- `session_id`

---

## ChromaDB Storage

**Database path:** `data/memory_db/` (configurable via `skills.memory.chroma_path`)

**Collection name:** `bea_diary`

**Embedding function:** OpenAI `text-embedding-3-small` (requires `OPENAI_API_KEY`).  
If no key is available, ChromaDB falls back to its built-in default embedder — functionality is preserved but retrieval quality degrades.

The database is persistent — it survives restarts and accumulates over time.

---

## Configuration

```json
"memory": {
  "enabled": true,
  "chroma_path": "data/memory_db",
  "openai_model": "gpt-4o-mini",
  "embedding_model": "text-embedding-3-small"
}
```

| Key | Description |
|---|---|
| `chroma_path` | Directory for the persistent ChromaDB files |
| `openai_model` | Model used for diary generation |
| `embedding_model` | OpenAI embedding model for vector search |

---

## Public Methods

### `save_current_session() -> bool`

Synchronous convenience method. Manually triggers diary generation for the current active session by calling `process_previous_session()` (fire-and-forget via `asyncio.create_task()`). Returns `True` if the trigger was enqueued, `False` if the skill is disabled or there is no active session with content. Called by `POST /memory/save`.

```python
brain.memory_skill.save_current_session()
```

---

## Web API

| Endpoint | Description |
|---|---|
| `POST /memory/save` | Manually triggers diary generation for the current session |

---

## `save_all_pending()`

Async method on `MemorySkill` called at engine shutdown from the `except KeyboardInterrupt` block in `main.py`. It checks if the current session has already been saved; if not, it awaits `_process_session_async()` directly to guarantee the diary entry is written before the process exits.

```python
await brain.memory_skill.save_all_pending()
```

Unlike `process_previous_session()`, which fires-and-forgets via `asyncio.create_task()`, this method is awaited synchronously so no data is lost on clean shutdown.

> **Scope limitation:** `save_all_pending()` is only called in the `except KeyboardInterrupt` handler. If the engine exits due to an unhandled exception (not a `KeyboardInterrupt`), this method is **not** invoked and the current session's diary entry may be lost. Only `Ctrl+C` / `KeyboardInterrupt` guarantees a clean memory save.

---

## Dependencies

- `chromadb >= 0.4.0`
- `openai` (for embeddings)
