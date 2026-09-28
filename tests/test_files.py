"""A file is swapped whole, and on Windows a reader holding it only delays the swap.

Windows refuses to replace a file any other handle has open: the engine reading
the soul on a turn, the dashboard reading a conversation, an antivirus scan.
They let go within moments; a save that gave up on the first refusal lost the
write for nothing. The swap refuses readers for the same moment, and a soul read
as empty because of it would have sent a turn out with no persona.
"""

import os
from pathlib import Path

import pytest

from src.utils import files
from src.utils.files import atomic_write_text, read_text


def unreadable(times: int):
    """`Path.read_text` as Windows answers while the file is being swapped, `times` times."""
    real = Path.read_text
    left = [times]

    def read(self, *args, **kwargs):
        if left[0] > 0:
            left[0] -= 1
            raise PermissionError(13, "Permission denied")
        return real(self, *args, **kwargs)

    return read


def test_on_windows_a_read_landing_on_a_swap_gets_the_file_once_it_is_done(tmp_path, monkeypatch):
    target = tmp_path / "soul.md"
    target.write_text("her", encoding="utf-8")
    monkeypatch.setattr(files, "WINDOWS", True)
    monkeypatch.setattr(Path, "read_text", unreadable(3))

    assert read_text(target) == "her"


def test_the_soul_is_never_read_as_empty_because_a_save_was_landing(tmp_path, monkeypatch):
    from src.core.persona_store import SoulFile

    soul = SoulFile(tmp_path / "soul.md")
    soul.path.write_text("her", encoding="utf-8")
    monkeypatch.setattr(files, "WINDOWS", True)
    monkeypatch.setattr(Path, "read_text", unreadable(2))

    assert soul.read() == "her"


def test_elsewhere_a_read_refused_is_real_and_is_not_waited_on(tmp_path, monkeypatch):
    target = tmp_path / "soul.md"
    target.write_text("her", encoding="utf-8")
    monkeypatch.setattr(files, "WINDOWS", False)
    monkeypatch.setattr(Path, "read_text", unreadable(1))

    with pytest.raises(PermissionError):
        read_text(target)


def refused(times: int):
    """`os.replace` as Windows answers while someone else holds the target, `times` times."""
    real = os.replace
    left = [times]

    def replace(src, dst):
        if left[0] > 0:
            left[0] -= 1
            raise PermissionError(5, "Access is denied")
        real(src, dst)

    return replace


def test_on_windows_a_swap_refused_while_a_reader_holds_the_file_lands_once_it_lets_go(tmp_path, monkeypatch):
    target = tmp_path / "soul.md"
    target.write_text("old", encoding="utf-8")
    monkeypatch.setattr(files, "WINDOWS", True)
    monkeypatch.setattr(files.os, "replace", refused(3))

    atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"
    assert list(tmp_path.iterdir()) == [target], "a temporary file was left behind"


def test_on_windows_a_file_held_for_good_still_fails_and_leaves_the_old_one(tmp_path, monkeypatch):
    target = tmp_path / "soul.md"
    target.write_text("old", encoding="utf-8")
    monkeypatch.setattr(files, "WINDOWS", True)
    monkeypatch.setattr(files, "REPLACE_PATIENCE_S", 0.05)
    monkeypatch.setattr(files.os, "replace", refused(10_000))

    with pytest.raises(PermissionError):
        atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.iterdir()) == [target], "a temporary file was left behind"


def test_elsewhere_a_permission_error_is_real_and_is_not_waited_on(tmp_path, monkeypatch):
    target = tmp_path / "soul.md"
    monkeypatch.setattr(files, "WINDOWS", False)
    monkeypatch.setattr(files.os, "replace", refused(1))

    with pytest.raises(PermissionError):
        atomic_write_text(target, "new")
