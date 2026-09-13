"""Long-term memory: embedded recollections plus similarity retrieval.

Embeddings live in `memories.embedding` as float32 blobs, and in a sqlite-vec
index beside them when the extension is available. The index is asked for
cosine distance directly, so it and the python path are the same measure rather
than two that have to be reconciled; the python path stays as the answer when
there is no extension, and the two are tested against each other.

The index is partitioned by `scope`, and carries `scope_key` as an ordinary
filterable column rather than a second partition key. That is the shape of the
questions actually asked of it: memories are written one session at a time and
read across all of them.

It was the other way round once — partitioned by session — which meant the only
query production ever makes could not use the index at all, and every recall
quietly scanned the whole store. Nothing failed; it was just slow in a way no
test could see.

Making `scope_key` a partition key as well is the obvious improvement and is a
trap. It does make a recall that names one session faster, but a partitioned
search that does *not* name one has to visit every partition, and a session is
created per day: at 20k memories over 50 sessions that costs 5 ms, over 2000
sessions it costs 1280 ms. As a plain column it is 4.3 ms at both, because the
work depends on how much is stored and not on how it happens to be grouped.
`docs/performance.md` has the numbers.

`recall_split` keeps what people said apart from what Bea said: she invents on
purpose, and her own lines coming back as facts would compound into fiction.
"""

import time
from typing import List, Optional, Tuple

from src.core.memory.db import Database
from src.core.memory.vectors import DTYPE, cosine, cosine_batch, stack, to_blob
from src.core.perf import perf_enabled
from src.utils.logger import get_logger

logger = get_logger("bea.memory.rag")

# below this, a "memory" is a fragment, not a recollection
MIN_REMEMBER_LEN = 8

# most candidates the index is asked for in one go.
#
# Not a top-k: everything above `min_similarity` is asked for, because the final
# order also weighs recency and a slightly less similar memory from today can
# beat the closest one from last year. A shortlist ordered by similarity alone
# cannot know which of the ones it left out were recent, so asking for k of them
# would quietly return a different answer than the full scan does — which is
# precisely what "both paths agree" is supposed to rule out.
#
# Coming back full is therefore the one case the index cannot answer: there may
# be more above the threshold than it was allowed to say. Then the scan runs,
# and the answer is exact rather than nearly right.
VEC_CANDIDATE_CAP = 1024

# the shape of `vec_memories`. Bumped when the table's columns or its distance
# metric change, which is what triggers the rebuild in `_init_vec_table`.
VEC_SCHEMA = "2"

# how many ids to fetch back per round trip after the index has chosen them
FETCH_CHUNK = 500

SOURCE_PERSON = "person"
SOURCE_BEA = "bea"

# `cosine` is re-exported: it was defined here before it was shared, and callers
# and tests import it from this module
__all__ = ["MIN_REMEMBER_LEN", "SOURCE_BEA", "SOURCE_PERSON", "Rag", "Recollection",
           "cosine"]


class Recollection:
    """One retrieved memory, with everything the prompt renderer needs."""

    __slots__ = ("text", "who", "source", "similarity", "created_at", "scope_key")

    def __init__(self, text: str, who: str, source: str, similarity: float,
                 created_at: float, scope_key: str = ""):
        self.text = text
        self.who = who
        self.source = source
        self.similarity = similarity
        self.created_at = created_at
        self.scope_key = scope_key

    def render(self) -> str:
        return f"{self.who}: {self.text}" if self.who else self.text

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Recollection {self.source} {self.similarity:.2f} {self.text[:40]!r}>"


class Rag:
    def __init__(self, db: Database, embedder, *, min_similarity: float = 0.35,
                 recency_weight: float = 0.3, decay_per_day: float = 0.1) -> None:
        self.db = db
        self.embedder = embedder
        self.min_similarity = min_similarity
        # a recent memory beats a marginally more similar old one
        self.recency_weight = recency_weight
        self.decay_per_day = decay_per_day
        self._vec_ready = False
        # said once: a store mid-model-change would otherwise say it per recall
        self._warned_width = False
        # the switch: off means the python path, exactly like no sqlite-vec
        if self.db.vec_enabled and perf_enabled():
            self._init_vec_table()

    def _init_vec_table(self) -> None:
        """Makes sure the index exists and matches this model, rebuilding if not.

        Never fatal. A store whose index cannot be built is a store that recalls
        through python instead — slower, and identical in what it returns.
        """
        try:
            dim = int(self.embedder.dim)
            wanted = f"{VEC_SCHEMA}:{dim}"
            if self._vec_meta() == wanted and self._vec_table_exists():
                self._vec_ready = True
                return
            self._rebuild_vec_table(dim, wanted)
            self._vec_ready = True
        except Exception as e:
            self._vec_ready = False
            logger.warning(f"Could not prepare vec_memories ({e}); using the python path.")

    def _vec_meta(self) -> Optional[str]:
        row = self.db.query_one("SELECT value FROM memory_meta WHERE key = 'vec_schema'")
        return row["value"] if row else None

    def _vec_table_exists(self) -> bool:
        return bool(self.db.query_one(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'vec_memories'"))

    def _rebuild_vec_table(self, dim: int, wanted: str) -> None:
        """Drops the index and fills it again from the vectors already stored.

        The index is derived, never the original: every vector in it also sits
        in `memories.embedding`, which this does not touch. So a rebuild costs a
        copy and not a re-embedding — no model is loaded and nothing is
        downloaded, which is what makes changing its shape affordable at all.
        """
        with self.db.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS vec_memories")
            cur.execute(
                f"CREATE VIRTUAL TABLE vec_memories USING vec0("
                f"scope TEXT partition key, scope_key TEXT, "
                f"embedding float[{dim}] distance_metric=cosine)"
            )
        copied = self._refill_vec_table(dim)
        self.db.execute(
            "INSERT INTO memory_meta (key, value) VALUES ('vec_schema', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (wanted,))
        logger.info(f"sqlite-vec index ready (dim={dim}, {copied} vectors indexed).")

    def _refill_vec_table(self, dim: int) -> int:
        """Every stored vector of the right width, back into the fresh index.

        Rows of another width are left out rather than reshaped: they are the
        leftovers of a model that has not been re-embedded yet, and `recall`
        already knows to ignore what it cannot compare.
        """
        width = dim * DTYPE(0).itemsize
        copied = 0
        last = 0
        while True:
            rows = self.db.query(
                "SELECT id, scope, scope_key, embedding FROM memories "
                "WHERE id > ? AND embedding IS NOT NULL AND length(embedding) = ? "
                "ORDER BY id LIMIT ?", (last, width, FETCH_CHUNK))
            if not rows:
                return copied
            with self.db.cursor() as cur:
                cur.executemany(
                    "INSERT INTO vec_memories (rowid, scope, scope_key, embedding) "
                    "VALUES (?, ?, ?, ?)",
                    [(r["id"], r["scope"], r["scope_key"], r["embedding"]) for r in rows])
            copied += len(rows)
            last = rows[-1]["id"]

    # --- model changes ------------------------------------------------------

    def ensure_model(self, model_name: str) -> int:
        """Re-embeds everything if the model changed. Returns how many.

        The text is stored in the clear, so a model switch loses nothing — the
        vectors are simply recomputed. Without this, old memories would sit in a
        different vector space and every similarity against them would be a
        meaningless number.
        """
        row = self.db.query_one("SELECT value FROM memory_meta WHERE key = 'embed_model'")
        previous = row["value"] if row else None
        if previous == model_name:
            return 0

        n = 0
        if previous is not None:
            logger.warning(f"Embedding model changed ({previous} → {model_name}): re-embedding.")
            n = self.reembed_all()
        self.db.execute(
            "INSERT INTO memory_meta (key, value) VALUES ('embed_model', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (model_name,),
        )
        return n

    def reembed_all(self, batch: int = 128) -> int:
        rows = self.db.query("SELECT id, text, scope, scope_key FROM memories ORDER BY id")
        if not rows:
            return 0

        # the index fixes its width at creation, so a new model needs a new one.
        # Emptied rather than rebuilt from `memories`: the vectors in there are
        # the old model's, and are about to be replaced row by row below.
        if self._vec_ready:
            try:
                with self.db.cursor() as cur:
                    cur.execute("DELETE FROM vec_memories")
                self._init_vec_table()
            except Exception as e:
                logger.warning(f"Rebuilding vec_memories failed ({e}); using the python path.")
                self._vec_ready = False

        done = 0
        for start in range(0, len(rows), batch):
            chunk = rows[start:start + batch]
            try:
                vectors = self.embedder.embed([r["text"] for r in chunk])
            except Exception as e:
                logger.error(f"Re-embedding failed at block {start}: {e}")
                break
            done += self._write_block(chunk, vectors)
        logger.info(f"Re-embedded {done}/{len(rows)} memories.")
        return done

    def _write_block(self, chunk, vectors) -> int:
        """One block of re-embedded vectors, in one transaction.

        Row by row this was two commits per memory. A commit is cheap and never
        free: the same 2000 writes cost 12.2 ms one at a time and 0.4 ms
        together, and a re-embed walks the entire store.
        """
        blobs = [to_blob(vec) for vec in vectors]
        with self.db.cursor() as cur:
            cur.executemany("UPDATE memories SET embedding = ? WHERE id = ?",
                            [(blob, row["id"]) for row, blob in zip(chunk, blobs, strict=True)])
            if self._vec_ready:
                # the index was emptied before this walk began, so every rowid
                # here is new to it
                cur.executemany(
                    "INSERT INTO vec_memories (rowid, scope, scope_key, embedding) "
                    "VALUES (?, ?, ?, ?)",
                    [(row["id"], row["scope"], row["scope_key"], blob)
                     for row, blob in zip(chunk, blobs, strict=True)])
        return len(chunk)

    # --- writing ------------------------------------------------------------

    def remember(self, *, scope: str, scope_key: str = "", text: str, who: str = "",
                 who_identity: Optional[str] = None, source: str = SOURCE_PERSON,
                 tags: str = "", created_at: Optional[float] = None) -> Optional[int]:
        text = (text or "").strip()
        if len(text) < MIN_REMEMBER_LEN:
            return None
        if source not in (SOURCE_PERSON, SOURCE_BEA):
            raise ValueError(f"unknown memory source: {source!r}")

        blob = None
        try:
            # before the transaction opens: embedding is the slow part, and
            # holding the write lock through it stalls everything else
            blob = to_blob(self.embedder.embed([text])[0])
        except Exception as e:
            # still worth keeping without a vector: a later re-embed fills it in
            logger.warning(f"Embedding failed, storing without a vector: {e}")

        # the duplicate is caught by `idx_memories_dedup`, which is a UNIQUE
        # index on exactly these three columns. Asking first, in its own
        # transaction, was asking the index a question it answers on the way in
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO memories (scope, scope_key, who_identity, who_name, text, "
                "source, embedding, tags, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT DO NOTHING",
                (scope, scope_key, who_identity, who, text, source, blob, tags,
                 created_at if created_at is not None else time.time()),
            )
            if not cur.rowcount:
                return None
            mem_id = cur.lastrowid or 0
            if blob is not None and self._vec_ready:
                try:
                    self._insert_vector(cur, mem_id, scope, scope_key, blob)
                except Exception as e:
                    # the memory still commits. The text is the original and the
                    # index is derived from it, so an index that will not take a
                    # vector costs a slower recall; letting it take the memory
                    # down with it would cost the memory
                    logger.warning(f"Vector index insert failed (id={mem_id}): {e}")
        return mem_id

    def _index_vector(self, mem_id: int, scope: str, scope_key: str, blob: bytes) -> None:
        """Indexes one vector, replacing any the same memory already had.

        Deliberately a DELETE and an INSERT: `INSERT OR REPLACE` does not
        replace on a vec0 table, it raises on the primary key, so what looked
        like an upsert was a statement that could only ever work once per row.
        """
        if not self._vec_ready:
            return
        try:
            with self.db.cursor() as cur:
                cur.execute("DELETE FROM vec_memories WHERE rowid = ?", (mem_id,))
                self._insert_vector(cur, mem_id, scope, scope_key, blob)
        except Exception as e:
            logger.warning(f"Vector index insert failed (id={mem_id}): {e}")

    @staticmethod
    def _insert_vector(cur, mem_id: int, scope: str, scope_key: str, blob: bytes) -> None:
        """Indexes a vector for a memory the index has never seen.

        No delete first, because there is nothing to delete: both callers hold
        a rowid sqlite has just minted, or one whose index was emptied a moment
        ago. Clearing it anyway cost 2.8µs of every single write.
        """
        cur.execute("INSERT INTO vec_memories (rowid, scope, scope_key, embedding) "
                    "VALUES (?, ?, ?, ?)", (mem_id, scope, scope_key, blob))

    # --- reading ------------------------------------------------------------

    def recall(self, query: str, *, scope: Optional[str] = None, scope_key: Optional[str] = None,
               k: int = 5) -> List[Recollection]:
        """Only what PEOPLE said. Backwards-compatible shape."""
        return self.recall_split(query, scope=scope, scope_key=scope_key, k=k)[0]

    def recall_split(
        self, query: str, *, scope: Optional[str] = None, scope_key: Optional[str] = None,
        k: int = 5,
    ) -> Tuple[List[Recollection], List[Recollection]]:
        """Returns (facts, things_bea_said) as two separate lists.

        Keeping them apart is the point: Bea's persona invents deliberately, and
        if her own output re-entered the prompt alongside real facts she would
        build on it as though it were true.
        """
        query = (query or "").strip()
        if not query:
            return [], []
        try:
            qvec = self.embedder.embed([query])[0]
        except Exception as e:
            logger.warning(f"Query embedding failed: {e}")
            return [], []

        rows = self._candidates(scope, scope_key, qvec, k)
        facts, hers = [], []
        for rec in rows:
            (hers if rec.source == SOURCE_BEA else facts).append(rec)
        return facts[:k], hers[:k]

    def _candidates(self, scope, scope_key, qvec, k) -> List[Recollection]:
        """The index when it can answer, the full scan when it cannot.

        A scope is all the index needs — it is what the table is partitioned by.
        Requiring a scope_key as well is what used to send every real recall
        down the scan, since nothing in the engine passes one when reading.
        """
        if self._vec_ready and scope is not None:
            try:
                return self._recall_vec(scope, scope_key, qvec, k)
            except Exception as e:
                logger.warning(f"Vector recall failed ({e}); falling back to python.")
        return self._recall_python(scope, scope_key, qvec, k)

    def _select(self, scope: Optional[str], scope_key: Optional[str]) -> Tuple[str, tuple]:
        sql = ("SELECT who_name, text, embedding, source, created_at, scope_key "
               "FROM memories WHERE embedding IS NOT NULL")
        params: List = []
        if scope is not None:
            sql += " AND scope = ?"
            params.append(scope)
        if scope_key is not None:
            sql += " AND scope_key = ?"
            params.append(scope_key)
        return sql, tuple(params)

    def _recall_python(self, scope, scope_key, qvec, k) -> List[Recollection]:
        sql, params = self._select(scope, scope_key)
        return self._rank([dict(r) for r in self.db.query(sql, params)], qvec, k)

    def _recall_vec(self, scope: str, scope_key: Optional[str], qvec, k) -> List[Recollection]:
        """Everything the index considers close enough, ranked the usual way.

        The index is asked for cosine distance, so `distance` is `1 - similarity`
        and `min_similarity` means the same thing on both sides. Asking it for
        every candidate above that threshold — rather than for the nearest few —
        is what makes this path and the scan return the same memories: the two
        then score the same set, and only then does recency decide.

        `min_similarity` is doing the work an overfetch margin used to pretend
        to do. Set it to zero and everything qualifies, so the index has nothing
        to narrow and the scan answers instead.
        """
        sql = "SELECT rowid FROM vec_memories WHERE scope = ?"
        params: List = [scope]
        if scope_key is not None:
            sql += " AND scope_key = ?"
            params.append(scope_key)
        # a vector with no direction gets a NULL distance rather than a number,
        # and NULL fails this comparison, which is the behaviour we want
        sql += " AND embedding MATCH ? AND k = ? AND distance <= ? ORDER BY distance"
        params += [to_blob(qvec), VEC_CANDIDATE_CAP, 1.0 - self.min_similarity]

        hits = self.db.query(sql, tuple(params))
        if len(hits) >= VEC_CANDIDATE_CAP:
            # it stopped counting, so there may be more that belong in the answer
            logger.debug("Too many memories are close enough to rank from the index; "
                         "scanning instead.")
            return self._recall_python(scope, scope_key, qvec, k)
        return self._rank(self._fetch([row["rowid"] for row in hits]), qvec, k)

    def _fetch(self, ids: List[int]) -> List[dict]:
        """The memories behind a list of ids, in as few round trips as possible.

        One query per id is what this replaced. It was invisible at four rows
        and is the whole cost at four thousand. Order is not preserved and does
        not need to be — `_rank` decides it.
        """
        rows: List[dict] = []
        for start in range(0, len(ids), FETCH_CHUNK):
            chunk = ids[start:start + FETCH_CHUNK]
            placeholders = ",".join("?" * len(chunk))
            rows.extend(dict(r) for r in self.db.query(
                "SELECT who_name, text, embedding, source, created_at, scope_key "
                f"FROM memories WHERE id IN ({placeholders}) AND embedding IS NOT NULL",
                tuple(chunk)))
        return rows

    def _rank(self, rows: List[dict], qvec, k: int) -> List[Recollection]:
        """Similarity and recency together, for every candidate at once.

        Scored as one matrix rather than a row at a time: the per-row version
        was 34x slower on the sizes a real store reaches, and produces the same
        numbers.
        """
        usable = self._comparable(rows, len(qvec))
        if not usable:
            return []

        now = time.time()
        similarities = cosine_batch(qvec, stack([r["embedding"] for r in usable]))
        ages = [max(0.0, now - float(r["created_at"] or now)) / 86400.0 for r in usable]

        scored: List[Tuple[float, Recollection]] = []
        for row, similarity, age_days in zip(usable, similarities, ages, strict=True):
            similarity = float(similarity)
            if similarity < self.min_similarity:
                continue
            recency = 1.0 / (1.0 + age_days * self.decay_per_day)
            final = similarity * (1.0 - self.recency_weight) + recency * self.recency_weight
            scored.append((final, Recollection(
                text=row["text"], who=row["who_name"] or "", source=row["source"],
                similarity=similarity, created_at=float(row["created_at"] or 0),
                scope_key=row["scope_key"] or "",
            )))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [rec for _, rec in scored[: k * 2]]

    def _comparable(self, rows: List[dict], dim: int) -> List[dict]:
        """The rows whose vectors can be compared with a query of this width.

        A store mid-model-change holds both widths at once. Skipping the ones
        that do not fit returns the memories that can still be found instead of
        failing the whole recall over the ones that cannot.
        """
        width = dim * DTYPE(0).itemsize
        usable = [r for r in rows if r["embedding"] is not None
                  and len(r["embedding"]) == width]
        dropped = len(rows) - len(usable)
        if dropped and not self._warned_width:
            self._warned_width = True
            logger.warning(f"{dropped} memories are from another embedding model "
                           f"and were skipped; they come back after a re-embed.")
        return usable

    # --- forgetting ---------------------------------------------------------

    def forget_scope(self, scope: str, scope_key: str) -> int:
        return self._forget("scope = ? AND scope_key = ?", (scope, scope_key))

    def forget_person(self, who_identity: str) -> int:
        """Everything attributed to one identity — someone asking to be forgotten."""
        return self._forget("who_identity = ?", (who_identity,))

    def _forget(self, where: str, params: tuple) -> int:
        rows = self.db.query(f"SELECT id FROM memories WHERE {where}", params)
        if not rows:
            return 0
        ids = [row["id"] for row in rows]
        try:
            with self.db.cursor() as cur:
                if self._vec_ready:
                    # no foreign key back to `memories`: clean it by hand, and in
                    # the same transaction, so a crash cannot leave the index
                    # holding vectors for memories that no longer exist
                    for start in range(0, len(ids), FETCH_CHUNK):
                        chunk = ids[start:start + FETCH_CHUNK]
                        cur.execute("DELETE FROM vec_memories WHERE rowid IN "
                                    f"({','.join('?' * len(chunk))})", tuple(chunk))
                cur.execute(f"DELETE FROM memories WHERE {where}", params)
        except Exception as e:
            logger.error(f"Forgetting failed, nothing was removed: {e}")
            return 0
        logger.info(f"Forgot {len(ids)} memories.")
        return len(ids)

    def count(self, scope: Optional[str] = None, scope_key: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) FROM memories WHERE 1=1"
        params: List = []
        if scope is not None:
            sql += " AND scope = ?"
            params.append(scope)
        if scope_key is not None:
            sql += " AND scope_key = ?"
            params.append(scope_key)
        return int(self.db.scalar(sql, tuple(params)))

    def exists(self, scope: str, scope_key: str) -> bool:
        return self.count(scope, scope_key) > 0
