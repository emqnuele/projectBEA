"""The catalog downloads files that a renderer will load and run.

Nothing here reaches the network. What is checked is the promise the catalog
makes: what it writes is exactly what was pinned, and anything else leaves no
file behind for the engine to pick up.
"""

import hashlib
import io
import re
import subprocess
import sys
from pathlib import Path

import pytest

from src.modules.avatar.catalog import (
    CATALOG,
    Asset,
    FetchError,
    defaults,
    fetch,
    fetch_all,
    find,
    installed,
)

ROOT = Path(__file__).resolve().parents[1]

MODEL = b"a model, as far as anyone here is concerned"
DIGEST = hashlib.sha256(MODEL).hexdigest()


def asset(**overrides) -> Asset:
    fields = dict(id="bea", kind="model", name="Bea", filename="bea.vrm", url="http://x/bea.vrm",
                  sha256=DIGEST, size=len(MODEL), licence="test")
    fields.update(overrides)
    return Asset(**fields)


class Response(io.BytesIO):
    def __init__(self, payload: bytes):
        super().__init__(payload)
        self.headers = {"content-length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def serving(payload: bytes):
    return lambda url, timeout=None: Response(payload)


def refuse(url, timeout=None):
    raise AssertionError("it went to the network for a file it already had")


def test_a_file_that_matches_is_kept(tmp_path):
    path = fetch(asset(), tmp_path, opener=serving(MODEL))
    assert path == tmp_path / "bea.vrm"
    assert path.read_bytes() == MODEL


def test_a_file_that_does_not_match_is_thrown_away(tmp_path):
    """A model is not data: it is loaded and run by three.js in a browser."""
    with pytest.raises(FetchError):
        fetch(asset(), tmp_path, opener=serving(b"something else"))

    assert list(tmp_path.iterdir()) == [], "a file that failed its checksum was left behind"


def test_an_interrupted_download_leaves_nothing_half_written(tmp_path):
    def dies(url, timeout=None):
        raise OSError("the connection went away")

    with pytest.raises(FetchError):
        fetch(asset(), tmp_path, opener=dies)
    assert list(tmp_path.iterdir()) == []


def test_a_file_already_there_is_not_downloaded_again(tmp_path):
    (tmp_path / "bea.vrm").write_bytes(MODEL)
    assert fetch(asset(), tmp_path, opener=refuse) == tmp_path / "bea.vrm"


def test_a_model_the_user_replaced_is_never_overwritten(tmp_path):
    """At that path it is their file: a mismatch is reported, not deleted."""
    mine = b"the model I actually stream with"
    (tmp_path / "bea.vrm").write_bytes(mine)

    with pytest.raises(FetchError, match="not the file this pins"):
        fetch(asset(), tmp_path, opener=serving(MODEL))
    assert (tmp_path / "bea.vrm").read_bytes() == mine


def test_progress_is_reported_up_to_the_whole_file(tmp_path):
    seen = []
    fetch(asset(), tmp_path, opener=serving(MODEL), progress=lambda w, t: seen.append((w, t)))
    assert seen and seen[-1] == (len(MODEL), len(MODEL))
    assert [w for w, _ in seen] == sorted(w for w, _ in seen)


def test_a_file_already_there_still_reports_that_it_is_complete(tmp_path):
    (tmp_path / "bea.vrm").write_bytes(MODEL)
    seen = []
    fetch(asset(), tmp_path, opener=refuse, progress=lambda w, t: seen.append((w, t)))
    assert seen == [(len(MODEL), len(MODEL))]


def test_installed_means_the_pinned_bytes_and_nothing_else(tmp_path):
    assert not installed(asset(), tmp_path)
    (tmp_path / "bea.vrm").write_bytes(b"x" * len(MODEL))
    assert not installed(asset(), tmp_path)
    (tmp_path / "bea.vrm").write_bytes(MODEL)
    assert installed(asset(), tmp_path)


def test_models_and_clips_land_in_their_own_folders(tmp_path):
    clip = asset(id="wave", kind="clip", filename="wave.vrma")
    done = fetch_all([asset(), clip], tmp_path / "models", tmp_path / "clips", opener=serving(MODEL))
    assert done == {"bea": tmp_path / "models" / "bea.vrm", "wave": tmp_path / "clips" / "wave.vrma"}


# --- the catalog itself -----------------------------------------------------


def test_every_download_is_pinned_to_a_tag_or_a_commit_and_never_a_branch():
    """A branch moves, and a download would fetch something else that day."""
    pinned = re.compile(r"^https://raw\.githubusercontent\.com/[^/]+/[^/]+/(v\d[\w.]*|[0-9a-f]{40})/")
    for item in CATALOG:
        assert pinned.match(item.url), item.url


def test_every_asset_carries_a_full_checksum_and_a_size():
    for item in CATALOG:
        assert re.fullmatch(r"[0-9a-f]{64}", item.sha256), item.id
        assert item.size > 0
        assert item.kind in ("model", "clip")
        assert item.url.endswith("/" + item.filename)


def test_no_two_assets_share_an_id_or_a_file():
    assert len({a.id for a in CATALOG}) == len(CATALOG)
    assert len({a.filename for a in CATALOG}) == len(CATALOG)


def test_the_default_is_one_model_and_its_idle_clip():
    kinds = sorted(a.kind for a in defaults())
    assert kinds == ["clip", "model"]
    assert find("avatar-sample-b") in defaults()
    assert find("idle-loop") in defaults()


def test_a_licence_that_asks_for_credit_says_so():
    assert find("seed-san").credit
    assert not find("avatar-sample-b").credit


def test_the_cli_lists_the_catalog_without_touching_the_network():
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "fetch_model.py"), "--list"],
                         capture_output=True, text=True, cwd=ROOT, check=True).stdout
    for item in CATALOG:
        assert item.id in out
