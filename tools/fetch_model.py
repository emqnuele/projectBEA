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
import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

# pinned to the release the dashboard's own three-vrm is built against. A branch
# is a moving target: `make model` would quietly fetch something else the day
# upstream pushes, and the checksums below would be the first to know.
TAG = "v3.5.5"
RAW = f"https://raw.githubusercontent.com/pixiv/three-vrm/{TAG}/packages/three-vrm-animation/examples/models"

# name, where it goes, and what it must hash to
DOWNLOADS = [
    ("VRM1_Constraint_Twist_Sample.vrm", "models",
     "12c2b97e95e700783a6a550dc0eee2d7880aeedccef9ae67bc4c5a2f0f2631a2"),
    ("test.vrma", "clips",
     "38d0fd12d61e896f1a970b5e358ebb41a96c8d5ee8e284496ea18f0ba1f04e7b"),
]


def digest_of(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def fetch(name: str, url: str, into: Path, digest: str, opener=urllib.request.urlopen) -> bool:
    into.mkdir(parents=True, exist_ok=True)
    target = into / name

    if target.exists():
        if digest_of(target) == digest:
            print(f"  {target} is already here ({target.stat().st_size / 1e6:.2f} MB)")
            return True
        # never overwritten: at this path it is the user's file, whether they put
        # a newer sample there or a download died halfway through
        print(f"  {target} is not the file this pins. Delete it to fetch the pinned one.")
        return False

    print(f"  {name} -> {target}")
    sha = hashlib.sha256()
    # written next to the target and renamed, so an interrupted download
    # never leaves a half a model behind for the engine to choke on
    partial = target.with_suffix(target.suffix + ".part")
    try:
        with opener(url, timeout=120) as response:
            total = int(response.headers.get("content-length") or 0)
            written = 0
            with open(partial, "wb") as out:
                while True:
                    chunk = response.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
                    sha.update(chunk)
                    written += len(chunk)
                    if total:
                        print(f"\r    {written * 100 // total}%", end="", flush=True)
        print("\r    done   ")
    except (urllib.error.URLError, OSError) as e:
        partial.unlink(missing_ok=True)
        print(f"    failed: {e}")
        return False

    if sha.hexdigest() != digest:
        # what arrived is not what was pinned. It is a model that will be loaded
        # and executed by a renderer, so it is deleted rather than kept around.
        partial.unlink(missing_ok=True)
        print(f"    failed: {name} does not match its checksum and was thrown away")
        return False

    partial.rename(target)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", type=Path, default=Path("data/models"))
    parser.add_argument("--clips-dir", type=Path, default=Path("data/clips"))
    args = parser.parse_args()

    folders = {"models": args.models_dir, "clips": args.clips_dir}

    print(f"Fetching the sample model and clip from three-vrm {TAG} "
          f"(nothing is committed to the repo):")
    ok = True
    for name, kind, digest in DOWNLOADS:
        ok = fetch(name, f"{RAW}/{name}", folders[kind], digest) and ok

    if ok:
        print("\nPoint `stage.model_path` at the .vrm in the dashboard, under Stream.")
        print("Read what it allows:  uv run python tools/inspect_vrm.py data/models/*.vrm")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
