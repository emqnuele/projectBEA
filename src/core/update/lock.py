"""One update at a time, across processes.

Two updates running together would interleave a `git checkout` of the prompts
with another run's snapshot, and the second one would back up files the first
had already reset. So: an exclusive file, created with O_EXCL, which is atomic
on every filesystem we care about.

A lock nobody released — the machine lost power mid-update — has to expire, or
the feature is broken until someone finds the file. Expiry is by age alone:
asking whether the recorded pid is still alive is the obvious refinement, and
on Windows `os.kill(pid, 0)` does not ask, it terminates. So the lock records
who holds it for the error message, and time decides when it is stale.
"""

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from src.utils.logger import get_logger

logger = get_logger("bea.update.lock")

LOCK_FILE = Path("data/.update.lock")

# comfortably longer than the slowest plausible run — a cold `uv sync` plus an
# `npm install` on a laptop — and short enough that a dead lock clears itself
# within one coffee break
STALE_AFTER = 45 * 60


class UpdateBusy(Exception):
    """Someone else is already updating."""


def holder(root: Path) -> Optional[dict]:
    """Who holds the lock right now, or None when it is free or stale."""
    path = Path(root) / LOCK_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    started = payload.get("started_at", 0)
    if not isinstance(started, (int, float)) or time.time() - started > STALE_AFTER:
        return None
    return payload


@contextmanager
def held(root: Path, source: str) -> Iterator[None]:
    """Holds the update lock for the duration of the block."""
    path = Path(root) / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        handle = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        current = holder(root)
        if current is not None:
            age = int(time.time() - current.get("started_at", time.time()))
            raise UpdateBusy(
                f"An update started {age}s ago from {current.get('source', 'somewhere')} "
                f"(pid {current.get('pid', '?')}) is still running."
            ) from None
        # stale: whoever wrote it is long gone
        logger.warning("Clearing a stale update lock")
        path.unlink(missing_ok=True)
        try:
            handle = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise UpdateBusy("Another update took the lock first.") from None

    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "source": source, "started_at": time.time()}, f)
        yield
    finally:
        path.unlink(missing_ok=True)
