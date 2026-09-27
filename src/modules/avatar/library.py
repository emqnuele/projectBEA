"""The models and clips on this machine, and the free ones that can be fetched.

What the dashboard's library shows and does, without FastAPI in it: listing
the `.vrm` files with what each one says about itself, fetching a catalog
entry on a thread, taking an upload, deleting a model. Everything that reads
a 20 MB file runs off the event loop — the router calls these from the
threadpool or from a thread of their own.

A model is addressed by its file name inside the models folder, never by a
path from the page: the page can only name what this module listed.
"""

import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from src.core.stage import base_clips, clip_files, clips_dir
from src.modules.avatar import catalog
from src.modules.avatar.vrm_file import describe, gltf_json, is_clip, is_vrm, thumbnail

# the id of the configured model when it lives outside the models folder
EXTERNAL = "external"

# a vroid model is 10-60 MB; this leaves room for a heavy one and none for a mistake
UPLOAD_LIMIT = 200 * 1024 * 1024

_SAFE = re.compile(r"[^A-Za-z0-9._ -]+")

# the first bytes of every binary fbx; the ascii flavour is not one mixamo sends
FBX_MAGIC = b"Kaydara FBX Binary  \x00"


def models_dir(config) -> Path:
    stage = getattr(config, "stage", None) or {}
    return Path(stage.get("models_dir") or "data/models")


def _configured(config) -> Optional[Path]:
    raw = ((getattr(config, "stage", None) or {}).get("model_path") or "").strip()
    return Path(raw).resolve() if raw else None


# --- reading files, once per version of them -------------------------------

_described: Dict[Path, Tuple[Tuple[float, int], Dict[str, Any]]] = {}
_described_lock = threading.Lock()


def described(path: Path) -> Dict[str, Any]:
    """`describe(path)`, remembered until the file changes."""
    stat = path.stat()
    key = (stat.st_mtime, stat.st_size)
    with _described_lock:
        hit = _described.get(path)
        if hit and hit[0] == key:
            return hit[1]
    try:
        info = describe(path)
    except (OSError, ValueError) as e:
        info = {"size": stat.st_size, "vrm": None, "error": str(e)}
    with _described_lock:
        _described[path] = (key, info)
    return info


def _entry(model_id: str, path: Path, active: Optional[Path], external: bool) -> Dict[str, Any]:
    info = described(path)
    stat = path.stat()
    known = next((a for a in catalog.CATALOG if a.kind == "model" and a.filename == path.name), None)
    return {
        "id": model_id,
        "file": path.name,
        "path": str(path),
        "name": info.get("title") or path.stem,
        "size": info.get("size", stat.st_size),
        "vrm": info.get("vrm"),
        "authors": info.get("authors", []),
        "licence": info.get("licence"),
        "credit": known.credit if known else "",
        "emotions": info.get("emotions", []),
        "warnings": info.get("warnings", []) if info.get("vrm") else [info.get("error") or "Not a VRM file."],
        "has_thumbnail": bool(info.get("has_thumbnail")),
        "version": int(stat.st_mtime),
        "active": active is not None and path.resolve() == active,
        "external": external,
    }


def list_models(config) -> List[Dict[str, Any]]:
    """Every .vrm in the models folder, and the configured one if it lives elsewhere."""
    folder = models_dir(config)
    active = _configured(config)
    out = []
    if folder.is_dir():
        for path in sorted(folder.glob("*.vrm")):
            if path.is_file():
                out.append(_entry(path.name, path, active, external=False))
    if active is not None and active.is_file() and not any(m["active"] for m in out):
        out.append(_entry(EXTERNAL, active, active, external=True))
    return out


def resolve_model(config, model_id: str) -> Optional[Path]:
    """The file a listed id names, or None. Never a path the page made up."""
    if model_id == EXTERNAL:
        active = _configured(config)
        return active if active is not None and active.is_file() else None
    folder = models_dir(config).resolve()
    if not model_id or model_id != Path(model_id).name or not model_id.endswith(".vrm"):
        return None
    path = (folder / model_id).resolve()
    return path if path.is_relative_to(folder) and path.is_file() else None


def model_thumbnail(config, model_id: str) -> Optional[Tuple[str, bytes]]:
    path = resolve_model(config, model_id)
    if path is None:
        return None
    try:
        return thumbnail(path)
    except (OSError, ValueError):
        return None


def delete_model(config, model_id: str) -> Path:
    """Removes a model from the models folder. Never the one on stage, never anything outside it."""
    if model_id == EXTERNAL:
        raise PermissionError("That model is not in the models folder; delete it yourself.")
    path = resolve_model(config, model_id)
    if path is None:
        raise FileNotFoundError(model_id)
    if path == _configured(config):
        raise PermissionError("That model is on stage. Pick another one first.")
    path.unlink()
    with _described_lock:
        _described.pop(path, None)
    return path


# --- clips -------------------------------------------------------------------


def clip_duration(doc: Dict[str, Any]) -> float:
    """The longest sampler input of every animation, in seconds."""
    accessors = doc.get("accessors", [])
    longest = 0.0
    for animation in doc.get("animations", []):
        for sampler in animation.get("samplers", []):
            index = sampler.get("input")
            if isinstance(index, int) and 0 <= index < len(accessors):
                top = accessors[index].get("max") or [0]
                longest = max(longest, float(top[0]))
    return longest


def list_clips(config) -> List[Dict[str, Any]]:
    bases = base_clips(config)
    out = []
    for path in clip_files(config):
        entry: Dict[str, Any] = {"name": path.stem, "file": path.name, "size": path.stat().st_size,
                                 "role": "base" if path.stem in bases else "gesture",
                                 "format": "mixamo" if path.suffix == ".fbx" else "vrma"}
        if path.suffix == ".fbx":
            # retargeted in the page; reading an fbx here would buy only a length
            out.append(entry)
            continue
        try:
            doc = gltf_json(path)
            animation = doc.get("extensions", {}).get("VRMC_vrm_animation", {})
            entry["duration"] = round(clip_duration(doc), 3)
            entry["bones"] = len(animation.get("humanoid", {}).get("humanBones", {}))
            entry["drives_gaze"] = "lookAt" in animation
        except (OSError, ValueError) as e:
            entry["error"] = str(e)
        out.append(entry)
    return out


# --- the catalog -------------------------------------------------------------


def list_catalog(config, downloads: "Downloads") -> List[Dict[str, Any]]:
    running = downloads.snapshot()
    out = []
    for asset in catalog.CATALOG:
        folder = models_dir(config) if asset.kind == "model" else clips_dir(config)
        target = folder / asset.filename
        out.append({
            "id": asset.id, "kind": asset.kind, "name": asset.name, "file": asset.filename,
            "size": asset.size, "licence": asset.licence, "credit": asset.credit, "default": asset.default,
            # size first: hashing 20 MB to draw a card is wasted when the size already disagrees
            "installed": target.is_file() and target.stat().st_size == asset.size,
            "download": running.get(asset.id),
        })
    return out


class Downloads:
    """Catalog fetches, one thread each, readable from any thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Dict[str, Any]] = {}

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._state.items()}

    def start(self, asset: catalog.Asset, into: Path,
              fetch: Callable[..., Path] = catalog.fetch) -> bool:
        """False when that asset is already on its way."""
        with self._lock:
            current = self._state.get(asset.id)
            if current and current["state"] == "running":
                return False
            self._state[asset.id] = {"state": "running", "written": 0, "total": asset.size, "error": ""}

        def progress(written: int, total: int) -> None:
            with self._lock:
                self._state[asset.id].update(written=written, total=total or asset.size)

        def run() -> None:
            try:
                fetch(asset, into, progress=progress)
                outcome = {"state": "done", "error": ""}
            except catalog.FetchError as e:
                outcome = {"state": "failed", "error": str(e)}
            except Exception as e:  # noqa: BLE001 - a thread that dies silently leaves the card spinning forever
                outcome = {"state": "failed", "error": f"{type(e).__name__}: {e}"}
            with self._lock:
                self._state[asset.id].update(outcome)

        threading.Thread(target=run, daemon=True, name=f"fetch-{asset.id}").start()
        return True


# --- uploads -----------------------------------------------------------------


def safe_name(raw: str, suffix: str) -> str:
    """A file name the page cannot use to leave the folder, or ''."""
    name = _SAFE.sub("", Path(raw or "").name).strip(" .")
    if not name.lower().endswith(suffix):
        return ""
    stem = name[: -len(suffix)].strip(" .")
    return f"{stem}{suffix}" if stem else ""


def save_upload(chunks: Iterable[bytes], name: str, folder: Path, kind: str,
                limit: int = UPLOAD_LIMIT) -> Path:
    """Writes an upload beside its target, checks what it is, then renames it into place.

    `kind` is "model" or "clip". Raises ValueError for anything that is not
    what it claims to be, and FileExistsError rather than replace a file.
    """
    suffixes = (".vrm",) if kind == "model" else (".vrma", ".fbx")
    clean = next((c for c in (safe_name(name, s) for s in suffixes) if c), "")
    if not clean:
        raise ValueError(f"The file name has to end in {' or '.join(suffixes)}.")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / clean
    if target.exists():
        raise FileExistsError(clean)
    # one partial file per upload: two of the same name at once must not write into each other
    partial = folder / f".{clean}.{uuid.uuid4().hex}.part"
    written = 0
    try:
        with open(partial, "wb") as out:
            for chunk in chunks:
                written += len(chunk)
                if written > limit:
                    raise ValueError(f"That file is over {limit // (1024 * 1024)} MB.")
                out.write(chunk)
        if clean.endswith(".fbx"):
            with open(partial, "rb") as f:
                if not f.read(len(FBX_MAGIC)) == FBX_MAGIC:
                    raise ValueError("That is not a binary FBX. From Mixamo, download FBX Binary, Without Skin.")
        else:
            doc = gltf_json(partial)
            if kind == "model" and not is_vrm(doc):
                raise ValueError("That is a glTF file, not a VRM: it has no humanoid bones to drive.")
            if kind == "clip" and not is_clip(doc):
                raise ValueError("That is not a VRM animation (.vrma).")
        try:
            # a link fails if the name was taken meanwhile; a rename would replace it on posix
            os.link(partial, target)
        except FileExistsError:
            raise FileExistsError(clean) from None
        except OSError:
            if target.exists():
                raise FileExistsError(clean) from None
            partial.rename(target)
        return target
    finally:
        partial.unlink(missing_ok=True)
