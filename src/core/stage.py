"""What the browser source is told, and the last thing it was told.

Deliberately not `EventManager`. That one replays a backlog to every new
subscriber, which is right for a dashboard reading a log and wrong for a stage:
OBS reloads a browser source whenever you toggle it, and replaying fifty events
would make her act out the last minute of the stream again. Here a fresh
connection gets one snapshot of how she looks *now*, and patches after that.
"""

import asyncio
import contextlib
from pathlib import Path
from typing import Any, Dict, List

from src.core.fanout import Fanout
from src.core.mind.moods import DEFAULT_MOOD

# how many patches a stalled page may buffer before it is dropped
QUEUE_LIMIT = 200

# things that describe a moment rather than a state. Storing the envelope would
# make a page that reconnects mouth a sentence nobody is saying any more.
TRANSIENT = frozenset({"envelope", "perform"})


def _model_id(raw: str) -> str:
    """Changes whenever the model does, without telling the page a path."""
    if not raw:
        return ""
    path = Path(raw)
    try:
        return f"{path.name}:{int(path.stat().st_mtime)}"
    except OSError:
        return path.name


def clips_dir(config) -> Path:
    """Where the .vrma behaviours live."""
    stage = getattr(config, "stage", None) or {}
    return Path(stage.get("clips_dir") or "data/clips")


def installed_clips(config) -> List[str]:
    """Every behaviour she can actually play, by name.

    Which is a different question per backend, and asking it in one place is
    what stops the dashboard from offering a behaviour she does not have and
    the mind from writing `<do:…>` for one that was never installed. A still
    image has no behaviours at all; adding one to the folder is enough for the
    `model` backend, which is the point of a folder.
    """
    stage = getattr(config, "stage", None) or {}
    backend = stage.get("avatar_backend", "png")
    if backend == "vtube_studio":
        return sorted(name for name in (stage.get("vts_clips") or {}) if name)
    if backend != "model":
        return []
    folder = clips_dir(config)
    if not folder.is_dir():
        return []
    return sorted(path.stem for path in folder.glob("*.vrma"))


def public_config(config) -> Dict[str, Any]:
    """What the browser source needs to draw her, and nothing else.

    Read by a page running inside OBS, so it carries no key, token or password.
    """
    stage = dict(getattr(config, "stage", None) or {})
    return {
        "avatar_backend": stage.get("avatar_backend", "png"),
        "caption_backend": stage.get("caption_backend", "obs"),
        "shot": stage.get("shot", "bust"),
        "background": stage.get("background", ""),
        "lipsync_fps": stage.get("lipsync_fps", 30),
        "max_fps": stage.get("max_fps", 0),
        "has_model": bool(stage.get("model_path")),
        "model_id": _model_id(stage.get("model_path") or ""),
        "typing_delay": config.typing_delay,
        "text_line_width": config.text_line_width,
        "text_lines": config.text_lines,
        "text_font_size": config.text_font_size,
    }


class StageChannel:
    """One-way fan-out from the engine to however many browser sources exist."""

    def __init__(self) -> None:
        # a page that stopped reading must not slow down the engine
        self._fanout = Fanout(QUEUE_LIMIT, "stage")
        self._state: Dict[str, Any] = {"mood": DEFAULT_MOOD, "state": "idle", "caption": ""}

    # --- writing ------------------------------------------------------------

    def publish(self, patch: Dict[str, Any]) -> None:
        """Merges the durable keys into the state and fans the patch out."""
        for key, value in patch.items():
            if key not in TRANSIENT:
                self._state[key] = value
        self._fanout.publish(patch)

    def snapshot(self) -> Dict[str, Any]:
        """Everything a page needs to draw her correctly the instant it loads."""
        return dict(self._state)

    # --- reading ------------------------------------------------------------

    def subscribe(self) -> "asyncio.Queue[Dict[str, Any]]":
        return self._fanout.subscribe()

    def unsubscribe(self, queue) -> None:
        self._fanout.unsubscribe(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._fanout)

    def close(self) -> None:
        for queue in self._fanout.queues():
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait({"closed": True})
            self.unsubscribe(queue)
