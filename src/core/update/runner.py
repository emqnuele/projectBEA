"""The update itself: what it checks, in what order, and what it refuses to do.

Two commitments shape everything below.

**Nothing the user wrote is ever lost.** Their prompts are read, backed up and
put back through a three-way merge; anything else of theirs that git tracks and
they have modified stops the run instead of being merged behind their back. The
update is fast-forward only, so a diverged checkout is reported rather than
rewritten. Every run is journalled, so one that dies halfway is undone by the
next one.

**Nothing happens halfway without saying so.** The git half and the rebuild half
can fail independently — a fetch can die on the network, `npm` can be missing
entirely — and rolling a successful fast-forward back because the dashboard did
not rebuild would trade a small problem for a large one. So each step reports
itself, and the report says plainly which ones ran.

The steps are a fixed sequence, named once here, because the terminal and the
dashboard both draw their progress from it.
"""

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from src.core.update import backup, lock, state
from src.core.update.gitrepo import GitError, Repo
from src.core.update.reconcile import (
    CONFLICT,
    PROMPTS,
    Outcome,
    new_file_for,
    pending_reviews,
    reconcile,
)
from src.core.update.version import current_version
from src.setup.node import PROJECTS as NODE_PROJECTS
from src.setup.node import executable
from src.utils.logger import get_logger

logger = get_logger("bea.update")

ROOT = Path(__file__).resolve().parents[3]

# how long a check is trusted before the remote is asked again. The dashboard
# polls; without this a tab left open all day is a fetch every few minutes.
CHECK_TTL = 30 * 60

# generous on purpose: a cold `uv sync` pulls a few hundred MB, and a first
# `npm install` on a slow link is measured in minutes, not seconds
DEPENDENCY_TIMEOUT = 30 * 60

# the node projects contribute a step each, so adding one is a line in
# `setup/node.py` rather than four scattered through here
STEPS: List[tuple] = [
    ("preflight", "Checking your install"),
    ("download", "Downloading the new version"),
    ("backup", "Backing up your files"),
    ("apply", "Applying the update"),
    ("reconcile", "Putting your edits back"),
    ("dependencies", "Updating dependencies"),
] + [(p.name, f"Updating the {p.name}") for p in NODE_PROJECTS]

RUNNING, DONE, SKIPPED, FAILED = "running", "done", "skipped", "failed"

# what the run as a whole came to
UPDATED, CURRENT, BLOCKED, FAILED_RUN = "updated", "up-to-date", "blocked", "failed"


@dataclass
class Step:
    id: str
    label: str
    status: str
    detail: str = ""

    def describe(self) -> dict:
        return {"id": self.id, "label": self.label, "status": self.status, "detail": self.detail}


@dataclass
class Report:
    status: str
    headline: str
    detail: str = ""
    steps: List[Step] = field(default_factory=list)
    prompts: List[Outcome] = field(default_factory=list)
    commits: List[dict] = field(default_factory=list)
    blocked_paths: List[str] = field(default_factory=list)
    from_sha: str = ""
    to_sha: str = ""
    backup: str = ""
    restart_required: bool = False

    @property
    def ok(self) -> bool:
        return self.status in (UPDATED, CURRENT)

    @property
    def reviews(self) -> List[Outcome]:
        return [p for p in self.prompts if p.needs_review]

    def describe(self) -> dict:
        return {
            "status": self.status,
            "ok": self.ok,
            "headline": self.headline,
            "detail": self.detail,
            "steps": [s.describe() for s in self.steps],
            "prompts": [p.describe() for p in self.prompts],
            "commits": self.commits,
            "blocked_paths": self.blocked_paths,
            "from": self.from_sha[:8],
            "to": self.to_sha[:8],
            "backup": self.backup,
            "restart_required": self.restart_required,
            "needs_review": len(self.reviews),
        }


@dataclass
class Availability:
    """What a check found, without changing anything."""

    supported: bool
    reason: str = ""
    behind: int = 0
    current: str = ""
    latest: str = ""
    version: str = ""
    commits: List[dict] = field(default_factory=list)
    reviews: List[str] = field(default_factory=list)
    busy: bool = False
    checked_at: float = 0.0

    @property
    def available(self) -> bool:
        return self.supported and self.behind > 0

    def describe(self) -> dict:
        return {
            "supported": self.supported,
            "available": self.available,
            "reason": self.reason,
            "behind": self.behind,
            "current": self.current[:8],
            "latest": self.latest[:8],
            "version": self.version,
            "commits": self.commits,
            "reviews": self.reviews,
            "busy": self.busy,
            "checked_at": self.checked_at,
        }


Progress = Callable[[Step], None]


def _noop(step: Step) -> None:
    pass


# --- is this install even updatable ------------------------------------------


def in_docker() -> bool:
    """Inside a container the source tree is the image, so pulling it is theatre."""
    return Path("/.dockerenv").exists() or os.getenv("BEA_IN_DOCKER") == "1"


def _unsupported(repo: Repo) -> str:
    """The reason this checkout cannot be updated in place, or an empty string."""
    if in_docker():
        return "She is running in Docker, where the update is a rebuild of the image."
    if not repo.available():
        return "git is not installed, so there is nothing to pull with."
    if not repo.is_repo():
        return "This is not a git checkout — it was most likely downloaded as a zip."
    if not repo.has_remote():
        return "This checkout has no `origin` remote to pull from."
    if repo.branch() is None:
        return "This checkout is on a detached HEAD. Check out a branch first."
    return ""


def supported(root: Path = ROOT) -> str:
    """Why this install cannot update itself, or an empty string when it can.

    Public because the diagnostic asks the same question, and reaching into a
    private helper to answer it is how the two end up disagreeing.
    """
    return _unsupported(Repo(root))


def _target_ref(repo: Repo) -> str:
    """What we are updating towards: the tracking branch, or origin's main."""
    return repo.upstream() or "origin/main"


# --- checking ----------------------------------------------------------------

_cached: Optional[Availability] = None


def check(root: Path = ROOT, force: bool = False, fetch: bool = True) -> Availability:
    """Asks the remote whether there is anything new. Cached, because tabs stay open."""
    global _cached

    if _cached and not force and time.time() - _cached.checked_at < CHECK_TTL:
        return _cached

    repo = Repo(root)
    reason = _unsupported(repo)
    if reason:
        _cached = Availability(supported=False, reason=reason, version=current_version(),
                               checked_at=time.time())
        return _cached

    busy = lock.holder(root) is not None
    result = Availability(supported=True, version=current_version(), busy=busy, checked_at=time.time())

    try:
        # an update running right now is rewriting the very refs we would read
        if fetch and not busy:
            if repo.is_shallow():
                repo.unshallow()
            repo.fetch()

        result.current = repo.head()
        target = repo.resolve(_target_ref(repo))
        if not target:
            result.supported = False
            result.reason = f"Could not find `{_target_ref(repo)}` — is the remote reachable?"
            _cached = result
            return result

        result.latest = target
        result.behind = repo.count_between(result.current, target)
        result.commits = [c.describe() for c in repo.commits_between(result.current, target)]
        result.reviews = pending_reviews(root, repo)
    except GitError as e:
        result.supported = False
        result.reason = str(e)

    _cached = result
    return result


def invalidate() -> None:
    """Forgets the cached check. Called whenever we ourselves moved the repo."""
    global _cached
    _cached = None


# --- updating ----------------------------------------------------------------


def apply(root: Path = ROOT, source: str = "cli", progress: Progress = _noop,
          rebuild: bool = True) -> Report:
    """Runs the whole update. Never raises for an expected failure — it reports it."""
    root = Path(root)
    repo = Repo(root)
    steps: List[Step] = []

    def step(step_id: str, status: str, detail: str = "") -> Step:
        label = dict(STEPS)[step_id]
        entry = Step(step_id, label, status, detail)
        # a step reported twice is the same step changing state, not a new one
        for index, existing in enumerate(steps):
            if existing.id == step_id:
                steps[index] = entry
                break
        else:
            steps.append(entry)
        progress(entry)
        return entry

    try:
        with lock.held(root, source):
            return _run(root, repo, step, steps, rebuild)
    except lock.UpdateBusy as e:
        return Report(status=BLOCKED, headline="An update is already running", detail=str(e), steps=steps)
    except GitError as e:
        logger.error(f"Update failed: {e}")
        return Report(status=FAILED_RUN, headline="The update could not finish", detail=str(e), steps=steps)
    except Exception as e:  # noqa: BLE001 - the last line before a 500
        logger.exception("Unexpected failure during update")
        return Report(status=FAILED_RUN, headline="The update could not finish",
                      detail=f"{type(e).__name__}: {e}", steps=steps)


def _run(root: Path, repo: Repo, step, steps: List[Step], rebuild: bool) -> Report:
    # --- 1. preflight --------------------------------------------------------
    step("preflight", RUNNING)

    recovered = backup.recover(root)
    if recovered:
        step("preflight", RUNNING, f"Recovered {len(recovered)} file(s) from an interrupted update")

    reason = _unsupported(repo)
    if reason:
        step("preflight", FAILED, reason)
        return Report(status=BLOCKED, headline="This install cannot update itself",
                      detail=reason, steps=steps)

    # anything of theirs outside the prompts is code, and code is not ours to merge
    blocked = [p for p in repo.modified_tracked() if not p.startswith(f"{PROMPTS}/")]
    if blocked:
        detail = ("These tracked files have local changes. Commit, stash or revert them and "
                  "run the update again.")
        step("preflight", FAILED, detail)
        return Report(status=BLOCKED, headline="You have local changes to the engine itself",
                      detail=detail, steps=steps, blocked_paths=blocked)

    base_sha = repo.head()
    edited = repo.modified_tracked(PROMPTS)
    ours = _read_all(root, edited)
    step("preflight", DONE,
         f"{len(edited)} edited prompt(s) to preserve" if edited else "no local edits to preserve")

    # --- 2. download ---------------------------------------------------------
    step("download", RUNNING)
    if repo.is_shallow():
        repo.unshallow()
    repo.fetch()
    target = repo.resolve(_target_ref(repo))
    if not target:
        detail = f"Could not resolve `{_target_ref(repo)}` after fetching."
        step("download", FAILED, detail)
        return Report(status=FAILED_RUN, headline="The new version could not be found",
                      detail=detail, steps=steps)

    if target == base_sha:
        step("download", DONE, "already on the latest version")
        for pending in ("backup", "apply", "reconcile", "dependencies",
                        *(p.name for p in NODE_PROJECTS)):
            step(pending, SKIPPED, "nothing to update")
        return Report(status=CURRENT, headline="She is already up to date",
                      steps=steps, from_sha=base_sha, to_sha=target)

    if not repo.is_ancestor(base_sha, target):
        detail = ("Your checkout has commits that are not upstream, so this cannot be a "
                  "fast-forward. Merge or reset it by hand.")
        step("download", FAILED, detail)
        return Report(status=BLOCKED, headline="Your checkout has diverged",
                      detail=detail, steps=steps, from_sha=base_sha, to_sha=target)

    commits = [c.describe() for c in repo.commits_between(base_sha, target)]
    step("download", DONE, f"{repo.count_between(base_sha, target)} new commit(s)")

    # --- 3. backup -----------------------------------------------------------
    step("backup", RUNNING)
    snapshot = backup.take(root, edited, base_sha)
    backup.open_journal(root, "reset", snapshot, base_sha, edited)
    step("backup", DONE, f"saved to {backup.BACKUP_ROOT}/{snapshot.name}")

    # --- 4. apply ------------------------------------------------------------
    step("apply", RUNNING)
    # last look before anything is destroyed: if a prompt changed underneath us
    # between the read and now, the snapshot is already out of date
    drifted = [p for p, text in ours.items() if _read(root / p) != text]
    if drifted:
        backup.close_journal(root)
        detail = f"{', '.join(drifted)} changed while the update was preparing. Nothing was touched."
        step("apply", FAILED, detail)
        return Report(status=BLOCKED, headline="Something edited a prompt mid-update",
                      detail=detail, steps=steps, blocked_paths=drifted,
                      backup=snapshot.name)

    repo.checkout_paths(edited)
    backup.mark_phase(root, "merge")
    repo.merge_ff_only(target)
    invalidate()
    step("apply", DONE, f"now on {target[:8]}")

    # --- 5. reconcile --------------------------------------------------------
    step("reconcile", RUNNING)
    backup.mark_phase(root, "reconcile")
    outcomes = _reconcile_all(root, repo, ours, base_sha, target)
    backup.close_journal(root)

    conflicts = [o for o in outcomes if o.state == CONFLICT]
    if conflicts:
        step("reconcile", DONE, f"{len(conflicts)} file(s) need your eyes")
    else:
        step("reconcile", DONE,
             f"{len(outcomes)} edited prompt(s) preserved" if outcomes else "no local edits to restore")

    # --- 6 & 7. dependencies and the dashboard -------------------------------
    changed = repo.changed_between(base_sha, target)
    if rebuild:
        _sync_dependencies(root, changed, step)
        _rebuild_node(root, changed, step)
    else:
        step("dependencies", SKIPPED, "asked to skip")
        for project in NODE_PROJECTS:
            step(project.name, SKIPPED, "asked to skip")

    headline = "Updated" if not conflicts else "Updated — some prompts need a look"
    return Report(
        status=UPDATED,
        headline=headline,
        detail=f"{len(commits)} commit(s) applied.",
        steps=steps,
        prompts=outcomes,
        commits=commits,
        from_sha=base_sha,
        to_sha=target,
        backup=snapshot.name,
        restart_required=True,
    )


def _base_for(root: Path, path: str, bases: state.BaseMap, head: str) -> Optional[str]:
    """Which revision this file's contents are built on.

    Recorded, when we have a record — which is not HEAD whenever an earlier
    conflict was left unresolved. Otherwise it depends on why there is no
    record, and an unresolved conflict leaves a `.new` on disk that says so
    independently of the state file. Without one, the file was checked out at
    the revision they are on and edited from there, which is every install that
    has never updated before; with one, we know their file predates something
    and not what, so the merge is refused rather than guessed.
    """
    recorded = bases.get(path)
    if recorded:
        return recorded
    return None if new_file_for(root, path).exists() else head


def _reconcile_all(root: Path, repo: Repo, ours: Dict[str, str], base_sha: str, target: str) -> List[Outcome]:
    bases = state.load(root)
    outcomes: List[Outcome] = []

    for path, text in ours.items():
        outcome = reconcile(root, repo, path, text, _base_for(root, path, bases, base_sha), target)
        outcomes.append(outcome)
        if outcome.base:
            bases.set(path, outcome.base)
        logger.info(f"{path}: {outcome.state} — {outcome.detail}")

    # files nobody edited are simply on the new version now
    for path in repo.tracked_under(PROMPTS):
        if path not in ours:
            bases.set(path, target)

    state.save(root, bases)
    return outcomes


# --- the rebuild half --------------------------------------------------------


def _sync_dependencies(root: Path, changed: List[str], step) -> None:
    if not any(p in ("uv.lock", "pyproject.toml") for p in changed):
        step("dependencies", SKIPPED, "no dependency changes in this update")
        return
    if not shutil.which("uv"):
        step("dependencies", FAILED, "uv is not on PATH — run `uv sync` yourself before starting her")
        return

    step("dependencies", RUNNING)
    ok, detail = _command(root, ["uv", "sync"])
    step("dependencies", DONE if ok else FAILED, detail if not ok else "python dependencies are current")


def _rebuild_node(root: Path, changed: List[str], step) -> None:
    """Every javascript part of her, not only the one you can see.

    The discord bot was left out of this for as long as it existed: an update
    that changed its packages left the skill switched on in the UI and the bot
    unable to start, saying so nowhere but its own stderr.
    """
    for project in NODE_PROJECTS:
        if not any(p.startswith(project.path + "/") for p in changed):
            step(project.name, SKIPPED, f"the {project.name} did not change in this update")
            continue
        if not shutil.which("npm"):
            # what npm builds is gitignored, so without this the user updates
            # and gets the old screens — or no voice — with no clue why
            step(project.name, FAILED,
                 f"npm is not on PATH — run `uv run bea --install-node` yourself, "
                 f"or the {project.name} stays as it was")
            continue

        step(project.name, RUNNING, "installing")
        ok, detail = _command(project.directory(root), ["npm", "install", "--no-audit", "--no-fund"])
        if ok and project.builds:
            step(project.name, RUNNING, "building")
            ok, detail = _command(project.directory(root), ["npm", "run", "build"])
        step(project.name, DONE if ok else FAILED,
             detail if not ok else f"the {project.name} is current")


def _command(cwd: Path, args: List[str]) -> tuple:
    """Runs one build command. Returns (ok, the last thing it said when it failed)."""
    # under the name this machine gave it: npm is `npm.cmd` on windows, which
    # subprocess cannot find by its bare name
    program = executable(args[0])
    if program is None:
        return False, f"{args[0]} is not installed"
    try:
        result = subprocess.run(
            [program, *args[1:]], cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=DEPENDENCY_TIMEOUT,
        )
    except FileNotFoundError:
        return False, f"{args[0]} is not installed"
    except subprocess.TimeoutExpired:
        return False, f"`{' '.join(args)}` did not finish within {DEPENDENCY_TIMEOUT // 60} minutes"

    if result.returncode == 0:
        return True, ""
    tail = (result.stderr or result.stdout or "").strip().splitlines()
    return False, f"`{' '.join(args)}` failed: " + (tail[-1] if tail else f"exit code {result.returncode}")


# --- small file helpers ------------------------------------------------------


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_all(root: Path, paths: List[str]) -> Dict[str, str]:
    contents = {}
    for relative in paths:
        text = _read(Path(root) / relative)
        if text is not None:
            contents[relative] = text
    return contents
