"""Putting a user's edited prompt back on top of a new version of the same file.

The prompts ship with the engine and are meant to be edited. `soul.md` is prose
the user writes; `operating.md` is machinery — the speak tool, the moods, how
perception is described — that keeps improving upstream. Both are versioned, so
an update can change a file the user has also changed, and the naive answers
are both wrong: taking theirs throws away the character someone wrote, keeping
ours freezes the engine's own instructions at whatever they were the day it was
first touched.

So every file gets a three-way merge — their version, the version they started
from, the new version — which is what git would do for a merge commit, run here
one file at a time so we decide what happens when it fails.

And when it fails there is exactly one rule, because a prompt is not source
code: **never write conflict markers into a file that goes into a system
prompt.** `<<<<<<<` in `soul.md` is not a merge to resolve later, it is a
character quietly going insane on stream. The user's file is left exactly as it
was and the new version is dropped beside it as `<name>.new` for them to read.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.core.update.gitrepo import GitError, Repo
from src.utils.files import atomic_write_text
from src.utils.logger import get_logger

logger = get_logger("bea.update.reconcile")

# where the editable prompts live. Everything outside it is engine source: if
# the user has edited that, the update refuses to run rather than merge code.
PROMPTS = "data/prompts"

NEW_SUFFIX = ".new"

UNTOUCHED = "untouched"
KEPT = "kept"
MERGED = "merged"
CONFLICT = "conflict"
REMOVED = "removed"


@dataclass(frozen=True)
class Outcome:
    """What happened to one file, in terms a person can act on."""

    path: str
    state: str
    detail: str
    # the revision this file's contents are now built on, to be recorded. On a
    # conflict it is the base we merged *from*, unchanged — "does not advance"
    # has to be written down, because an absent record would later be read as
    # "based on whatever HEAD is now", which is the misreading this whole
    # module exists to avoid.
    base: Optional[str] = None

    @property
    def needs_review(self) -> bool:
        return self.state == CONFLICT

    def describe(self) -> dict:
        return {
            "path": self.path,
            "name": Path(self.path).name,
            "state": self.state,
            "detail": self.detail,
            "needs_review": self.needs_review,
        }


def _lf(text: str) -> str:
    """Line endings out of the way, so a merge is about the words.

    The three sides reach us having been read three different ways: the user's
    file through python's text mode, which turns CRLF into LF, and the other two
    straight out of git as bytes, which does not. On windows that made every
    line of every prompt differ from itself — so a clean merge came back as a
    conflict, and the engine's own improvements were dropped on the floor while
    the report said the user's edits had collided with them.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _newline(text: str) -> str:
    """What this file is written with, so a merge does not quietly convert it."""
    crlf = text.count("\r\n")
    return "\r\n" if crlf and crlf >= text.count("\n") - crlf else "\n"


def _as_written(text: str, newline: str) -> str:
    return text if newline == "\n" else text.replace("\n", newline)


def new_file_for(root: Path, path: str) -> Path:
    return Path(root) / (path + NEW_SUFFIX)


def pending_reviews(root: Path, repo: Repo) -> list:
    """Files sitting on an unresolved conflict, i.e. carrying a `.new` beside them."""
    found = []
    for path in repo.tracked_under(PROMPTS):
        if new_file_for(root, path).is_file():
            found.append(path)
    return sorted(found)


def reconcile(root: Path, repo: Repo, path: str, ours: str, base_sha: Optional[str], target: str) -> Outcome:
    """Restores the user's version of one file, merged with the new one where it can be.

    Called after the fast-forward, so the working copy holds the new version and
    `ours` is what was snapshotted before it was reset.
    """
    root = Path(root)
    theirs = repo.file_at(target, path)

    # whatever the user's file is written with survives whatever we decide
    style = _newline(ours)
    ours = _lf(ours)
    if theirs is not None:
        theirs = _lf(theirs)

    def write(destination: Path, text: str) -> None:
        _write(destination, _as_written(text, style))

    if theirs is None:
        # the new version does not have this file at all — deleted upstream, or
        # a blob we refuse to decode. Either way the user's copy is the only
        # one anybody asked for.
        write(root / path, ours)
        # the base stays where it was: if the file comes back upstream, their
        # edits still have something to be merged against
        return Outcome(path, REMOVED, "the new version no longer ships this file; yours was kept",
                       base=base_sha)

    if ours == theirs:
        _clear_new(root, path)
        return Outcome(path, UNTOUCHED, "already identical to the new version", base=target)

    base = repo.file_at(base_sha, path) if base_sha else None
    if base is not None:
        base = _lf(base)

    if base is None:
        # no usable base: either we never recorded one, or the revision is gone
        # from a shallow history. A two-way guess is exactly the silent data
        # loss this module exists to prevent, so hand both versions over.
        write(root / path, ours)
        write(new_file_for(root, path), theirs)
        return Outcome(
            path, CONFLICT,
            "there is no record of which version yours was based on, so it was left untouched",
            base=None,
        )

    if base == theirs:
        write(root / path, ours)
        _clear_new(root, path)
        return Outcome(path, KEPT, "the new version does not change this file", base=target)

    merged = _merge(repo, ours=ours, base=base, theirs=theirs)
    if merged is None:
        write(root / path, ours)
        write(new_file_for(root, path), theirs)
        return Outcome(
            path, CONFLICT,
            "your edits and the new version touch the same lines",
            base=base_sha,
        )

    write(root / path, merged)
    _clear_new(root, path)
    return Outcome(path, MERGED, "your edits were carried over onto the new version", base=target)


def resolve(root: Path, repo: Repo, path: str, choice: str, target: str) -> Outcome:
    """The human ending to a conflict, and the only other place a base advances.

    Without it, an update that conflicted stays conflicted forever: someone who
    reconciles by hand leaves no trace of having done so, and the next update
    would try to replay the same changes onto a file that already has them.
    """
    root = Path(root)
    if choice not in ("mine", "theirs"):
        raise ValueError(f"Unknown resolution: {choice}")

    incoming = new_file_for(root, path)
    if choice == "theirs":
        text = _read(incoming)
        if text is None:
            raise FileNotFoundError(f"There is no new version of {path} to take")
        _write(root / path, text)

    _clear_new(root, path)
    detail = ("the new version was taken" if choice == "theirs" else "your version was kept")
    return Outcome(path, KEPT if choice == "mine" else MERGED, detail, base=target)


# --- the merge itself --------------------------------------------------------


def _merge(repo: Repo, ours: str, base: str, theirs: str) -> Optional[str]:
    """`git merge-file` on three temporary files. None when the sides collide."""
    with tempfile.TemporaryDirectory(prefix="bea-merge-") as workspace:
        directory = Path(workspace)
        sides = {}
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            # all three arrive normalised to LF, and newline="" writes them out
            # unchanged: the merge compares words, and the caller puts the
            # user's own line endings back on whatever comes out of it
            sides[name] = directory / name
            sides[name].write_text(text, encoding="utf-8", newline="")
        try:
            return repo.merge_file(sides["ours"], sides["base"], sides["theirs"])
        except GitError as e:
            logger.error(f"merge-file failed, treating as a conflict: {e}")
            return None


def _write(path: Path, text: str) -> None:
    atomic_write_text(path, text)


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _clear_new(root: Path, path: str) -> None:
    """A resolved conflict must not leave its leftovers on disk.

    A stale `.new` is a file somebody opens six months later wondering whether
    they were supposed to do something with it.
    """
    new_file_for(root, path).unlink(missing_ok=True)
