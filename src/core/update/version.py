"""One version number, read from one place.

There used to be two: `pyproject.toml` said one thing and the dashboard's
sidebar had another hardcoded in a constant. That is harmless right up until
something has to answer "what are you running, and is it older than what is on
GitHub" — at which point two answers is the same as none.

The installed metadata is the source; the file is the fallback for a checkout
that was never `uv sync`'d, which is exactly the state a broken install is in.
"""

import re
from functools import lru_cache
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[3] / "pyproject.toml"

UNKNOWN = "unknown"


@lru_cache(maxsize=1)
def current_version() -> str:
    try:
        from importlib.metadata import version

        return version("projectbea")
    except Exception:  # noqa: BLE001 - metadata missing or unreadable, fall through
        pass

    try:
        # deliberately not tomllib: this has to work on 3.10, and one regex is
        # cheaper than a conditional import for a single well-known line
        match = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.MULTILINE)
        return match.group(1) if match else UNKNOWN
    except OSError:
        return UNKNOWN
