"""What is put aside before anything is touched, and the note that says so.

Two separate jobs live here because they answer two different fears.

The **snapshot** is for the user: their prompts, their config, their memory,
copied whole before the first write. Nothing in the update is supposed to need
it — the reconciliation is careful — but "supposed to" is not an argument you
can make to someone who lost the character they spent a week writing.

The **journal** is for the machine: a note recording which phase the update had
reached, written before the phase starts and deleted when the run succeeds.
Finding one on startup means a previous update died between resetting the
prompts and putting them back, which is the one window where the working copy
is worse than either end state. The next run reads it and restores.
"""

import json
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from src.utils.files import atomic_write_text
from src.utils.logger import get_logger

logger = get_logger("bea.update.backup")

BACKUP_ROOT = Path("data/.backups")
JOURNAL_FILE = Path("data/.update.journal.json")

# enough to go back through a bad week, few enough to not quietly eat a disk
KEEP_BACKUPS = 8

# copied alongside the prompts even though git never touches them: an update is
# the moment people are most afraid, and the answer to "can I go back" should
# not have an asterisk
EXTRAS = ("config.json", ".env")

DATABASE = "data/bea.db"


@dataclass(frozen=True)
class Snapshot:
    directory: Path
    files: List[str]

    @property
    def name(self) -> str:
        return self.directory.name


def take(root: Path, files: Sequence[str], base_sha: str) -> Snapshot:
    """Copies `files` (repo-relative) plus config, env and the memory database."""
    root = Path(root)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    directory = root / BACKUP_ROOT / stamp
    directory.mkdir(parents=True, exist_ok=True)

    saved: List[str] = []
    for relative in list(files) + list(EXTRAS):
        source = root / relative
        if not source.is_file():
            continue
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source, target)
            saved.append(relative)
        except OSError as e:
            logger.warning(f"Could not back up {relative}: {e}")

    if _copy_database(root / DATABASE, directory / DATABASE):
        saved.append(DATABASE)

    manifest = {
        "created_at": time.time(),
        "base": base_sha,
        "files": saved,
    }
    atomic_write_text(directory / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    _prune(root)
    return Snapshot(directory=directory, files=saved)


def _copy_database(source: Path, target: Path) -> bool:
    """A live SQLite database in WAL mode cannot be copied with `cp` and trusted.

    The engine holds it open while this runs, so the file on disk is missing
    whatever is still in the write-ahead log. The backup API takes a consistent
    copy of a database someone else is using, which is exactly the case here.
    """
    if not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as live, sqlite3.connect(target) as copy:
            live.backup(copy)
        return True
    except sqlite3.Error as e:
        logger.warning(f"Could not back up the memory database: {e}")
        target.unlink(missing_ok=True)
        return False


def _prune(root: Path) -> None:
    directory = Path(root) / BACKUP_ROOT
    try:
        existing = sorted((d for d in directory.iterdir() if d.is_dir()), key=lambda d: d.name)
    except OSError:
        return
    for old in existing[:-KEEP_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)


def restore(root: Path, snapshot_dir: Path, files: Sequence[str]) -> List[str]:
    """Puts named files back from a snapshot. Returns what was actually restored."""
    root, snapshot_dir = Path(root), Path(snapshot_dir)
    restored = []
    for relative in files:
        source = snapshot_dir / relative
        if not source.is_file():
            continue
        try:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            restored.append(relative)
        except OSError as e:
            logger.error(f"Could not restore {relative}: {e}")
    return restored


# --- the journal -------------------------------------------------------------


def open_journal(root: Path, phase: str, snapshot: Snapshot, base_sha: str, files: Sequence[str]) -> None:
    atomic_write_text(
        Path(root) / JOURNAL_FILE,
        json.dumps({
            "phase": phase,
            "snapshot": snapshot.name,
            "base": base_sha,
            "files": list(files),
            "at": time.time(),
        }, indent=2) + "\n",
    )


def mark_phase(root: Path, phase: str) -> None:
    path = Path(root) / JOURNAL_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    payload["phase"] = phase
    try:
        atomic_write_text(path, json.dumps(payload, indent=2) + "\n")
    except OSError as e:
        logger.warning(f"Could not update the update journal: {e}")


def close_journal(root: Path) -> None:
    (Path(root) / JOURNAL_FILE).unlink(missing_ok=True)


def read_journal(root: Path) -> Optional[Dict]:
    try:
        payload = json.loads((Path(root) / JOURNAL_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def recover(root: Path) -> List[str]:
    """Undoes an update that died mid-flight, by putting the user's files back.

    Only the phases between the reset and the reconciliation leave the working
    copy holding something the user did not write; a crash anywhere else left
    their files alone and there is nothing to do but forget the journal.
    """
    journal = read_journal(root)
    if not journal:
        return []

    restored: List[str] = []
    if journal.get("phase") in ("reset", "merge", "reconcile"):
        snapshot_dir = Path(root) / BACKUP_ROOT / str(journal.get("snapshot", ""))
        files = [f for f in journal.get("files", []) if isinstance(f, str)]
        restored = restore(root, snapshot_dir, files)
        if restored:
            logger.warning(f"Recovered {len(restored)} file(s) from an interrupted update")

    close_journal(root)
    return restored
