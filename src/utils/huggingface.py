"""Fetching weights from Hugging Face, and what to say when it did not happen.

Two of her parts come from there — whisper and the embedder — and both hand
back whatever huggingface_hub raised, which says `401` at a person who never
knew an account was involved.

The second half of the file is the download itself: one bar, watched from the
bytes on disk, with every other library's bar turned off for the duration. It
lives here rather than in the wizard because the engine fetches the same
weights, in the same place, when nobody ran the wizard at all.
"""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, List, Optional

TOKEN_HINT = (
    "Hugging Face refused the download. The weights are public, so this is "
    "almost always a shared or office IP being rate-limited: wait a few minutes, "
    "or put HF_TOKEN=<your token> in .env (https://huggingface.co/settings/tokens) "
    "and it will be used for the download."
)

OFFLINE_HINT = (
    "The weights could not be reached. Check the connection, then start her "
    "again — the download resumes where it stopped."
)


def download_hint(error: Exception) -> Optional[str]:
    """A line the person reading the log can act on, or None.

    Only the two cases with a real answer get a hint; everything else is left
    to speak for itself rather than be guessed at.
    """
    text = f"{type(error).__name__}: {error}".lower()

    if any(word in text for word in ("401", "403", "429", "gated", "rate limit",
                                     "too many requests", "unauthorized")):
        return TOKEN_HINT
    if any(word in text for word in ("connection", "timeout", "timed out",
                                     "network", "dns", "offline", "unreachable")):
        return OFFLINE_HINT
    return None


# --- downloading, with nobody else drawing on the terminal -------------------

# Every library that pulls weights draws its own progress bar, and two of them
# draw it with a bare `print`. Inside a live display that is not a second bar —
# it is the first one, shredded. Whoever is watching gets one bar, ours.
QUIET_ENV = {
    "HF_HUB_DISABLE_PROGRESS_BARS": "1",
    # windows without developer mode cannot symlink, and the hub explains the
    # fallback — which works — in nine lines, on every single start
    "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
    "TQDM_DISABLE": "1",
}


@contextmanager
def quiet() -> Iterator[None]:
    """Downloads with the other bars off. Everything is restored afterwards."""
    previous = {name: os.environ.get(name) for name in QUIET_ENV}
    os.environ.update(QUIET_ENV)

    # the hub reads that flag once, at import, which by now has happened: the
    # environment alone would be a no-op for the process we are in
    reenable: Optional[Callable[[], None]] = None
    try:
        # the module, not the package: the three are re-exported without being
        # declared as exports, which a type checker is right to object to
        from huggingface_hub.utils.tqdm import (
            are_progress_bars_disabled,
            disable_progress_bars,
            enable_progress_bars,
        )

        if not are_progress_bars_disabled():
            disable_progress_bars()
            reenable = enable_progress_bars
    except Exception:
        pass

    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        if reenable is not None:
            try:
                reenable()
            except Exception:
                pass


def directory_bytes(path: str) -> int:
    """Everything under `path`, part-written files included.

    huggingface_hub writes `<blob>.incomplete` beside the finished blobs while
    it works, so this grows smoothly and lands on the real size.
    """
    root = Path(path)
    if not root.is_dir():
        return 0
    return sum(file.stat().st_size for file in root.rglob("*") if file.is_file())


def watched(work: Callable[[], Any], root: str,
            on_progress: Optional[Callable[[int], None]] = None,
            tick: float = 0.3) -> Optional[Exception]:
    """Runs a download, reporting how much of it has landed in `root` as it goes.

    Returns the error it failed on, or None — a download is never worth taking
    anything else down, here or at startup. The work happens on a thread only
    so that the bytes on disk can be watched while it does.
    """
    import threading

    os.makedirs(root, exist_ok=True)
    failure: List[Exception] = []

    # the cache root is shared with every model already down there, so only the
    # bytes that arrive from here on belong to this download's bar
    already = directory_bytes(root)

    def report() -> None:
        if on_progress:
            on_progress(max(0, directory_bytes(root) - already))

    def attempt() -> None:
        try:
            work()
        except Exception as error:
            failure.append(error)

    with quiet():
        worker = threading.Thread(target=attempt, daemon=True)
        worker.start()
        while worker.is_alive():
            worker.join(tick)
            report()
    report()

    return failure[0] if failure else None
