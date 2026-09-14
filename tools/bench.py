"""What the engine actually costs, on this machine, right now.

The live database holds a handful of rows, so nothing here can be learned by
running against it: every retrieval path looks instant at that size and the one
that scales badly looks exactly like the one that does not. So the corpus is
synthetic and sized on purpose, and the numbers are the only thing allowed to
decide whether a change was worth making.

Two rules it exists to enforce:

  - no optimisation lands without a before and an after from this file
  - a scenario that disagrees with what someone expected is right, and the
    expectation is wrong

Vectors in the synthetic corpus are random rather than embedded. Embedding
50k sentences would take minutes and would measure the model, not the store —
the model has its own scenario, where it is the thing under test.

    uv run python tools/bench.py                 # everything that can run here
    uv run python tools/bench.py --scenario recall --sizes 1000,20000
    uv run python tools/bench.py --json bench.json
"""

import argparse
import json
import logging
import os
import platform
import statistics
import sys
import tempfile
import time
from array import array
from pathlib import Path
from typing import Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# the real embedding model is 384; keeping the synthetic corpus at the same
# width means the blob sizes, and so the io, are the ones she will really have
DIM = 384

DEFAULT_SIZES = (100, 1_000, 10_000)

# distinct subjects the synthetic memories are about. A store is not a uniform
# cloud: she talks about a few dozen things repeatedly, and a query is close to
# one of them and far from the rest
TOPICS = 40

# how much of a memory is its subject and how much is everything else about it.
# Tuned so similarity within a topic lands around 0.6-0.8 and across topics near
# zero, which is roughly what the real model produces on real diary entries
TOPIC_SHARE = 0.72

# the engine's own default. Benchmarking with a lower one measures a threshold
# nobody runs, and the threshold is what decides how much work retrieval does
MIN_SIMILARITY = 0.35

# discarded: sqlite pages, onnx arenas and the python bytecode all warm up, and
# a first iteration measures the warming rather than the work
WARMUP = 3
ITERATIONS = 30


# --- timing ------------------------------------------------------------------


class Result:
    """One measured thing. p50 and p95 — never a mean, which a single slow
    outlier drags somewhere no run ever actually landed."""

    __slots__ = ("name", "detail", "n", "p50", "p95", "note")

    def __init__(self, name: str, detail: str, n: int, samples: List[float],
                 note: str = "") -> None:
        self.name = name
        self.detail = detail
        self.n = n
        self.note = note
        if samples:
            ordered = sorted(samples)
            self.p50 = statistics.median(ordered) * 1e3
            self.p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] * 1e3
        else:
            self.p50 = self.p95 = float("nan")

    def row(self) -> str:
        if self.note:
            return f"  {self.name:<22} {self.detail:<18} {self.note}"
        return (f"  {self.name:<22} {self.detail:<18} "
                f"p50 {self.p50:9.3f} ms   p95 {self.p95:9.3f} ms")

    def as_dict(self) -> dict:
        return {"scenario": self.name, "detail": self.detail, "n": self.n,
                "p50_ms": round(self.p50, 4), "p95_ms": round(self.p95, 4),
                "note": self.note}


def measure(name: str, detail: str, n: int, work: Callable[[], object], *,
            iterations: int = ITERATIONS, warmup: int = WARMUP,
            setup: Optional[Callable[[], object]] = None) -> Result:
    for _ in range(warmup):
        if setup:
            setup()
        work()
    samples = []
    for _ in range(iterations):
        if setup:
            setup()
        start = time.perf_counter()
        work()
        samples.append(time.perf_counter() - start)
    return Result(name, detail, n, samples)


def skipped(name: str, detail: str, why: str) -> Result:
    return Result(name, detail, 0, [], note=f"skipped — {why}")


# --- the synthetic corpus -----------------------------------------------------


class BenchEmbedder:
    """Deterministic vectors with no model behind them.

    Queries land near one of the corpus topics rather than anywhere in the
    space. Uniformly random vectors in 384 dimensions are all nearly orthogonal
    to each other, so every similarity comes out near zero, nothing clears
    `min_similarity`, and a retrieval benchmark built on them measures a case
    that never happens. Real sentences cluster; so do these.
    """

    def __init__(self, dim: int = DIM, topics: int = TOPICS, seed: int = 7) -> None:
        self._dim = dim
        self._topics = _centroids(dim, topics, seed)
        self.calls = 0

    def embed(self, texts):
        import numpy as np
        self.calls += 1
        out = []
        for text in texts:
            seed = abs(hash(text)) % (2 ** 32)
            rng = np.random.default_rng(seed)
            topic = self._topics[seed % len(self._topics)]
            out.append(_near(topic, rng).tolist())
        return out

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def identity(self) -> str:
        return f"bench@{self._dim}"


def _centroids(dim: int, count: int, seed: int):
    import numpy as np
    rng = np.random.default_rng(seed)
    m = rng.normal(size=(count, dim)).astype(np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def _near(centroid, rng):
    import numpy as np
    noise = rng.normal(size=centroid.shape).astype(np.float32)
    noise /= np.linalg.norm(noise)
    v = TOPIC_SHARE * centroid + (1.0 - TOPIC_SHARE) * noise
    return (v / np.linalg.norm(v)).astype(np.float32)


def _blob(vec) -> bytes:
    return array("f", vec).tobytes()


def build_corpus(path: str, rows: int, *, sessions: int = 50, seed: int = 7):
    """A store with `rows` memories, spread over `sessions` days.

    Mirrors the real shape: one scope, a scope_key per session, timestamps over
    a year so the recency half of the ranking is genuinely exercised.
    """
    import numpy as np

    from src.core.memory.db import Database
    from src.core.memory.rag import Rag

    db = Database(path).init()
    rag = Rag(db, BenchEmbedder(), min_similarity=MIN_SIMILARITY)

    rng = np.random.default_rng(seed)
    topics = _centroids(DIM, TOPICS, seed)
    vectors = np.stack([_near(topics[i % TOPICS], rng) for i in range(rows)])
    now = time.time()
    payload = []
    for i in range(rows):
        payload.append((
            i + 1, "diary", f"s{i % sessions}", f"identity:{i % 200}", f"person{i % 200}",
            f"memoria sintetica numero {i} su qualcosa che è successo",
            "bea" if i % 5 == 0 else "person",
            vectors[i].tobytes(), "", now - (i % 400) * 86400.0,
        ))
    with db.cursor() as cur:
        cur.executemany(
            "INSERT INTO memories (id, scope, scope_key, who_identity, who_name, text, "
            "source, embedding, tags, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)", payload)
    _fill_index(db, rag, payload)
    return db, rag


def _fill_index(db, rag, payload) -> None:
    """Populates whatever vector table this revision of `Rag` created.

    Written against the columns the table reports rather than a hardcoded list,
    so the harness keeps working across the schema change it exists to measure.
    """
    if not getattr(rag, "_vec_ready", False):
        return
    columns = {r[1] for r in db.query("PRAGMA table_info(vec_memories)")}
    try:
        with db.cursor() as cur:
            if "scope" in columns:
                cur.executemany(
                    "INSERT INTO vec_memories (rowid, scope, scope_key, embedding) "
                    "VALUES (?,?,?,?)",
                    [(r[0], r[1], r[2], r[7]) for r in payload])
            else:
                cur.executemany(
                    "INSERT INTO vec_memories (rowid, scope_key, embedding) VALUES (?,?,?)",
                    [(r[0], f"{r[1]}:{r[2]}", r[7]) for r in payload])
    except Exception as e:
        print(f"  ! could not fill the vector index ({e}); vec rows will be skipped")
        rag._vec_ready = False


class corpus:
    """A throwaway store on disk, cleaned up afterwards.

    On disk and not `:memory:` on purpose: page cache, mmap and WAL are part of
    what is being measured, and none of them behave the same in memory.
    """

    def __init__(self, rows: int, **kw):
        self.rows = rows
        self.kw = kw

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="bea-bench-")
        self.db, self.rag = build_corpus(os.path.join(self.dir, "bench.db"),
                                         self.rows, **self.kw)
        return self.db, self.rag

    def __exit__(self, *exc):
        self.db.close()
        for name in os.listdir(self.dir):
            try:
                os.remove(os.path.join(self.dir, name))
            except OSError:
                pass
        os.rmdir(self.dir)
        return False


# --- scenarios ----------------------------------------------------------------


def _recall(rows: int, *, scope_key: Optional[str], label: str) -> List[Result]:
    """The same recall down both paths, in one run so the comparison is fair."""
    out = []
    with corpus(rows) as (db, rag):
        queries = [f"cosa è successo quel giorno numero {i}" for i in range(50)]
        counter = {"i": 0}

        def once():
            q = queries[counter["i"] % len(queries)]
            counter["i"] += 1
            rag.recall_split(q, scope="diary", scope_key=scope_key, k=5)

        vec_ready = bool(getattr(rag, "_vec_ready", False))
        if vec_ready:
            rag._vec_ready = True
            out.append(measure(label, f"{rows} rows, vec", rows, once))
        else:
            out.append(skipped(label, f"{rows} rows, vec", "sqlite-vec unavailable"))
        rag._vec_ready = False
        out.append(measure(label, f"{rows} rows, python", rows, once))
        rag._vec_ready = vec_ready
    return out


def scenario_recall(sizes, **_) -> List[Result]:
    """Recall narrowed to one session — what the tests exercise."""
    return [r for n in sizes for r in _recall(n, scope_key="s1", label="recall")]


def scenario_recall_nofilter(sizes, **_) -> List[Result]:
    """Recall across every session — what production actually calls.

    `single_context`, the memory skill and the dashboard all pass a scope and
    no scope_key. If this row and `recall` differ by an order of magnitude, the
    index is not serving the query anyone really makes.
    """
    return [r for n in sizes for r in _recall(n, scope_key=None, label="recall_nofilter")]


def _writer(rag, start: int) -> Callable[[], object]:
    counter = {"i": start}

    def once():
        counter["i"] += 1
        rag.remember(scope="diary", scope_key="s1",
                     text=f"una cosa nuova che vale la pena ricordare {counter['i']}")
    return once


def scenario_remember(sizes, **_) -> List[Result]:
    results = []
    for rows in sizes:
        with corpus(rows) as (db, rag):
            results.append(measure("remember", f"into {rows} rows", rows,
                                   _writer(rag, rows)))
    return results


def scenario_reembed(sizes, **_) -> List[Result]:
    """Rare but long: it runs inside startup whenever the model changed."""
    results = []
    for rows in sizes:
        if rows > 20_000:
            continue
        with corpus(rows) as (db, rag):
            # fewer iterations: each one rewrites every row in the store
            results.append(measure("reembed_all", f"{rows} rows", rows,
                                   rag.reembed_all, iterations=3, warmup=1))
    return results


def _forgetter(rag) -> Callable[[], object]:
    session = {"i": 0}

    def once():
        session["i"] += 1
        rag.forget_scope("diary", f"s{session['i'] % 50}")
    return once


def scenario_forget(sizes, **_) -> List[Result]:
    results = []
    for rows in sizes:
        with corpus(rows) as (db, rag):
            results.append(measure("forget_scope", f"of {rows} rows", rows,
                                   _forgetter(rag), iterations=10, warmup=1))
    return results


def scenario_startup(sizes, **_) -> List[Result]:
    """Opening the store and wiring recall.

    Worth its own row because it is the one cost the user waits on with nothing
    on screen, and because it is where a supposedly lazy model can turn out not
    to be — `Rag.__init__` asks the embedder for its width.
    """
    from src.core.memory.db import Database
    from src.core.memory.rag import Rag

    results = []
    for rows in sizes[:1]:
        with corpus(rows) as (db, rag):
            path = db.path
        # measured against a real embedder, which is the point of the row
        try:
            from src.core.memory.embedder import FastEmbedEmbedder
        except Exception as e:
            return [skipped("startup", "real embedder", str(e))]

        def once(path=path):
            opened = Database(path).init()
            Rag(opened, FastEmbedEmbedder(), min_similarity=0.35)
            opened.close()

        try:
            once()
        except Exception as e:
            return [skipped("startup", "real embedder", f"{type(e).__name__}: {e}")]
        results.append(measure("startup", "open + wire recall", rows, once,
                               iterations=5, warmup=1))
    return results


def scenario_embed(**_) -> List[Result]:
    """The real model. Everything above uses synthetic vectors; this does not."""
    try:
        from src.core.memory.embedder import FastEmbedEmbedder
        embedder = FastEmbedEmbedder()
        embedder.embed(["scaldiamo il modello"])
    except Exception as e:
        return [skipped("embed", "real model", f"{type(e).__name__}: {e}")]

    one = ["una singola frase da trasformare in vettore"]
    many = [f"frase numero {i} del blocco da trentadue" for i in range(32)]
    return [
        measure("embed", "1 text", 1, lambda: embedder.embed(one), iterations=20),
        measure("embed", "32 texts", 32, lambda: embedder.embed(many), iterations=10),
        measure("embed_dim", "read the width", 1,
                lambda: FastEmbedEmbedder().dim, iterations=5, warmup=1),
    ]


def scenario_history(**_) -> List[Result]:
    """One message appended to a session that already has some.

    Rewriting the whole file each time makes this grow with the session rather
    than staying flat, which is the shape to watch for here.
    """
    from src.utils.history_manager import HistoryManager

    results = []
    for existing in (10, 200, 2000):
        directory = tempfile.mkdtemp(prefix="bea-bench-hist-")
        try:
            manager = HistoryManager(storage_dir=directory)
            manager.create_session()
            for i in range(existing):
                manager.add_message("user", f"messaggio di riempimento {i}")
            results.append(measure("history_append", f"session of {existing}", existing,
                                   lambda m=manager: m.add_message("user", "un altro messaggio"),
                                   iterations=20))
        finally:
            for name in os.listdir(directory):
                os.remove(os.path.join(directory, name))
            os.rmdir(directory)
    return results


def scenario_turnlog(**_) -> List[Result]:
    """Here to be checked rather than to be fixed.

    Writing a turn down looks like per-turn file io, which reads as expensive.
    It is measured so the guess is not the thing anyone acts on.
    """
    from src.core.mind.turnlog import TurnLog

    directory = tempfile.mkdtemp(prefix="bea-bench-turns-")
    try:
        log = TurnLog(directory=Path(directory))
        record = {"prompt": "x" * 4000, "perceptions": ["ciao"], "reply": "ciao a te"}
        result = measure("turnlog_write", "one turn", 1, lambda: log.write(dict(record)),
                         iterations=50)
    finally:
        for name in os.listdir(directory):
            os.remove(os.path.join(directory, name))
        os.rmdir(directory)
    return [result]


def scenario_stt(**_) -> List[Result]:
    """Local whisper on a real file, when there is one to transcribe."""
    sample = next((p for p in (ROOT / "tests").rglob("*.wav")), None)
    if sample is None:
        return [skipped("stt", "local whisper", "no sample wav in tests/")]
    try:
        from src.core.config import BrainConfig
        from src.modules.STT.faster_whisper_stt import FasterWhisperSTT
        stt = FasterWhisperSTT(BrainConfig())
        if stt.model is None:
            return [skipped("stt", "local whisper", "model not loaded")]
    except Exception as e:
        return [skipped("stt", "local whisper", f"{type(e).__name__}: {e}")]
    return [measure("stt", f"{sample.name}", 1, lambda: stt.transcribe(str(sample)),
                    iterations=5, warmup=1)]


SCENARIOS: Dict[str, Callable[..., List[Result]]] = {
    "recall": scenario_recall,
    "recall_nofilter": scenario_recall_nofilter,
    "remember": scenario_remember,
    "reembed": scenario_reembed,
    "forget": scenario_forget,
    "startup": scenario_startup,
    "embed": scenario_embed,
    "history": scenario_history,
    "turnlog": scenario_turnlog,
    "stt": scenario_stt,
}

# the ones that need neither a model nor a download, so they are the ones a
# contributor can actually reproduce
FAST = ("recall", "recall_nofilter", "remember", "forget", "history", "turnlog")


# --- reporting ----------------------------------------------------------------


def machine() -> dict:
    from src.core.memory.db import Database
    probe = Database(":memory:")
    probe.connect()
    vec = probe.vec_enabled
    probe.close()
    return {
        "os": platform.system(),
        "release": platform.release(),
        "arch": platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "sqlite_vec": vec,
        "commit": _commit(),
    }


def _commit() -> str:
    import subprocess
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def main(argv=None) -> int:
    global ITERATIONS
    from src.utils.logger import quieten
    parser = argparse.ArgumentParser(description="Measure what the engine costs here.")
    parser.add_argument("--scenario", action="append", default=None,
                        help="run only this one; repeatable")
    parser.add_argument("--sizes", default=None,
                        help=f"corpus sizes, comma separated (default {DEFAULT_SIZES})")
    parser.add_argument("--iterations", type=int, default=None,
                        help=f"measured runs per row (default {ITERATIONS})")
    parser.add_argument("--fast", action="store_true",
                        help="only the scenarios that need no model")
    parser.add_argument("--json", default=None, help="also write the numbers here")
    parser.add_argument("--list", action="store_true", help="list the scenarios and exit")
    args = parser.parse_args(argv)

    if args.list:
        for name in SCENARIOS:
            print(name)
        return 0

    if args.iterations:
        ITERATIONS = args.iterations

    sizes = tuple(int(s) for s in args.sizes.split(",")) if args.sizes else DEFAULT_SIZES
    wanted = args.scenario or (list(FAST) if args.fast else list(SCENARIOS))

    # a run is a table; an engine narrating every store it opens buries it.
    # done here and not at import, so the suite that imports this module keeps
    # the logging its own tests assert on
    quieten(logging.ERROR)

    host = machine()
    print(f"\nprojectBEA bench — {host['os']} {host['arch']}, python {host['python']}, "
          f"{host['cpu_count']} cpus, sqlite-vec {'on' if host['sqlite_vec'] else 'off'}, "
          f"commit {host['commit']}\n")

    results: List[Result] = []
    for name in wanted:
        if name not in SCENARIOS:
            print(f"  ? unknown scenario {name!r}")
            continue
        print(f"{name}:")
        try:
            rows = SCENARIOS[name](sizes=sizes)
        except Exception as e:
            rows = [skipped(name, "", f"{type(e).__name__}: {e}")]
        for row in rows:
            print(row.row())
        results.extend(rows)
        print()

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"machine": host, "iterations": ITERATIONS,
             "results": [r.as_dict() for r in results]}, indent=2), encoding="utf-8")
        print(f"written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
