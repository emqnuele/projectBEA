# Performance

← [Back to README](../README.md) | [Architecture](architecture.md)

How the engine is measured, what it costs, and which of the obvious
optimisations turned out not to be worth doing. Every number on this page came
out of `tools/bench.py` on a real machine, and nothing here is an estimate.

---

## The rule

**No performance change lands without a before and an after from the harness.**

The live database on a working install holds a handful of rows. At that size
every retrieval path is instant, and the one that scales badly is
indistinguishable from the one that does not — which is exactly how a dead fast
path survived in this codebase for months with a green test suite. Guessing is
not allowed to be the thing anyone acts on.

---

## Running it

```bash
uv run python tools/bench.py                       # everything this machine can run
uv run python tools/bench.py --fast                # only what needs no model
uv run python tools/bench.py --scenario recall --sizes 1000,50000
uv run python tools/bench.py --json after.json     # keep the numbers
```

`--fast` is the reproducible subset: it needs neither a downloaded model nor a
network, so a contributor gets comparable numbers on a clean checkout.

### Method

| | |
|---|---|
| Warmup | 3 iterations, discarded — sqlite pages, ONNX arenas and bytecode all warm up |
| Measured | 30 iterations (fewer for the scenarios that rewrite a whole store) |
| Reported | **p50 and p95**, never a mean |
| Corpus | synthetic, seeded, on disk — never `:memory:`, because WAL and mmap are part of what is measured |
| Vectors | random, not embedded — the model is measured in its own scenario, where it is the thing under test |

The corpus mirrors the real shape: one scope, one `scope_key` per session,
~50 sessions, timestamps spread over 400 days so the recency half of the
ranking is genuinely exercised.

### Scenarios

| Scenario | What it answers |
|---|---|
| `recall` | retrieval narrowed to one session — what the tests exercise |
| `recall_nofilter` | retrieval across every session — **what production actually calls** |
| `remember` | the cost of writing one memory and indexing it |
| `reembed` | the bulk path, which runs inside startup when the model changed |
| `forget` | deleting a scope and its vectors |
| `startup` | opening the store and wiring recall, with the real embedder |
| `embed` | the real model, one text and a batch of 32 |
| `history` | appending one message to a session that already has some |
| `turnlog` | writing one turn down |
| `stt` | local whisper on a sample wav, when one is present |

Each retrieval row is run **twice in the same process**, once with the vector
index and once forced onto the pure-python path, so the two are comparable
without a second run and a second machine.

---

## Baseline

`Darwin arm64`, 10 cpus, python 3.12, sqlite-vec on. p50, milliseconds.

| Scenario | size | before | after |
|---|---|---|---|
| `recall` (one session) | 10 000 | 4.756 py / 0.571 vec | 0.678 py / 0.432 vec |
| `recall_nofilter` (production) | 1 000 | 24.547 py / 24.578 vec | 2.306 py / 0.345 vec |
| `recall_nofilter` (production) | 10 000 | 245.141 py / 246.002 vec | 26.961 py / 3.670 vec |
| `remember` | into 10 000 | 0.064 | 0.070 |
| `reembed_all` | 10 000 | 851.336 | 405.893 |
| `startup` | — | 255.708 | 1.374 |
| `embed` 1 text | — | 2.108 | 2.923 |
| `embed` 32 texts | — | 39.661 | 66.577 |
| `history_append` | session of 2 000 | 3.041 | 0.001 |
| `turnlog_write` | one turn | 0.029 | 0.029 |

### What the baseline says

**The vector index was not being used.** `recall_nofilter` costs the same with
sqlite-vec on and off, to three significant figures, at every size. That is not
a slow index — it is an index the query never reaches. Production passes a
`scope` and no `scope_key`; the old code required both before it would use the
fast path, so every recall a user ever triggered went down the full scan.
`recall`, which does pass a `scope_key`, shows what the index is worth when the
query can actually reach it: **4.756 ms → 0.571 ms** at 10 000 rows.

**Startup was not lazy.** `embed_dim` — reading the width of the embedding model
— cost 257 ms, and `startup` cost 255 ms. They are the same number because they
were the same work: `Rag.__init__` asked the embedder for its width, which
loaded the model. On a warm cache that is a quarter of a second; on a fresh
install it is a 220 MB download, in startup, which the module docstring
promised would never happen.

**Two suspects were acquitted.** Writing a turn down costs 29 µs and embedding
one sentence costs 2.1 ms. Neither is worth touching, and both had been
proposed as optimisation targets before they were measured.

---

## Voice detector

The Discord voice detector (`VoiceActivity` + `SpeechBuffer`, see
[Discord](skills/discord.md#voice-input-turn-segmentation)) has its own
harness. The voice path is Node, and what matters there is turns, not
milliseconds per call.

```bash
uv run python tools/vad_bench/corpus.py   # 15 scenarios, ~95 s each, into data/vad_bench/
node tools/vad_bench/bench.js             # --hangovers 500,400 --json out.json
```

**Corpus.** Sixteen turns from six edge-tts voices (Italian and English), from
"Sì." to a 7-second story with pauses inside it, 1.6–3.2 s apart. The same
timeline runs under every background: clean, fan, hiss, keyboard and tonal
music with a beat, at 15 and 5 dB SNR; the same noise with nobody talking; and
a speaker 20 dB quieter. Ground truth comes from the clean track (−40 dB from
the peak). Six of the sixteen turns contain a pause of about a second, so any
500 ms hangover splits them: six splits per scenario are the floor.

**Path.** Each 20 ms frame goes through Opus at 64 kbps and back, then into the
real `SpeechBuffer` with the sweep on the same clock. "Open" is a microphone
that always transmits. "Gated" is Discord's own voice activity closing the
stream (an assumed 300 ms release). End = time from the true end of speech
until the turn is sent.

The harness also plays the clean track 20, 25 and 30 dB quieter while she
is talking: her own voice leaking back through a headset, or a television in
somebody's room. Every duck or turn out of that is her being cut off by
something nobody said to her.

`Apple M5`, node 24, hangover 500 ms, open microphone unless noted.

| | result |
|---|---|
| end p50 / p95, clean + mild noise | 464 / 1140 ms |
| end p50 / p95, heavy noise (5 dB) | 433 / 2300 ms |
| noise interrupting her, noise only | 0 |
| her voice leaking back at −20 / −25 / −30 dB: ducks | 6 / 0 / 0 |
| turns missed, clean + mild noise (64) | 8 |
| turns missed, quiet speaker (32) | 23 |
| cpu per second of audio | 1.2 ms |

### Known limits

- **One-word answers.** Only vowels count as voice (an s sits above the speech
  band and looks like hiss), and the onset is not counted. A quick "sì" or
  "yeah" can fall under `MIN_SPEECH_MS` and be dropped. Counting them sends
  fillers ("hmm", "ehm") as turns of their own too, and she answers those.
  That only works once a filler followed by more speech can be joined to it.
- **Quiet speakers.** A voice 20 dB under the rest is kept out by
  `ENTER_MARGIN`, the same margin that keeps her echo out. The two are the same
  signal, and the echo is the one that breaks a call.
- **Music with a strong beat** under a voice can merge two turns. The level
  is measured over the full band, so a kick drum at 55 Hz counts as loudness.

---

## Rejected optimisations

Kept here with their numbers so they are not proposed again.

### CoreML for embeddings (macOS)

`onnxruntime` on macOS already ships `CoreMLExecutionProvider` — no extra
package is needed, and the provider can simply be requested. It does not help:

| | CPU | CoreML |
|---|---|---|
| load | 0.37 s | 0.53 s |
| 1 text | 2.0 ms | 2.0 ms |
| 32 texts | 40.7 ms | 41.9 ms |

The model is a 12-layer MiniLM. It is small enough that the round trip to the
neural engine costs more than the work saved, and the session takes longer to
build. **Not adopted.**

### `onnxruntime-gpu` / `onnxruntime-directml` as optional extras

`onnxruntime` is a *transitive, mandatory* dependency of both `fastembed` and
`kokoro-onnx`. The GPU and DirectML builds are mutually exclusive with it, so an
extra that installs one replaces a package two other dependencies rely on —
the most likely single thing to break `uv sync --locked` across the three-OS CI
matrix. The payoff would be on a model that costs 2 ms a call.

**Not adopted.** The GPU win worth having is in whisper, and it needs no extra
package at all — see below.

### Dropping the `commit()` on read paths

`Database.query` committed after every `SELECT`. Removing it is worth
**0.2 µs per read** (1.3 µs → 1.1 µs). It was done anyway, because a commit
after a read is code that misstates its own intent, but it is not a
performance change and should not be described as one.

---

## Per-OS

There is very little, and that is the honest answer rather than a gap.

| Platform | What is actually different |
|---|---|
| Linux / Windows + NVIDIA | whisper runs on CUDA in `float16` instead of CPU `int8` |
| Windows | `mmap_size` is set lower (128 MB vs 256 MB) |
| macOS | nothing — the CPU path is already the fast one, see above |

The CUDA difference is resolved at runtime inside the process, not by the
installers. `install.sh` and `install.ps1` deliberately contain no hardware
detection: the same decision living in three places is how three places
disagree.

### Turning it all off

`BEA_PERF=off` disables every optimisation introduced for performance — the
vector path, thread tuning, device selection, and the debounced history writer —
and the engine runs the way it did before any of it. It exists so that a
regression can be bisected in one step, and CI runs the suite with it set.
