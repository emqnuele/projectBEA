"""Writing a file without ever leaving half of one behind.

Two things read the prompt files: the engine, on every turn, and the updater,
while it is deciding what to merge. Both can be reading at the moment the
dashboard saves an edit — and `Path.write_text` truncates first and writes
after, so a reader landing in that window gets a file that is empty or cut in
half, and a soul cut in half goes straight into a system prompt.

`os.replace` is atomic on POSIX and on Windows, so a reader sees either the old
file or the new one and never the seam between them. Windows alone refuses the
swap while any other handle has the target open — a reader, an antivirus, the
search indexer — and they let go within moments, so there it is retried briefly
before the write is given up. The swap refuses readers of the file for the same
moment, so a file written here is read back with `read_text`, which waits it out.
"""

import os
import tempfile
import time
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")

WINDOWS = os.name == "nt"
# how long a swap refused by another handle is retried before the write fails
REPLACE_PATIENCE_S = 1.0


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # the temp file has to share a filesystem with the target or os.replace
    # degrades into a copy, which is exactly the window we are closing
    handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(handle, "w", encoding=encoding, newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        _patiently(lambda: os.replace(tmp, path))
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_text(path: Path, encoding: str = "utf-8") -> str:
    """A file `atomic_write_text` may be swapping at this very moment, read whole."""
    return _patiently(lambda: Path(path).read_text(encoding=encoding))


def _patiently(act: Callable[[], T]) -> T:
    deadline = time.monotonic() + REPLACE_PATIENCE_S
    wait = 0.005
    while True:
        try:
            return act()
        except PermissionError:
            # elsewhere a refusal is a real permission problem, and waiting would not change it
            if not WINDOWS or time.monotonic() >= deadline:
                raise
            time.sleep(wait)
            wait = min(wait * 2, 0.1)
