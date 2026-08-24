# Memory Skill — long-term recall

← [Skills Overview](overview.md) | [Back to README](../../README.md)

---

## What it does

At the end of a session Bea writes a diary entry about it. On every turn, the
entries that resemble what is happening right now are retrieved and injected
into her prompt. That is the whole loop.

Everything Bea remembers lives in one transactional SQLite file,
`data/bea.db`. Embeddings are computed locally by `fastembed` and stored as
float32 blobs in the `memories` table.

```
src/core/skills/memory/
├── memory.py      MemorySkill — the capability
└── generator.py   DiaryGenerator — one LLM call, JSON out

src/core/memory/           (the storage layer, shared with everything else)
├── db.py          SQLite in WAL + a lock; loads sqlite-vec when available
├── rag.py         embed, recall, recall_split, forget
├── embedder.py    fastembed / ONNX on CPU, lazy
└── schema.sql
```

---

## Recall — two blocks, never one

`context_for(batch)` runs on every batch and returns what she remembers. It
comes back **split by who said it**:

```
[LONG TERM MEMORY]
- [3 days ago] marco said he's building a redstone farm

[THINGS YOU SAID BEFORE — your own past lines, not established facts.
 You made some of them up; don't treat them as true just because you said them.]
- [yesterday] you told chat you own four ferraris
```

Bea invents on purpose. Without that split her own inventions come back as
retrieved facts, she builds on them as if they were true, and the fiction
compounds into incoherence. `memories.source` is `'person'` or `'bea'`, and
`rag.recall_split()` returns two lists.

**There is no recall tool.** Memory is injected on every turn, so asking for it
would only cost a second embedding and a slow round-trip for something already
in front of her.

### How a result is ranked

`rag.py` embeds the query, computes cosine similarity against the candidates,
and mixes in recency so a recent memory beats a marginally more similar old one.
When `sqlite-vec` is installed it is used as a coarse pre-filter (over-fetching
`VEC_OVERFETCH × k` candidates, since it orders by L2 and we re-rank by cosine);
without it the pure-Python path runs over the same rows and returns the same
thing.

`min_similarity` (default `0.35`) is the floor below which a result is not a
recollection, just noise.

---

## The diary

```
Brain.create_new_session()
    └─ memory_skill.process_previous_session(session_id, history)
            └─ [async task] DiaryGenerator.generate_diary(history)
                    ├─ background model, JSON mode
                    └─ {"diary_content", "tags", "user_id"}
            └─ rag.remember(text, scope="diary", ...)
```

The generator runs on the **`background`** model pool, never on the mind's — a
diary is not worth the good model, and it must not compete with the part of her
that talks to people.

On shutdown, `save_all_pending()` is awaited in the `finally` block of
`src/cli.py`, so the current session is written on a clean stop, a crash **and**
a Ctrl+C. It guards on existence, so a double call is harmless.

`POST /memory/save` triggers the same pass for the live session from the
dashboard.

---

## The embedding model

The default is **multilingual** on purpose:
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. With an
English-only model, non-English sentences collapse into the same region of the
space and retrieval becomes close to random.

Vectors from two different models are not comparable, so changing
`embedding_model` re-embeds everything: `rag.ensure_model()` checks the recorded
model at startup and rebuilds the store if it moved.

The model (~100 MB) is downloaded on first use into `embedding_cache_dir`, not
at startup. If it cannot be loaded at all, the brain logs the error and keeps
going: the roster, the person cards and the hot facts still work — only recall
is lost.

---

## Configuration

```json
"memory": {
  "enabled": true,
  "db_path": "data/bea.db",
  "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
  "embedding_cache_dir": "data/embeddings_cache",
  "min_similarity": 0.35
}
```

| Key | Default | Description |
|---|---|---|
| `db_path` | `data/bea.db` | The one file that holds everything she remembers |
| `embedding_model` | multilingual MiniLM | Any fastembed model id |
| `embedding_cache_dir` | `data/embeddings_cache` | Where the ONNX model is cached |
| `min_similarity` | `0.35` | Below this, a match is not a recollection |

Old configs carrying `"local"`, `"default"` or an empty string as
`embedding_model` are migrated at load time (`embedder.resolve_model`), because
fastembed rejects those names.

---

## Importing a Chroma-era store

`tools/migrate_to_sqlite.py` lifts a Chroma diary and the JSON roster, people,
recent-facts and self-lore files into `bea.db`.

```bash
make migrate
```

runs it with `--dry-run` first; re-run without the flag to apply. It needs the
`migrate` extra (`chromadb`), which is not installed by default.

---

## Related

- [Social memory](social.md) — who people are, on top of the same database
- [Dream](dream.md) — the nightly pass that turns raw sessions into durable memory
- [Architecture → Memory](../architecture.md#memory)
