"""Downloads the free models and clips in the catalog, checked to the byte.

No model ships with projectBEA, for the same reason no speech model does: it is
tens of megabytes of binary that most people replace with their own. What
ships is `src/modules/avatar/catalog.py` — where each file lives upstream and
what it must hash to — and this tool and the dashboard's download button both
fetch from it.

    uv run python tools/fetch_model.py              # the default model and idle clip
    uv run python tools/fetch_model.py --all        # everything in the catalog
    uv run python tools/fetch_model.py --id seed-san
    uv run python tools/fetch_model.py --list
"""

import argparse
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.modules.avatar.catalog import (  # noqa: E402
    CATALOG,
    Asset,
    FetchError,
    defaults,
    fetch,
    find,
    folder_for,
)


def chosen(args) -> List[Asset]:
    if args.all:
        return list(CATALOG)
    if args.id:
        picked = []
        for asset_id in args.id:
            asset = find(asset_id)
            if asset is None:
                raise SystemExit(f"No asset called {asset_id!r}. Try --list.")
            picked.append(asset)
        return picked
    return list(defaults())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models-dir", type=Path, default=Path("data/models"))
    parser.add_argument("--clips-dir", type=Path, default=Path("data/clips"))
    parser.add_argument("--all", action="store_true", help="every model and clip in the catalog")
    parser.add_argument("--id", action="append", help="one asset by id; may be repeated")
    parser.add_argument("--list", action="store_true", help="show the catalog and exit")
    args = parser.parse_args()

    if args.list:
        for asset in CATALOG:
            mark = "*" if asset.default else " "
            print(f" {mark} {asset.id:<18} {asset.kind:<5} {asset.size / 1e6:6.2f} MB  {asset.licence}")
            if asset.credit:
                print(f"   {'':<18} credit required: {asset.credit}")
        return 0

    print("Fetching from the pinned catalog (nothing is committed to the repo):")
    ok = True
    for asset in chosen(args):
        into = folder_for(asset, args.models_dir, args.clips_dir)
        print(f"  {asset.filename} -> {into / asset.filename}")

        def progress(written: int, total: int) -> None:
            print(f"\r    {written * 100 // max(1, total)}%", end="", flush=True)

        try:
            fetch(asset, into, progress=progress)
            print("\r    done   ")
            if asset.credit:
                print(f"    credit required on stream: {asset.credit}")
        except FetchError as e:
            print(f"\r    failed: {e}")
            ok = False

    if ok:
        print("\nPick the model in the dashboard, under Stream, or set `stage.model_path` to it.")
        print("Read what it allows:  uv run python tools/inspect_vrm.py data/models/*.vrm")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
