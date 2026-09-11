# Updating

← [Back to README](../README.md) | [Setup →](setup.md) | [Configuration →](configuration.md)

---

## Why `git pull` is not the update command

Six files under `data/prompts/` are tracked by git *and* meant to be edited by
the person running the engine:

| File | Read by | What an edit means |
|---|---|---|
| `soul.md` | every context, via `persona_store` | prose the user wrote; the character |
| `operating.md` | `src/core/mind/operating.py` | the speak tool, moods, how perception is phrased |
| `chat.md` | fallback when the operating manual is absent | legacy system prompt |
| `monologue.md` | the monologue skill | what she says into silence |
| `minecraft.md`, `minecraft_body.md` | the Minecraft agent | goal reasoning and the body loop |

`soul.md` is content and `operating.md` is machinery, but both ship with the
repository and both keep changing upstream. That combination is what breaks a
plain pull: git either refuses the merge, or writes `<<<<<<<` conflict markers
into a file that `src/utils/prompts.py:load_text` will read verbatim into a
system prompt on the next turn. The second outcome is silent — she simply starts
behaving strangely.

Everything else a user owns is already outside git: `.env`, `config.json`,
`data/bea.db`, `data/conversations/`, `data/models/`, `data/clips/` are all
ignored, and `BrainConfig.load_from_file` deep-merges `config.json` over the
dataclass defaults, so settings added upstream appear without migration. The
updater exists for the prompts, and for the rebuild steps a pull leaves undone.

---

## The state a file can be in

```
                 │ upstream unchanged │ upstream changed
 ────────────────┼────────────────────┼──────────────────
  user untouched │ nothing to do      │ git updates it
  user edited    │ keep theirs        │ three-way merge
```

The bottom-right cell is the whole feature. Both naive answers are wrong: taking
upstream discards the character someone wrote, keeping the local copy freezes
`operating.md` at whatever it was the first time it was touched, so the engine's
own instructions stop improving while the engine does not.

`src/core/update/reconcile.py` runs `git merge-file` per file with three inputs —
the user's version, the version it was based on, the new version — and produces
one of five outcomes:

| Outcome | Meaning | Base advances |
|---|---|---|
| `untouched` | the local edit is byte-identical to the new version | yes |
| `kept` | upstream did not change this file | yes |
| `merged` | both sides changed, disjoint regions, combined | yes |
| `conflict` | both sides changed overlapping lines | **no** |
| `removed` | upstream deleted the file; the local copy stands | no |

### The conflict rule

On `conflict` the user's file is written back byte-for-byte and the new version
is written beside it as `<name>.new`. Conflict markers are never written into a
prompt — a marker in `soul.md` is not a merge to resolve later, it is a system
prompt containing garbage.

`.new` is tool-owned: regenerated on every update, overwritten rather than
accumulated, deleted the moment the file stops conflicting or a decision is
recorded. It is always reproducible with `git show HEAD:<path>`, so nothing is
lost by replacing it.

---

## The base map

A three-way merge needs a base, and the base is **not** `HEAD`. If an update
conflicts and nobody resolves it, that file is still built on the revision from
before that update. Merging the next update from the new `HEAD` would present
the changes the user never took as deletions the user made, and drop them for
good — the second time, silently.

Git cannot supply this: to git the file is simply modified. So it is recorded in
`data/.prompt_base.json` (untracked):

```json
{ "format": 1, "bases": { "data/prompts/operating.md": "a1b2c3…" } }
```

Rules, in `runner._base_for` and `reconcile`:

* recorded → use it
* no record, no `.new` beside the file → the pre-merge `HEAD`. A checkout nobody
  has updated holds files that came out of the commit it sits on, so that commit
  *is* the base. Without this, the first update of every install would conflict.
* no record, `.new` present → refuse to merge. A pending conflict is on disk, we
  do not know what it was based on, and guessing `HEAD` is the data loss above.
* on conflict the base is rewritten unchanged, not omitted — an absent entry
  would later be read as "based on whatever `HEAD` is now".

The base also advances on an explicit resolution, which is the only place a
human decides instead of the merge. Without that endpoint, someone who
reconciles by hand leaves no trace, and the next update replays changes their
file already contains.

---

## The run

`src/core/update/runner.py:apply`. Seven steps, named once in `STEPS` and
rendered by both the terminal and the dashboard.

| Step | Does | Refuses when |
|---|---|---|
| `preflight` | recovers an interrupted run, classifies local changes | not a git checkout, no `origin`, detached HEAD, Docker, git missing, **any modified tracked file outside `data/prompts/`** |
| `download` | `fetch` (un-shallowing a `--depth 1` clone first), resolves the target | the target is not a descendant of `HEAD` — a diverged checkout is reported, never rewritten |
| `backup` | snapshots edited prompts, `config.json`, `.env` and the database; opens the journal | — |
| `apply` | re-reads the prompts, `checkout HEAD -- data/prompts`, `merge --ff-only` | a prompt changed between the first read and this one |
| `reconcile` | three-way merge per file, writes the base map, closes the journal | — |
| `dependencies` | `uv sync`, when `uv.lock` or `pyproject.toml` changed | `uv` not on PATH — reported, run continues |
| `dashboard` | `npm install && npm run build`, when `src/web/frontend/` changed | `npm` not on PATH — reported, run continues |

The target is the tracking branch (`@{u}`), falling back to `origin/main`. The
merge is `--ff-only`: there is no scenario in which the updater creates a merge
commit in somebody's install.

The last two steps can fail without failing the run. Rolling back a successful
fast-forward because `npm` is missing would trade a small problem for a large
one, so the report says which steps ran and the exit code is non-zero.
`src/web/frontend/dist/` is gitignored, so **skipping the rebuild leaves the old
dashboard on screen** — that is why a missing `npm` is reported loudly rather
than ignored.

### Refusals

Local modifications to tracked files outside `data/prompts/` abort the run with
the list. The updater merges prose, not source: if someone has patched the
engine, that is their patch to reconcile.

### Interruption

`data/.update.journal.json` records the phase before it starts and is deleted on
success. Only `reset`, `merge` and `reconcile` leave the working copy holding
something the user did not write; finding a journal in one of those phases makes
the next run restore the snapshot before doing anything else. A crash anywhere
else left the files alone and only the journal is cleared.

### Concurrency

`data/.update.lock` is created with `O_EXCL`, carries the pid and the source
(`cli` / `dashboard`), and expires by age after 45 minutes. Liveness is
deliberately not checked: `os.kill(pid, 0)` does not probe on Windows, it
terminates.

Two narrower races are handled in the run itself:

* **A prompt saved mid-update.** The dashboard can write `soul.md` at any moment,
  including between the updater reading it and handing the path to
  `git checkout`. The contents are re-read immediately before the reset and the
  run aborts if anything drifted.
* **A torn read.** `persona_store.SoulFile.write` and every write the updater
  makes go through `src/utils/files.py:atomic_write_text` (temp file in the same
  directory, `os.replace`), so a reader sees the old file or the new one, never
  a truncated one.

A check that runs while the lock is held skips the fetch rather than reading
refs another process is rewriting.

---

## Entry points

```bash
make update                     # uv run bea --update
uv run bea --update --no-rebuild   # git half only
```

`--update` is dispatched in `src/cli.py:run` before the engine is imported, for
the same reason `--setup` and `--doctor` are: it exists to repair the tree
everything else is imported from.

### HTTP

All under `src/web/updates.py`, mounted before the SPA catch-all.

| Endpoint | Notes |
|---|---|
| `GET /update?force=` | availability, `can_apply`, pending reviews, the live run. Cached 30 min server-side |
| `POST /update/check` | forces a fetch |
| `POST /update/apply` | 202; runs on a worker thread. 409 when one is in flight, 403 when disabled |
| `GET /update/run` | step-by-step progress, then the finished report |
| `GET /update/reviews` | files carrying a `.new` |
| `GET /update/reviews/{name}` | both versions, for the diff view |
| `POST /update/reviews/{name}` | `{"choice": "mine" \| "theirs"}` — advances the base, clears the `.new`, reloads the config |

`{name}` is matched against the list of files the updater itself flagged; a name
from the browser is never joined onto a path. The run is threaded because it
blocks on git, uv and npm for minutes, and the event loop is also drawing the
progress bar for that run.

`POST /update/apply` executes code. It is loopback-only like the rest of the
API, it refuses to touch anything modified outside `data/prompts/`, and it can
be switched off entirely:

```json
"updates": { "check": true, "allow_web_apply": true }
```

`check` is the only part that reaches the network, and only to the remote the
copy was cloned from. `allow_web_apply` closes the dashboard door without
affecting `make update`.

---

## Files on disk

| Path | Lifetime |
|---|---|
| `data/.prompt_base.json` | permanent; losing it costs one manual reconciliation |
| `data/prompts/*.new` | until the conflict is settled |
| `data/.backups/<utc-stamp>/` | last 8 runs; carries `manifest.json` with the base sha |
| `data/.update.lock` | duration of a run, or 45 minutes |
| `data/.update.journal.json` | duration of a run |

The database is copied with the SQLite backup API rather than `cp`: the engine
holds it open in WAL mode, so the file on disk is missing whatever is still in
the log.

---

## What it does not do

* **Restart her.** The new code is on disk; the running process keeps the old
  one until someone restarts it. A self-`exec` from inside the request that
  triggered it races the memory flush in `cli.main`'s `finally` block, which is
  worse than a banner saying "restart to finish".
* **Merge anything outside `data/prompts/`.**
* **Rewrite history, stash, or create merge commits.** `git stash pop` writes
  conflict markers on collision, which is the one outcome forbidden here.
* **Work in Docker.** The source tree is the image; the update is
  `docker compose build`.

---

## Version

`src/core/update/version.py` reads the installed package metadata, falling back
to `pyproject.toml`. It is the single source of truth: `GET /status` carries it
and the dashboard renders what it is told. The dashboard used to hardcode its
own string, which disagreed with `pyproject.toml` — two version numbers is the
same as none, and an update check has nothing to compare against.
