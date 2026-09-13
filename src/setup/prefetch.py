"""Pulling the weights down while someone is still watching.

Two models arrive from Hugging Face on a fresh install: whisper, the first time
she hears anything, and the embedder, the first time she remembers anything.
Both are lazy on purpose — startup should not wait for a download — but on a
fresh clone that means her first sentence, or her first memory, silently taking
a minute. Doing it here costs the same minute in the one place where it looks
like progress rather than a hang.

Nothing here is required. Every failure is a warning: the engine fetches what
is missing on first use exactly as it did before.
"""

import os
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from src.core.memory.embedder import DEFAULT_CACHE_DIR, FastEmbedEmbedder, resolve_model
from src.modules.STT.faster_whisper_stt import normalize_model

# only ever used to size a progress bar, so being a little off is harmless
WHISPER_MB = {
    "tiny": 75,
    "base": 145,
    "small": 480,
    "large-v3-turbo": 1600,
}

EMBEDDER_FALLBACK_MB = 220


def directory_bytes(path: str) -> int:
    """Everything under `path`, part-written files included.

    huggingface_hub writes into `.cache/huggingface` inside the same folder
    while it works, so this grows smoothly and lands on the real size.
    """
    root = Path(path)
    if not root.is_dir():
        return 0
    return sum(file.stat().st_size for file in root.rglob("*") if file.is_file())


def run(work: Callable[[], Any], root: str,
        on_progress: Optional[Callable[[int], None]] = None,
        tick: float = 0.3) -> Optional[Exception]:
    """Runs a download, reporting how much of `root` exists as it goes.

    Returns the error it failed on, or None. The work happens on a thread only
    so that the bytes on disk can be watched while it does.
    """
    os.makedirs(root, exist_ok=True)
    failure: list[Exception] = []

    def attempt() -> None:
        try:
            work()
        except Exception as error:
            failure.append(error)

    worker = threading.Thread(target=attempt, daemon=True)
    worker.start()
    while worker.is_alive():
        worker.join(tick)
        if on_progress:
            on_progress(directory_bytes(root))
    if on_progress:
        on_progress(directory_bytes(root))

    return failure[0] if failure else None


# --- whisper ----------------------------------------------------------------


def _download_whisper(model: str, root: str, local_files_only: bool = False) -> str:
    from faster_whisper.utils import download_model

    return download_model(model, output_dir=root, local_files_only=local_files_only)


def whisper_here(model: str, root: str, downloader: Optional[Callable[..., Any]] = None) -> bool:
    """Whether the weights are already on disk, asked of the library itself."""
    downloader = downloader or _download_whisper
    try:
        downloader(normalize_model(model), root, local_files_only=True)
        return True
    except Exception:
        return False


def fetch_whisper(model: str, root: str, downloader: Optional[Callable[..., Any]] = None,
                  on_progress: Optional[Callable[[int], None]] = None,
                  tick: float = 0.3) -> Optional[Exception]:
    downloader = downloader or _download_whisper
    return run(lambda: downloader(normalize_model(model), root), root, on_progress, tick)


# --- the embedder -----------------------------------------------------------


def embedder_mb(model: Optional[str] = None) -> int:
    """What the embedding model weighs, asked of fastembed's own catalogue."""
    wanted = resolve_model(model)
    try:
        from fastembed import TextEmbedding

        for known in TextEmbedding.list_supported_models():
            if known["model"] == wanted:
                return round(float(known["size_in_GB"]) * 1000)
    except Exception:
        pass
    return EMBEDDER_FALLBACK_MB


def embedder_here(cache_dir: str = DEFAULT_CACHE_DIR) -> bool:
    """Whether an ONNX model is already cached.

    fastembed has no offline probe and the layout of its cache is its own
    business — but nothing else puts an .onnx file in there.
    """
    return any(Path(cache_dir).rglob("*.onnx")) if Path(cache_dir).is_dir() else False


def fetch_embedder(model: Optional[str] = None, cache_dir: str = DEFAULT_CACHE_DIR,
                   loader: Optional[Callable[[], Any]] = None,
                   on_progress: Optional[Callable[[int], None]] = None,
                   tick: float = 0.3) -> Optional[Exception]:
    """Embeds one throwaway sentence, which is what downloads the model.

    Going through `embed` rather than the loader alone means a model that
    arrived but cannot run is found here, not at her first memory.
    """
    load = loader or (lambda: FastEmbedEmbedder(model, cache_dir).embed(["warm-up"]))
    return run(load, cache_dir, on_progress, tick)
