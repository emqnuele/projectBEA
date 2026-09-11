"""Every call the updater makes to the git binary, and nothing else.

Keeping them here is not tidiness. Two of the arguments below are the
difference between an update and a hung dashboard: `GIT_TERMINAL_PROMPT=0` and
`ssh -oBatchMode=yes` mean a clone over SSH with a passphrase-protected key
fails in a second instead of waiting forever for a password nobody will ever
type into a web request. Scatter the subprocess calls and one of them will
eventually be written without those.

Nothing here decides anything: it answers questions about the repository and
performs the two writes the updater is allowed to make (`checkout` of paths it
has already backed up, and a fast-forward). The policy lives in `runner`.
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from src.utils.logger import get_logger

logger = get_logger("bea.update.git")

# a local git command answers in milliseconds; anything reaching the network
# gets its own, larger budget. Both exist so a wedged git never wedges the API.
LOCAL_TIMEOUT = 30
NETWORK_TIMEOUT = 180


class GitError(Exception):
    """A git command that failed, carrying what it printed."""

    def __init__(self, message: str, stderr: str = ""):
        super().__init__(message)
        self.message = message
        self.stderr = stderr.strip()

    def __str__(self) -> str:
        return f"{self.message}: {self.stderr}" if self.stderr else self.message


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    author: str
    date: str

    def describe(self) -> Dict[str, str]:
        return {"sha": self.sha[:8], "subject": self.subject, "author": self.author, "date": self.date}


def _environment() -> Dict[str, str]:
    env = dict(os.environ)
    # never ask a human anything: there is nobody at the other end of an HTTP
    # request, and an interactive prompt would hang until the timeout
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -oBatchMode=yes")
    # parsing porcelain output in the user's locale is a bug waiting for a
    # non-English machine
    env["LC_ALL"] = "C"
    return env


class Repo:
    """The working copy the engine is running from."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    # --- running git ---------------------------------------------------------

    def run(self, *args: str, timeout: int = LOCAL_TIMEOUT, check: bool = True) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=_environment(),
            )
        except FileNotFoundError as e:
            raise GitError("git is not installed, or not on PATH") from e
        except subprocess.TimeoutExpired as e:
            raise GitError(f"git {args[0]} timed out after {timeout}s") from e

        if check and result.returncode != 0:
            raise GitError(f"git {args[0]} failed", result.stderr or result.stdout)
        return result

    def out(self, *args: str, timeout: int = LOCAL_TIMEOUT) -> str:
        return self.run(*args, timeout=timeout).stdout.strip()

    def raw(self, *args: str, timeout: int = LOCAL_TIMEOUT) -> Optional[bytes]:
        """Bytes, undecoded. For blobs, where a lossy decode would be a silent edit."""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(self.root),
                capture_output=True,
                timeout=timeout,
                env=_environment(),
            )
        except FileNotFoundError as e:
            raise GitError("git is not installed, or not on PATH") from e
        except subprocess.TimeoutExpired as e:
            raise GitError(f"git {args[0]} timed out after {timeout}s") from e
        return result.stdout if result.returncode == 0 else None

    # --- what kind of checkout is this --------------------------------------

    def available(self) -> bool:
        try:
            self.run("--version")
            return True
        except GitError:
            return False

    def is_repo(self) -> bool:
        try:
            return self.out("rev-parse", "--is-inside-work-tree") == "true"
        except GitError:
            return False

    def is_shallow(self) -> bool:
        try:
            return self.out("rev-parse", "--is-shallow-repository") == "true"
        except GitError:
            return False

    def has_remote(self, name: str = "origin") -> bool:
        try:
            return name in self.out("remote").split()
        except GitError:
            return False

    def remote_url(self, name: str = "origin") -> str:
        try:
            return self.out("remote", "get-url", name)
        except GitError:
            return ""

    def branch(self) -> Optional[str]:
        """The current branch, or None on a detached HEAD."""
        name = self.out("rev-parse", "--abbrev-ref", "HEAD")
        return None if name == "HEAD" else name

    def upstream(self) -> Optional[str]:
        """The tracking branch, e.g. `origin/main`. None when there is none."""
        try:
            return self.out("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        except GitError:
            return None

    # --- reading -------------------------------------------------------------

    def head(self) -> str:
        return self.out("rev-parse", "HEAD")

    def resolve(self, rev: str) -> Optional[str]:
        try:
            return self.out("rev-parse", "--verify", f"{rev}^{{commit}}")
        except GitError:
            return None

    def modified_tracked(self, *paths: str) -> List[str]:
        """Tracked files that differ from HEAD, staged or not. Untracked are not ours."""
        args = ["diff", "--name-only", "HEAD", "--"]
        result = self.run(*args, *paths)
        return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})

    def changed_between(self, base: str, head: str, *paths: str) -> List[str]:
        result = self.run("diff", "--name-only", f"{base}..{head}", "--", *paths)
        return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})

    def tracked_under(self, prefix: str) -> List[str]:
        result = self.run("ls-files", "--", prefix)
        return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})

    def file_at(self, rev: str, path: str) -> Optional[str]:
        """The contents of one file at one revision, or None if it was not there.

        Also None when the blob is not valid UTF-8: a prompt that is not text is
        a prompt we refuse to merge rather than mangle.
        """
        blob = self.raw("show", f"{rev}:{path}")
        if blob is None:
            return None
        try:
            return blob.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(f"{path} at {rev[:8]} is not valid UTF-8; it will not be merged")
            return None

    def count_between(self, base: str, head: str) -> int:
        try:
            return int(self.out("rev-list", "--count", f"{base}..{head}"))
        except (GitError, ValueError):
            return 0

    def commits_between(self, base: str, head: str, limit: int = 50) -> List[Commit]:
        """Newest first. An empty list means nothing new, or a history too shallow to say."""
        try:
            result = self.run(
                "log", f"--max-count={limit}", "--no-merges",
                "--pretty=format:%H%x1f%s%x1f%an%x1f%cs", f"{base}..{head}",
            )
        except GitError:
            return []
        commits = []
        for line in result.stdout.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 4:
                commits.append(Commit(sha=parts[0], subject=parts[1], author=parts[2], date=parts[3]))
        return commits

    def is_ancestor(self, maybe_ancestor: str, head: str) -> bool:
        result = self.run("merge-base", "--is-ancestor", maybe_ancestor, head, check=False)
        return result.returncode == 0

    # --- writing -------------------------------------------------------------

    def fetch(self, remote: str = "origin") -> None:
        self.run("fetch", "--quiet", remote, timeout=NETWORK_TIMEOUT)

    def unshallow(self, remote: str = "origin") -> None:
        """Gives a `--depth 1` install enough history to diff and to log.

        Falls back to a bounded deepen: on a big repository over a slow link,
        some history beats failing the whole update over a changelog.
        """
        try:
            self.run("fetch", "--unshallow", "--quiet", remote, timeout=NETWORK_TIMEOUT)
        except GitError as e:
            logger.warning(f"Could not unshallow, deepening instead: {e}")
            self.run("fetch", "--depth=100", "--quiet", remote, timeout=NETWORK_TIMEOUT)

    def checkout_paths(self, paths: Sequence[str]) -> None:
        """Throws away local changes to these paths. Only ever called on a backup."""
        if paths:
            self.run("checkout", "HEAD", "--", *paths)

    def merge_ff_only(self, rev: str) -> None:
        self.run("merge", "--ff-only", rev)

    def merge_file(self, ours: Path, base: Path, theirs: Path) -> Optional[str]:
        """A three-way merge of one file. None when the two sides collide.

        `git merge-file` returns the number of conflict regions, so anything
        between 1 and 127 is a collision and 255 is git itself failing.
        """
        result = self.run(
            "merge-file", "-p", "--quiet",
            "-L", "your version", "-L", "the version you started from", "-L", "the new version",
            str(ours), str(base), str(theirs),
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
        if result.returncode >= 128 or result.returncode < 0:
            raise GitError("git merge-file failed", result.stderr)
        return None
