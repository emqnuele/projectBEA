"""Writing a file without ever leaving half of one behind.

Two things read the prompt files: the engine, on every turn, and the updater,
while it is deciding what to merge. Both can be reading at the moment the
dashboard saves an edit — and `Path.write_text` truncates first and writes
after, so a reader landing in that window gets a file that is empty or cut in
half, and a soul cut in half goes straight into a system prompt.

`os.replace` is atomic on POSIX and on Windows, so a reader sees either the old
file or the new one and never the seam between them.
"""

import os
import tempfile
from pathlib import Path


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
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
