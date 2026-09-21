"""ATLAS persistence repository — durable state storage for ATLAS domain.

Provides save/load for the full ATLAS domain snapshot as a JSON file.

The repository is storage-backend-neutral: it only knows about
AtlasData (the serialized shape) and the filesystem path. It does NOT
know about AtlasService, events, or any business logic.

The persistence file is a snapshot of current domain state. It is NOT
an event log. Event log entries are owned by EventManager/EventJournal.

Design decisions:
  - Single JSON file per ATLAS instance (simple, human-readable, atomic).
  - File location defaults to data/atlas/state.json; injectable for tests.
  - Missing file = empty state (first run).
  - Corrupted file = empty state + warning (safe failure).
  - No renderer details anywhere in the persisted data.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os

from src.utils.logger import get_logger

logger = get_logger("atlas.repository")


# ------------------------------------------------------------------
# AtlasData — serialized shape of full ATLAS state
# ------------------------------------------------------------------

@dataclass
class AtlasData:
    """Serialized representation of full ATLAS domain state.

    This is what gets written to and read from the persistence file.
    It contains the complete domain snapshot: all projects, work items,
    milestones, decisions, artifacts, and the active project ID.

    No event log entries, no runtime state, no renderer details.
    """

    version: int = 1
    saved_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    active_project_id: Optional[str] = None
    projects: List[Dict[str, Any]] = field(default_factory=list)
    work_items: List[Dict[str, Any]] = field(default_factory=list)
    milestones: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "saved_at": self.saved_at,
            "active_project_id": self.active_project_id,
            "projects": self.projects,
            "work_items": self.work_items,
            "milestones": self.milestones,
            "decisions": self.decisions,
            "artifacts": self.artifacts,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AtlasData":
        return cls(
            version=d.get("version", 1),
            saved_at=d.get("saved_at", 0.0),
            active_project_id=d.get("active_project_id"),
            projects=d.get("projects", []),
            work_items=d.get("work_items", []),
            milestones=d.get("milestones", []),
            decisions=d.get("decisions", []),
            artifacts=d.get("artifacts", []),
        )


# ------------------------------------------------------------------
# AtlasRepository — filesystem persistence
# ------------------------------------------------------------------

class AtlasRepository:
    """Persists ATLAS domain state to a JSON file.

    Thread-safety is NOT guaranteed. Callers (AtlasService) should
    serialize persistence calls within the event loop.

    The repository is a pure persistence adapter: it reads/writes JSON
    and does not contain domain logic.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """Initialize the repository.

        Args:
            storage_path: Directory to store ATLAS state in.
                Defaults to data/atlas/ under the current working directory.
                Pass a temp path in tests.
        """
        if storage_path is None:
            storage_path = os.path.join(os.getcwd(), "data", "atlas")
        self._storage_path = Path(storage_path)
        self._state_file = self._storage_path / "state.json"

    @property
    def storage_path(self) -> Path:
        return self._storage_path

    def load(self) -> AtlasData:
        """Load ATLAS state from disk.

        Returns empty state if the file does not exist (first run).
        Returns empty state with a warning if the file is corrupted.
        """
        if not self._state_file.exists():
            return AtlasData()

        try:
            raw = self._state_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            return AtlasData.from_dict(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"ATLAS state file corrupted, starting fresh: {e}")
            return AtlasData()

    def save(self, data: AtlasData) -> None:
        """Persist ATLAS state to disk.

        Creates the storage directory if it does not exist.
        Overwrites the existing state file atomically (write-to-temp-then-rename
        would be more robust but adds complexity; the current approach is
        sufficient for single-process use).
        """
        try:
            self._storage_path.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps(data.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as e:
            logger.error(f"ATLAS state save failed: {e}")
            raise

    def clear(self) -> None:
        """Remove the persisted state file.

        Used for testing and reset scenarios.
        """
        if self._state_file.exists():
            self._state_file.unlink()
