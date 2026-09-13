"""Embeddings as bytes, and the one measure of closeness the engine uses.

There were two copies of `cosine` — one in `rag.py`, one in `picker.py` —
already spelling the norm differently. They still agreed, which is the point:
the next edit to one of them is where they stop, and nothing would have said
so. Two answers to "how close are these" is one more than a system can have.

Both were also written a float at a time. That reads clearly and costs 34x:
scoring 2000 stored memories against a query took 89.5 ms in python and 2.65 ms
through numpy, on the same machine and the same data. numpy is already a
required dependency; there was never a trade to make.
"""

from typing import Sequence

import numpy as np

# what goes in the `embedding` blob column, and what sqlite-vec reads back
DTYPE = np.float32


def to_blob(vec: Sequence[float]) -> bytes:
    """A vector as the float32 bytes stored in `memories.embedding`."""
    return np.asarray(vec, dtype=DTYPE).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    """One stored vector. A view where possible, so nothing is copied to read it."""
    return np.frombuffer(blob, dtype=DTYPE)


def stack(blobs: Sequence[bytes]) -> np.ndarray:
    """Stored vectors as one `(n, dim)` array, width taken from the first.

    Joined and reinterpreted in a single pass rather than decoded row by row:
    this is where almost all of the 34x lives, because the per-row version
    spends its time building python floats nobody ever looks at individually.

    Blobs of differing widths cannot be stacked, and saying so here is better
    than reshaping into whatever happens to divide evenly.
    """
    blobs = list(blobs)
    if not blobs:
        return np.empty((0, 0), dtype=DTYPE)
    width = len(blobs[0]) // DTYPE(0).itemsize
    if width == 0 or any(len(b) != len(blobs[0]) for b in blobs):
        raise ValueError("stored vectors do not all have the same width")
    return np.frombuffer(b"".join(blobs), dtype=DTYPE).reshape(len(blobs), width)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Closeness of two vectors, in [-1, 1]. Zero when either has no direction.

    Raises on a length mismatch rather than comparing what overlaps: vectors of
    two different widths mean two different models, and a number computed
    across them would be meaningless in a way no caller could detect.
    """
    x = np.asarray(a, dtype=np.float64)
    y = np.asarray(b, dtype=np.float64)
    if x.shape != y.shape:
        raise ValueError(f"cannot compare a vector of {x.size} with one of {y.size}")
    na = float(np.linalg.norm(x))
    nb = float(np.linalg.norm(y))
    if na == 0.0 or nb == 0.0:
        return 0.0
    value = float(np.dot(x, y)) / (na * nb)
    # floating point can push an identical pair a hair past 1.0, which then
    # reads as "more similar than possible" to anything comparing thresholds
    return max(-1.0, min(1.0, value))


def cosine_batch(query: Sequence[float], rows: np.ndarray) -> np.ndarray:
    """`query` against every row of `rows`, as one array of similarities."""
    if rows.size == 0:
        return np.empty(0, dtype=np.float64)
    q = np.asarray(query, dtype=np.float64)
    if q.size != rows.shape[1]:
        raise ValueError(f"cannot compare a vector of {q.size} with rows of {rows.shape[1]}")
    m = rows.astype(np.float64, copy=False)
    norms = np.linalg.norm(m, axis=1) * float(np.linalg.norm(q))
    sims = m @ q
    # a stored zero vector has no direction; it is unrelated to everything
    # rather than undefined, which is what dividing by its norm would give
    out = np.zeros_like(sims)
    np.divide(sims, norms, out=out, where=norms > 0)
    return np.clip(out, -1.0, 1.0)


def is_finite(vec: Sequence[float]) -> bool:
    """Whether a vector is safe to store. A NaN poisons every later comparison."""
    return bool(np.all(np.isfinite(np.asarray(vec, dtype=np.float64))))


def norm(vec: Sequence[float]) -> float:
    return float(np.linalg.norm(np.asarray(vec, dtype=np.float64)))


__all__ = ["DTYPE", "cosine", "cosine_batch", "from_blob", "is_finite", "norm",
           "stack", "to_blob"]
