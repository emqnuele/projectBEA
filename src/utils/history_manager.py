import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.perf import perf_enabled
from src.utils.logger import get_logger

logger = get_logger("bea.utils.history")

# writes closer together than this share one trip to disk
DEBOUNCE_SECONDS = 1.0


class HistoryManager:
    def __init__(self, storage_dir: str = "data/conversations",
                 debounce_seconds: Optional[float] = None):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.current_session_file: Optional[Path] = None
        self.history: List[Dict[str, Any]] = []
        # set by `create_session`, which every entry point calls before use
        self.session_id: str = ""
        self.title = ""
        if debounce_seconds is None:
            # the switch: off means every message hits the disk, as before
            debounce_seconds = DEBOUNCE_SECONDS if perf_enabled() else 0.0
        self.debounce_seconds = max(0.0, float(debounce_seconds))
        self._lock = threading.Lock()
        self._dirty = False
        self._last_write = float('-inf')
        self._timer: Optional[threading.Timer] = None

    def create_session(self):
        """Starts a new conversation session."""
        with self._lock:
            # the old file first: switching sessions must not drop its last second
            self._cancel_locked()
            if self._dirty:
                self._write_now_locked()
            self._fresh_session_locked()

            # reset memory
            self.history = []
            self.title = ""

            # a new file must exist right away: readers poll for it
            self._write_now_locked()

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Lists all available sessions sorted by date (newest first)."""
        sessions = []
        for file_path in self.storage_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # create a summary
                first_msg = ""
                if data.get("messages"):
                    # find first user message for title
                    for msg in data["messages"]:
                        if msg["role"] == "user":
                            first_msg = msg["content"]
                            break

                sessions.append({
                    "id": data.get("session_id", file_path.stem),
                    "timestamp": data.get("start_time", ""),
                    "title": data.get("title", ""),
                    "preview": first_msg[:50] + "..." if first_msg else "New Conversation",
                    "message_count": len(data.get("messages", []))
                })
            except Exception as e:
                logger.error(f"Error reading session file {file_path}: {e}")

        # sort by timestamp descending
        sessions.sort(key=lambda x: x["timestamp"], reverse=True)
        return sessions

    def load_session(self, session_id: str) -> bool:
        """Loads a specific session by ID. Returns True if successful."""
        filename = f"{session_id}.json"
        file_path = self.storage_dir / filename

        if not file_path.exists():
            return False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            with self._lock:
                # same reason as create_session: the switch must not eat the tail
                self._cancel_locked()
                if self._dirty:
                    self._write_now_locked()
                self.session_id = data.get("session_id", session_id)
                self.history = data.get("messages", [])
                self.title = data.get("title", "")
                self.current_session_file = file_path
                self._dirty = False
            return True
        except Exception as e:
            logger.error(f"Error loading session {session_id}: {e}")
            return False

    def set_session_title(self, session_id: str, title: str) -> bool:
        """Writes a title into a session file (used by the dreamer to name chats)."""
        file_path = self.storage_dir / f"{session_id}.json"
        if not file_path.exists():
            return False
        try:
            with self._lock:
                if session_id == self.session_id:
                    # the in-memory copy is newer than the file when debounced
                    self.title = title
                    self._write_now_locked()
                    return True
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data["title"] = title
            _atomic_write(file_path, data)
            return True
        except Exception as e:
            logger.error(f"Error setting title for {session_id}: {e}")
            return False

    def add_message(self, role: str, content: str, mood: Optional[str] = None, **kwargs):
        """
        Adds a message to the history and saves it.
        role: 'user' or 'assistant' (or 'system' if needed)
        content: The text content
        mood: Optional mood for assistant messages
        kwargs: Extra metadata fields to store (e.g. thought, confidence)
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        if mood:
            message["mood"] = mood

        # merge extra metadata
        if kwargs:
            message.update(kwargs)

        with self._lock:
            if not self.current_session_file:
                self._fresh_session_locked()
            self.history.append(message)
            self._store_locked()

    def get_recent_history(self, limit: int = 20) -> List[Dict[str, str]]:
        """
        Returns the last `limit` messages in a format suitable for LLMs.
        """
        with self._lock:
            return list(self.history[-limit:])

    def flush(self) -> None:
        """Writes whatever is pending. Called on shutdown and session switches."""
        with self._lock:
            self._cancel_locked()
            if self._dirty:
                self._write_now_locked()

    def _store_locked(self) -> None:
        # isolated messages stay as fresh as before; bursts share one write
        if (self.debounce_seconds <= 0
                or time.monotonic() - self._last_write >= self.debounce_seconds):
            self._write_now_locked()
            return
        self._dirty = True
        if self._timer is None:
            self._timer = threading.Timer(self.debounce_seconds, self._on_timer)
            self._timer.daemon = True
            self._timer.start()

    def _on_timer(self) -> None:
        with self._lock:
            self._timer = None
            if self._dirty:
                self._write_now_locked()

    def _cancel_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _fresh_session_locked(self) -> None:
        # two sessions born in the same second must not share a file
        timestamp = int(time.time())
        candidate = f"session_{timestamp}"
        suffix = 2
        while (self.storage_dir / f"{candidate}.json").exists():
            candidate = f"session_{timestamp}-{suffix}"
            suffix += 1
        self.session_id = candidate
        self.current_session_file = self.storage_dir / f"{candidate}.json"

    def _snapshot_locked(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "start_time": self.history[0]["timestamp"] if self.history else datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "title": self.title,
            "messages": list(self.history),
        }

    def _write_now_locked(self) -> None:
        if not self.current_session_file:
            self._fresh_session_locked()
        assert self.current_session_file is not None
        try:
            _atomic_write(self.current_session_file, self._snapshot_locked())
        except Exception as e:
            logger.error(f"Error saving conversation history: {e}")
        else:
            self._dirty = False
            self._last_write = time.monotonic()

    def delete_session(self, session_id: str) -> bool:
        """Removes a session file. The active session is never deletable."""
        if session_id == self.session_id:
            return False
        file_path = self.storage_dir / f"{session_id}.json"
        if not file_path.exists():
            return False
        try:
            file_path.unlink()
            return True
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            return False


def _atomic_write(path: Path, data: Dict[str, Any]) -> None:
    # a crash mid-write must leave the previous file, never half of the new one
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
