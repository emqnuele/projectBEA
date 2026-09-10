"""`make model` downloads a file that a renderer will load and run.

Nothing here reaches the network. What is checked is the promise the tool makes:
what it writes is exactly what was pinned, and anything else leaves no file
behind for the engine to pick up.
"""

import hashlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from fetch_model import DOWNLOADS, RAW, TAG, fetch  # noqa: E402

MODEL = b"a model, as far as anyone here is concerned"
DIGEST = hashlib.sha256(MODEL).hexdigest()


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


def test_a_file_that_matches_is_kept(tmp_path):
    assert fetch("bea.vrm", "http://x/bea.vrm", tmp_path, DIGEST, serving(MODEL))
    assert (tmp_path / "bea.vrm").read_bytes() == MODEL


def test_a_file_that_does_not_match_is_thrown_away(tmp_path):
    """A model is not data: it is loaded and run by three.js in a browser."""
    assert not fetch("bea.vrm", "http://x/bea.vrm", tmp_path, DIGEST, serving(b"something else"))

    assert list(tmp_path.iterdir()) == [], "a file that failed its checksum was left behind"


def test_an_interrupted_download_leaves_nothing_half_written(tmp_path):
    def dies(url, timeout=None):
        raise OSError("the connection went away")

    assert not fetch("bea.vrm", "http://x/bea.vrm", tmp_path, DIGEST, dies)
    assert list(tmp_path.iterdir()) == []


def test_a_file_already_there_is_not_downloaded_again(tmp_path):
    (tmp_path / "bea.vrm").write_bytes(MODEL)

    def refuse(url, timeout=None):
        raise AssertionError("it went to the network for a file it already had")

    assert fetch("bea.vrm", "http://x/bea.vrm", tmp_path, DIGEST, refuse)


def test_a_model_the_user_replaced_is_never_overwritten(tmp_path):
    """At that path it is their file: a mismatch is reported, not deleted."""
    mine = b"the model I actually stream with"
    (tmp_path / "bea.vrm").write_bytes(mine)

    assert not fetch("bea.vrm", "http://x/bea.vrm", tmp_path, DIGEST, serving(MODEL))
    assert (tmp_path / "bea.vrm").read_bytes() == mine


def test_the_download_is_pinned_to_a_tag_and_not_a_branch():
    """A branch moves, and `make model` would fetch something else that day."""
    assert TAG.startswith("v")
    assert f"/{TAG}/" in RAW
    assert "/dev/" not in RAW
    assert all(len(digest) == 64 for _name, _kind, digest in DOWNLOADS)
