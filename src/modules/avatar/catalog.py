"""The free models and clips projectBEA knows how to fetch, pinned to the byte.

No model ships with the repository: it is tens of megabytes of binary most
people replace with their own. What ships is this list — where each file lives
upstream, what it must hash to and what its licence allows — so `make model`
and the dashboard's download button fetch exactly the same bytes.

Every URL points at a commit or a tag, never a branch. What arrives is loaded
and run by a renderer, so a file that does not match its checksum is deleted
rather than kept, and a file already on disk is never overwritten: at that path
it is the user's.
"""

import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Tuple

CHATVRM = "https://raw.githubusercontent.com/pixiv/ChatVRM/b542aa00e19dccf9fc48ba340cf7eee011d2329a/public"
THREE_VRM = "https://raw.githubusercontent.com/pixiv/three-vrm/v3.5.5/packages/three-vrm-animation/examples/models"
VRMC = "https://raw.githubusercontent.com/vrm-c/vrm-specification/821c11b250d8c70d5804ee13431e42bee56ea9c0/samples"

KINDS = ("model", "clip")

CHUNK = 1 << 16

Progress = Callable[[int, int], None]


@dataclass(frozen=True)
class Asset:
    id: str
    kind: str
    name: str
    filename: str
    url: str
    sha256: str
    size: int
    licence: str
    credit: str = ""
    default: bool = False


CATALOG: Tuple[Asset, ...] = (
    Asset("avatar-sample-b", "model", "AvatarSample_B", "AvatarSample_B.vrm",
          f"{CHATVRM}/AvatarSample_B.vrm",
          "ffbd8c92a9e67c0a948f69c7a2eec91e5c282c9ae70e9184309fc164d74cbc27", 21047556,
          "VRoid Project (pixiv). Commercial use, redistribution and changes allowed. No credit needed.",
          default=True),
    Asset("idle-loop", "clip", "idle_loop", "idle_loop.vrma",
          f"{CHATVRM}/idle_loop.vrma",
          "ace95ba6dcc0bdf2ed1081c002332b4184441117c8d543b6f642b3d2c5cf99be", 157664,
          "pixiv/ChatVRM, MIT.",
          default=True),
    Asset("constraint-twist", "model", "Constraint Twist Sample", "VRM1_Constraint_Twist_Sample.vrm",
          f"{THREE_VRM}/VRM1_Constraint_Twist_Sample.vrm",
          "12c2b97e95e700783a6a550dc0eee2d7880aeedccef9ae67bc4c5a2f0f2631a2", 10776032,
          "pixiv Inc., MIT sample."),
    Asset("seed-san", "model", "Seed-san", "Seed-san.vrm",
          f"{VRMC}/Seed-san/vrm/Seed-san.vrm",
          "624d0d554bc205bbdc33e22a68a2c3c20edebb3e573011ead8878a65e5329b23", 10917800,
          "VirtualCast, Inc. Commercial use and redistribution allowed.",
          credit="Seed-san by VirtualCast, Inc."),
)

BY_ID: Dict[str, Asset] = {asset.id: asset for asset in CATALOG}


class FetchError(Exception):
    """A download that did not leave the pinned file on disk, in words for a person."""


def defaults() -> Tuple[Asset, ...]:
    return tuple(asset for asset in CATALOG if asset.default)


def find(asset_id: str) -> Optional[Asset]:
    return BY_ID.get(asset_id)


def folder_for(asset: Asset, models_dir: Path, clips_dir: Path) -> Path:
    return models_dir if asset.kind == "model" else clips_dir


def digest_of(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def installed(asset: Asset, into: Path) -> bool:
    """Whether the pinned file is already there, byte for byte."""
    target = into / asset.filename
    return target.is_file() and target.stat().st_size == asset.size and digest_of(target) == asset.sha256


def fetch(asset: Asset, into: Path, *, opener=urllib.request.urlopen,
          progress: Optional[Progress] = None) -> Path:
    """Puts the pinned file at `into/filename` and returns its path.

    A file already there with the right hash costs no network. Anything else
    raises `FetchError` and leaves nothing half-written behind.
    """
    into.mkdir(parents=True, exist_ok=True)
    target = into / asset.filename

    if target.exists():
        if digest_of(target) == asset.sha256:
            if progress:
                progress(asset.size, asset.size)
            return target
        raise FetchError(f"{target} is not the file this pins. Delete it to fetch the pinned one.")

    sha = hashlib.sha256()
    # written beside the target and renamed, so an interrupted download never leaves half a model
    partial = target.with_suffix(target.suffix + ".part")
    try:
        with opener(asset.url, timeout=120) as response:
            total = int(response.headers.get("content-length") or 0) or asset.size
            written = 0
            with open(partial, "wb") as out:
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    out.write(chunk)
                    sha.update(chunk)
                    written += len(chunk)
                    if progress:
                        progress(written, total)
    except (urllib.error.URLError, OSError) as e:
        partial.unlink(missing_ok=True)
        raise FetchError(f"{asset.filename}: {e}") from e

    if sha.hexdigest() != asset.sha256:
        # a renderer would load and run it, so it is deleted rather than kept
        partial.unlink(missing_ok=True)
        raise FetchError(f"{asset.filename} does not match its checksum and was thrown away")

    partial.rename(target)
    return target


def fetch_all(assets: Iterable[Asset], models_dir: Path, clips_dir: Path, *,
              opener=urllib.request.urlopen,
              progress: Optional[Callable[[Asset, int, int], None]] = None) -> Dict[str, Path]:
    """Fetches each asset into its folder; the first failure stops the rest."""
    done: Dict[str, Path] = {}
    for asset in assets:
        report = (lambda w, t, a=asset: progress(a, w, t)) if progress else None
        done[asset.id] = fetch(asset, folder_for(asset, models_dir, clips_dir),
                               opener=opener, progress=report)
    return done
