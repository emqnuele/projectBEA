"""Fails a pull request that changes what she ships without raising her version.

Only paths that reach an install count: code, data, dependencies and the example
config. Tests, CI and docs change nothing anybody runs, so they need no bump.

    uv run python tools/version_bumped.py origin/main
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent

SHIPPED = ("src/", "data/", "pyproject.toml", "uv.lock", "config.example.json")

# anchored, so `target-version` in the ruff section never matches
VERSION = re.compile(r'^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"\s*$', re.M)

Version = Tuple[int, int, int]


def parse(pyproject: str) -> Version:
    match = VERSION.search(pyproject)
    if match is None:
        raise ValueError('no `version = "X.Y.Z"` in pyproject.toml')
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def shipped(paths: Iterable[str]) -> List[str]:
    return [p for p in paths if p.startswith(SHIPPED)]


def verdict(changed: Iterable[str], base: str, head: str) -> Optional[str]:
    """None when the pull request is fine, else what is wrong with it."""
    touched = shipped(changed)
    if not touched:
        return None
    before, after = parse(base), parse(head)
    if after > before:
        return None
    shown = ", ".join(touched[:5]) + (" …" if len(touched) > 5 else "")
    was = ".".join(map(str, before))
    return (
        f"this changes what ships ({shown}) but the version is still {was}. "
        f"Raise it in pyproject.toml (a fix: {before[0]}.{before[1]}.{before[2] + 1}, "
        f"something new: {before[0]}.{before[1] + 1}.0) and run `uv lock`."
    )


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    base_ref = argv[1]
    changed = _git("diff", "--name-only", f"{base_ref}...HEAD").split()
    problem = verdict(changed, _git("show", f"{base_ref}:pyproject.toml"),
                      (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if problem:
        print(f"version not raised: {problem}", file=sys.stderr)
        return 1
    print(f"version ok: {'.'.join(map(str, parse((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
