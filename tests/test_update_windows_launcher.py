"""The launcher `uv sync` has to replace while the update runs from it.

On windows a running executable cannot be deleted, only renamed, so the updater
moves `bea.exe` aside before the sync and puts it back if nothing replaced it.
These run on any platform: the rename is plain `os.replace`, and the lock itself
is windows' to enforce, so what is tested is that the name is free during the
sync and never left empty after it.
"""

from pathlib import Path

import pytest

from src.core.update import runner

OLD = b"old launcher"
NEW = b"new launcher"


@pytest.fixture
def scripts(tmp_path, monkeypatch):
    folder = tmp_path / "Scripts"
    folder.mkdir()
    (folder / runner.LAUNCHER).write_bytes(OLD)
    monkeypatch.setattr(runner, "WINDOWS", True)
    monkeypatch.setattr(runner, "_scripts_dir", lambda: folder)
    monkeypatch.setattr(runner.shutil, "which", lambda name: f"/usr/bin/{name}")
    return folder


def sync(monkeypatch, command):
    steps = []
    monkeypatch.setattr(runner, "_command", command)
    runner._sync_dependencies(Path("."), ["uv.lock"], lambda *args: steps.append(args))
    return steps[-1]


def leftovers(folder):
    return sorted(p.name for p in folder.glob(f"{runner.LAUNCHER}.*.old"))


def test_the_name_is_free_while_uv_sync_runs_and_the_new_launcher_stays(scripts, monkeypatch):
    seen = []

    def uv(cwd, args):
        launcher = scripts / runner.LAUNCHER
        seen.append(launcher.exists())
        launcher.write_bytes(NEW)
        return True, ""

    last = sync(monkeypatch, uv)

    assert seen == [False]
    assert last[1] == runner.DONE
    assert (scripts / runner.LAUNCHER).read_bytes() == NEW
    # the old one is still the running process, so it waits for the next update
    assert len(leftovers(scripts)) == 1


def test_the_next_update_clears_what_the_last_one_moved_aside(scripts, monkeypatch):
    (scripts / f"{runner.LAUNCHER}.1.old").write_bytes(OLD)

    def uv(cwd, args):
        (scripts / runner.LAUNCHER).write_bytes(NEW)
        return True, ""

    sync(monkeypatch, uv)

    assert f"{runner.LAUNCHER}.1.old" not in leftovers(scripts)


def test_a_sync_that_does_not_reinstall_the_project_gets_the_old_launcher_back(scripts, monkeypatch):
    sync(monkeypatch, lambda cwd, args: (True, ""))

    assert (scripts / runner.LAUNCHER).read_bytes() == OLD
    assert leftovers(scripts) == []


def test_a_failed_sync_gets_the_old_launcher_back(scripts, monkeypatch):
    last = sync(monkeypatch, lambda cwd, args: (False, "`uv sync` failed: no network"))

    assert last[1] == runner.FAILED
    assert (scripts / runner.LAUNCHER).read_bytes() == OLD
    assert leftovers(scripts) == []


def test_a_sync_that_raises_still_gets_the_old_launcher_back(scripts, monkeypatch):
    def uv(cwd, args):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        sync(monkeypatch, uv)

    assert (scripts / runner.LAUNCHER).read_bytes() == OLD


def test_a_launcher_that_cannot_be_moved_leaves_the_sync_as_it_was(scripts, monkeypatch):
    def refuse(src, dst):
        raise PermissionError("in use")

    monkeypatch.setattr(runner.os, "replace", refuse)
    ran = []
    last = sync(monkeypatch, lambda cwd, args: (ran.append(args), (True, ""))[1])

    assert ran == [["uv", "sync"]]
    assert last[1] == runner.DONE
    assert (scripts / runner.LAUNCHER).read_bytes() == OLD


def test_a_stale_copy_still_in_use_does_not_stop_the_update(scripts, monkeypatch):
    stale = scripts / f"{runner.LAUNCHER}.1.old"
    stale.write_bytes(OLD)
    real_unlink = Path.unlink

    def locked(self, *args, **kwargs):
        if self == stale:
            raise PermissionError("in use")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked)
    last = sync(monkeypatch, lambda cwd, args: (True, ""))

    assert last[1] == runner.DONE
    assert stale.exists()
    assert (scripts / runner.LAUNCHER).read_bytes() == OLD


def test_nothing_is_moved_off_windows(scripts, monkeypatch):
    monkeypatch.setattr(runner, "WINDOWS", False)
    seen = []

    def uv(cwd, args):
        seen.append((scripts / runner.LAUNCHER).exists())
        return True, ""

    sync(monkeypatch, uv)

    assert seen == [True]
    assert leftovers(scripts) == []
