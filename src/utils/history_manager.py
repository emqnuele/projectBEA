import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger("bea.utils.history")

class HistoryManager:
    def __init__(self, storage_dir: str = "data/conversations"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.current_session_file = None
        self.history: List[Dict[str, Any]] = []
        self.session_id = None
        self.title = ""

    def create_session(self):
        """Starts a new conversation session."""
        timestamp = int(time.time())
        self.session_id = f"session_{timestamp}"
        filename = f"{self.session_id}.json"
        self.current_session_file = self.storage_dir / filename

        # reset memory
        self.history = []
        self.title = ""

        # initialize empty session file
        self._save_to_disk()

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

            self.session_id = data.get("session_id", session_id)
            self.history = data.get("messages", [])
            self.title = data.get("title", "")
            self.current_session_file = file_path
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
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data["title"] = title
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            if session_id == self.session_id:
                self.title = title
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

        self.history.append(message)
        self._save_to_disk()

    def get_recent_history(self, limit: int = 20) -> List[Dict[str, str]]:
        """
        Returns the last `limit` messages in a format suitable for LLMs.
        """
        return self.history[-limit:]

    def _save_to_disk(self):
        """Saves current history to JSON file."""
        if not self.current_session_file:
            self.create_session()

        assert self.current_session_file is not None
        data = {
            "session_id": self.session_id,
            "start_time": self.history[0]["timestamp"] if self.history else datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "title": self.title,
            "messages": self.history
        }

        try:
            with open(self.current_session_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving conversation history: {e}")

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
