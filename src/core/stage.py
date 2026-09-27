"""What the browser source is told, and the last thing it was told.

Deliberately not `EventManager`. That one replays a backlog to every new
subscriber, which is right for a dashboard reading a log and wrong for a stage:
OBS reloads a browser source whenever you toggle it, and replaying fifty events
would make her act out the last minute of the stream again. Here a fresh
connection gets one snapshot of how she looks *now*, and patches after that.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.core.fanout import Fanout, offer
from src.core.mind.moods import DEFAULT_MOOD

# how many patches a stalled page may buffer before it is dropped
QUEUE_LIMIT = 200

# things that describe a moment rather than a state. Storing the envelope would
# make a page that reconnects mouth a sentence nobody is saying any more.
TRANSIENT = frozenset({"envelope", "perform", "mouth_segment", "mouth_sync"})


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


def base_clips(config) -> Set[str]:
    """The clips that carry her body underneath everything else.

    Played in a loop by the page, never as a one-shot: `<do:relax>` landing on
    the idle clip would start it a second time on top of itself.
    """
    stage = getattr(config, "stage", None) or {}
    names = {str(stage.get("idle_clip") or "").strip()}
    for name in (stage.get("state_clips") or {}).values():
        names.add(str(name or "").strip())
    names.discard("")
    return names


# a clip's formats, in the order a name is looked up when both exist
CLIP_SUFFIXES = (".vrma", ".fbx")


def clip_files(config) -> List[Path]:
    """Every clip in the folder, bases and gestures alike, one file per name."""
    folder = clips_dir(config)
    if not folder.is_dir():
        return []
    chosen: Dict[str, Path] = {}
    for suffix in reversed(CLIP_SUFFIXES):
        for path in folder.glob(f"*{suffix}"):
            chosen[path.stem] = path
    return sorted(chosen.values(), key=lambda p: p.stem)


def clip_path(config, name: str) -> Optional[Path]:
    """The file a clip name refers to, never outside the clips folder."""
    folder = clips_dir(config).resolve()
    for suffix in CLIP_SUFFIXES:
        path = (folder / f"{name}{suffix}").resolve()
        if path.is_relative_to(folder) and path.is_file():
            return path
    return None


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
    bases = base_clips(config)
    return sorted(path.stem for path in clip_files(config) if path.stem not in bases)


def public_config(config) -> Dict[str, Any]:
    """What the browser source needs to draw her, and nothing else.

    Read by a page running inside OBS, so it carries no key, token or password.
    """
    stage = dict(getattr(config, "stage", None) or {})
    return {
        "avatar_backend": stage.get("avatar_backend", "png"),
        "png_render": stage.get("png_render", "obs"),
        "caption_backend": stage.get("caption_backend", "obs"),
        "shot": stage.get("shot", "bust"),
        "background": stage.get("background", ""),
        "light_preset": stage.get("light_preset", "flat"),
        "lipsync_fps": stage.get("lipsync_fps", 30),
        "max_fps": stage.get("max_fps", 0),
        "idle_clip": stage.get("idle_clip", ""),
        "state_clips": dict(stage.get("state_clips") or {}),
        "expression_intensity": stage.get("expression_intensity", 1.0),
        "face_blend_blink": stage.get("face_blend_blink", True),
        "mouth_under_emotion": stage.get("mouth_under_emotion", 1.0),
        "has_model": bool(stage.get("model_path")),
        "model_id": _model_id(stage.get("model_path") or ""),
        "typing_delay": config.typing_delay,
        "text_line_width": config.text_line_width,
        "text_lines": config.text_lines,
        "text_font_size": config.text_font_size,
    }


def publish_segment(channel: "StageChannel", envelope, fps: int, utterance_id: str, offset_ms: int) -> None:
    if not len(envelope):
        return
    channel.publish({"mouth_segment": {"id": utterance_id, "frames": list(envelope),
                                       "fps": int(fps), "offset_ms": int(offset_ms)}})


def publish_sync(channel: "StageChannel", utterance_id: str, played_ms: int) -> None:
    channel.publish({"mouth_sync": {"id": utterance_id, "played_ms": int(played_ms)}})


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
            offer(queue, {"closed": True})
            self.unsubscribe(queue)
