"""Downloads the free sample model and the free sample clip.

No model ships with projectBEA, for the same reason no speech model does: it is
11 MB of binary that most people will replace with their own, and a repository
is a bad place to keep either. `.gitignore` already treats large models this way.

The default is pixiv's VRM 1.0 sample, from the MIT-licensed `pixiv/three-vrm`
repository. Its own embedded metadata allows redistribution, commercial use and
requires no credit — run `tools/inspect_vrm.py` on it and it will tell you so
itself.
"""

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

RAW = "https://raw.githubusercontent.com/pixiv/three-vrm/dev/packages/three-vrm-animation/examples/models"

DOWNLOADS = [
    ("VRM1_Constraint_Twist_Sample.vrm", f"{RAW}/VRM1_Constraint_Twist_Sample.vrm", "data/models"),
    ("test.vrma", f"{RAW}/test.vrma", "data/clips"),
]


def fetch(name: str, url: str, into: Path) -> bool:
    into.mkdir(parents=True, exist_ok=True)
    target = into / name

    if target.exists():
        print(f"  {target} is already here ({target.stat().st_size / 1e6:.2f} MB)")
        return True

    print(f"  {name} -> {target}")
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            total = int(response.headers.get("content-length") or 0)
            written = 0
            # written next to the target and renamed, so an interrupted download
            # never leaves a half a model behind for the engine to choke on
            partial = target.with_suffix(target.suffix + ".part")
            with open(partial, "wb") as out:
                while True:
                    chunk = response.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
                    if total:
                        print(f"\r    {written * 100 // total}%", end="", flush=True)
            print("\r    done   ")
            partial.rename(target)
        return True
    except (urllib.error.URLError, OSError) as e:
        print(f"    failed: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", type=Path, default=Path("data/models"))
    parser.add_argument("--clips-dir", type=Path, default=Path("data/clips"))
    args = parser.parse_args()

    print("Fetching the sample model and clip (nothing is committed to the repo):")
    ok = True
    for name, url, default_dir in DOWNLOADS:
        into = args.models_dir if default_dir.endswith("models") else args.clips_dir
        ok = fetch(name, url, into) and ok

    if ok:
        print("\nPoint `stage.model_path` at the .vrm in the dashboard, under Stream.")
        print("Read what it allows:  uv run python tools/inspect_vrm.py data/models/*.vrm")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
