"""Long-term memory: embedded recollections plus similarity retrieval.

Embeddings live in `memories.embedding` as float32 blobs. The pure-python
cosine path is always correct; sqlite-vec, when present, is only a coarse
pre-filter re-ranked by the same cosine, so both paths return the same thing.

`recall_split` keeps what people said apart from what Bea said: she invents on
purpose, and her own lines coming back as facts would compound into fiction.
"""

import math
import time
from array import array
from typing import List, Optional, Sequence, Tuple

from src.core.memory.db import Database
from src.utils.logger import get_logger

logger = get_logger("bea.memory.rag")

# below this, a "memory" is a fragment, not a recollection
MIN_REMEMBER_LEN = 8

# candidates to pull from sqlite-vec per final result: it orders by L2 and we
# re-rank by cosine, so without the margin the right memory can fall outside
VEC_OVERFETCH = 3

SOURCE_PERSON = "person"
SOURCE_BEA = "bea"


def _to_blob(vec: Sequence[float]) -> bytes:
    return array("f", vec).tobytes()


def _from_blob(blob: bytes) -> List[float]:
    a = array("f")
    a.frombytes(blob)
    return list(a)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


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
        if self.db.vec_enabled:
            self._init_vec_table()

    def _init_vec_table(self) -> None:
        try:
            dim = self.embedder.dim
            with self.db.cursor() as cur:
                cur.execute(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories USING vec0("
                    f"scope_key TEXT partition key, embedding float[{dim}])"
                )
            self._vec_ready = True
            logger.info(f"sqlite-vec index ready (dim={dim}).")
        except Exception as e:
            self._vec_ready = False
            logger.warning(f"Could not create vec_memories ({e}); using the python path.")

    @staticmethod
    def _partition(scope: str, scope_key: str) -> str:
        return f"{scope}:{scope_key}"

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

        # the vec table fixes its dimension at creation: a new dim needs a rebuild
        if self._vec_ready:
            try:
                with self.db.cursor() as cur:
                    cur.execute("DROP TABLE IF EXISTS vec_memories")
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
            for row, vec in zip(chunk, vectors, strict=True):
                blob = _to_blob(vec)
                self.db.execute("UPDATE memories SET embedding = ? WHERE id = ?", (blob, row["id"]))
                self._index_vector(row["id"], row["scope"], row["scope_key"], blob)
                done += 1
        logger.info(f"Re-embedded {done}/{len(rows)} memories.")
        return done

    # --- writing ------------------------------------------------------------

    def remember(self, *, scope: str, scope_key: str = "", text: str, who: str = "",
                 who_identity: Optional[str] = None, source: str = SOURCE_PERSON,
                 tags: str = "", created_at: Optional[float] = None) -> Optional[int]:
        text = (text or "").strip()
        if len(text) < MIN_REMEMBER_LEN:
            return None
        if source not in (SOURCE_PERSON, SOURCE_BEA):
            raise ValueError(f"unknown memory source: {source!r}")

        dup = self.db.query_one(
            "SELECT id FROM memories WHERE scope = ? AND scope_key = ? AND text = ?",
            (scope, scope_key, text),
        )
        if dup:
            return None

        blob = None
        try:
            blob = _to_blob(self.embedder.embed([text])[0])
        except Exception as e:
            # still worth keeping without a vector: a later re-embed fills it in
            logger.warning(f"Embedding failed, storing without a vector: {e}")

        mem_id = self.db.execute(
            "INSERT INTO memories (scope, scope_key, who_identity, who_name, text, source, "
            "embedding, tags, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (scope, scope_key, who_identity, who, text, source, blob, tags,
             created_at if created_at is not None else time.time()),
        )
        if blob is not None:
            self._index_vector(mem_id, scope, scope_key, blob)
        return mem_id

    def _index_vector(self, mem_id: int, scope: str, scope_key: str, blob: bytes) -> None:
        if not self._vec_ready:
            return
        try:
            with self.db.cursor() as cur:
                cur.execute(
                    "INSERT OR REPLACE INTO vec_memories (rowid, scope_key, embedding) "
                    "VALUES (?, ?, ?)",
                    (mem_id, self._partition(scope, scope_key), blob),
                )
        except Exception as e:
            logger.warning(f"Vector index insert failed (id={mem_id}): {e}")

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
        if self._vec_ready and scope is not None and scope_key is not None:
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

    def _recall_vec(self, scope: str, scope_key: str, qvec, k) -> List[Recollection]:
        """sqlite-vec as a coarse pre-filter, re-ranked by the same cosine.

        vec0 works in L2 distance, not cosine: the `min_similarity` threshold is
        meaningless in that space, and on non-normalized vectors even the ordering
        differs. So it only supplies candidates quickly; the decision is the same
        cosine the python path uses, and both return identical results.
        """
        hits = self.db.query(
            "SELECT rowid FROM vec_memories WHERE scope_key = ? AND embedding MATCH ? "
            "AND k = ? ORDER BY distance",
            (self._partition(scope, scope_key), _to_blob(qvec), k * VEC_OVERFETCH),
        )
        rows = []
        for hit in hits:
            row = self.db.query_one(
                "SELECT who_name, text, embedding, source, created_at, scope_key "
                "FROM memories WHERE id = ? AND embedding IS NOT NULL",
                (hit["rowid"],),
            )
            if row:
                rows.append(dict(row))
        return self._rank(rows, qvec, k)

    def _rank(self, rows: List[dict], qvec, k: int) -> List[Recollection]:
        now = time.time()
        scored: List[Tuple[float, Recollection]] = []
        for row in rows:
            similarity = cosine(qvec, _from_blob(row["embedding"]))
            if similarity < self.min_similarity:
                continue
            age_days = max(0.0, (now - float(row["created_at"] or now))) / 86400.0
            recency = 1.0 / (1.0 + age_days * self.decay_per_day)
            final = similarity * (1.0 - self.recency_weight) + recency * self.recency_weight
            scored.append((final, Recollection(
                text=row["text"], who=row["who_name"] or "", source=row["source"],
                similarity=similarity, created_at=float(row["created_at"] or 0),
                scope_key=row["scope_key"] or "",
            )))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [rec for _, rec in scored[: k * 2]]

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
        if self._vec_ready:
            # no foreign key back to `memories`: clean it by hand
            for row in rows:
                try:
                    self.db.execute("DELETE FROM vec_memories WHERE rowid = ?", (row["id"],))
                except Exception as e:
                    logger.warning(f"Vector cleanup failed (id={row['id']}): {e}")
        self.db.execute(f"DELETE FROM memories WHERE {where}", params)
        logger.info(f"Forgot {len(rows)} memories.")
        return len(rows)

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
