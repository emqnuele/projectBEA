"""The parts of her that are javascript, and how to get them installed.

There are two, and for a long time only one of them was ever installed. The
dashboard is the obvious one — you notice a missing dashboard immediately. Her
discord voice is a node program too, and nothing said so: the installer built
the dashboard, the updater rebuilt the dashboard, and the discord toggle in the
UI turned on a bot whose packages had never been fetched. It went on looking
enabled and simply never came online.

Listed in one place so that anything which installs, updates or checks her
covers all of it — and so adding a third is one line rather than three.
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger("bea.setup.node")

# `npm install` on a slow link is measured in minutes
TIMEOUT = 900


@dataclass(frozen=True)
class NodeProject:
    """One npm project of hers: where it lives and what it needs."""

    name: str
    path: str
    builds: bool  # whether `npm run build` follows the install

    def directory(self, root: Optional[Path] = None) -> Path:
        return (root or Path.cwd()) / self.path

    def installed(self, root: Optional[Path] = None) -> bool:
        return (self.directory(root) / "node_modules").is_dir()


PROJECTS: Tuple[NodeProject, ...] = (
    NodeProject("dashboard", "src/web/frontend", builds=True),
    NodeProject("discord bot", "src/core/skills/voice/bot", builds=False),
)


def executable(name: str) -> Optional[str]:
    """The program to actually run, under the name this machine gave it.

    Windows ships npm as `npm.cmd`, and `CreateProcess` — which is what
    subprocess uses without a shell — only ever looks for an `.exe` under a bare
    name. It runs a `.cmd` quite happily once told the full name, which is what
    `which` returns. Without this every npm step failed on windows saying npm
    was not installed, on machines where it plainly was.
    """
    return shutil.which(name)


def run(project: NodeProject, args: List[str], root: Optional[Path] = None) -> Tuple[bool, str]:
    """One npm command. Returns (ok, what it said when it did not work)."""
    npm = executable("npm")
    if npm is None:
        return False, "npm is not installed"
    try:
        result = subprocess.run(
            [npm, *args], cwd=str(project.directory(root)), capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT,
        )
    except FileNotFoundError:
        return False, "npm is not installed"
    except subprocess.TimeoutExpired:
        return False, f"`npm {' '.join(args)}` did not finish within {TIMEOUT // 60} minutes"
    if result.returncode == 0:
        return True, ""
    last = (result.stderr or result.stdout or "").strip().splitlines()
    return False, last[-1] if last else f"npm exited with {result.returncode}"


def install_all(root: Optional[Path] = None) -> int:
    """Installs (and builds) every node project. Returns a process exit code.

    Written for the people who have no `make`: every target in the Makefile is
    a one-line command underneath, and this is the one that was not.
    """
    if shutil.which("npm") is None:
        logger.error("Node.js is not installed. Get Node 20 or newer from https://nodejs.org, "
                     "then run this again.")
        return 1

    failed = False
    for project in PROJECTS:
        logger.info(f"Installing the {project.name}…")
        ok, detail = run(project, ["install", "--no-audit", "--no-fund"], root)
        if ok and project.builds:
            logger.info(f"Building the {project.name}…")
            ok, detail = run(project, ["run", "build"], root)
        if ok:
            logger.info(f"The {project.name} is ready.")
        else:
            logger.error(f"The {project.name} could not be installed: {detail}")
            failed = True

    return 1 if failed else 0
