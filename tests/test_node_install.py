"""Every javascript part of her gets installed, not only the visible one.

The dashboard is the obvious one — a missing dashboard announces itself. Her
discord voice is a node program too, and nothing installed it: the toggle in the
UI turned on a bot whose packages had never been fetched, and it went on looking
enabled while never coming online.
"""

from pathlib import Path

import pytest

from src.setup import node


def test_the_discord_bot_is_one_of_the_projects():
    assert "discord bot" in {p.name for p in node.PROJECTS}


def test_every_project_points_at_a_real_package_json():
    for project in node.PROJECTS:
        assert (Path(project.path) / "package.json").is_file(), project.name


def test_only_the_dashboard_needs_building():
    """The bot is run from source; there is nothing to bundle."""
    builds = {p.name for p in node.PROJECTS if p.builds}
    assert builds == {"dashboard"}


def test_all_of_them_are_installed(monkeypatch):
    ran = []

    def record(project, args, root=None):
        ran.append((project.name, args))
        return True, ""

    monkeypatch.setattr(node.shutil, "which", lambda name: "/usr/bin/npm")
    monkeypatch.setattr(node, "run", record)

    assert node.install_all() == 0
    assert ("discord bot", ["install", "--no-audit", "--no-fund"]) in ran
    assert ("dashboard", ["run", "build"]) in ran


def test_a_machine_without_node_is_told_rather_than_left_guessing(monkeypatch, caplog):
    monkeypatch.setattr(node.shutil, "which", lambda name: None)
    with caplog.at_level("ERROR", logger="bea.setup.node"):
        assert node.install_all() == 1
    assert "nodejs.org" in caplog.text


def test_one_project_failing_does_not_hide_the_others(monkeypatch):
    ran = []

    def record(project, args, root=None):
        ran.append(project.name)
        return project.name != "dashboard", "npm exploded"

    monkeypatch.setattr(node.shutil, "which", lambda name: "/usr/bin/npm")
    monkeypatch.setattr(node, "run", record)

    assert node.install_all() == 1
    assert "discord bot" in ran


@pytest.mark.parametrize("project", node.PROJECTS, ids=lambda p: p.name)
def test_a_project_knows_whether_it_has_been_installed(project, tmp_path):
    assert not project.installed(tmp_path)
    (tmp_path / project.path / "node_modules").mkdir(parents=True)
    assert project.installed(tmp_path)


# --- windows calls npm something else ----------------------------------------


def test_npm_is_run_under_the_name_this_machine_gave_it(monkeypatch):
    """On windows npm is `npm.cmd`, and subprocess will not find it by the
    bare name — every npm step failed saying npm was not installed."""
    seen = {}

    def fake_run(args, **kwargs):
        seen["argv0"] = args[0]
        raise RuntimeError("far enough: the name is what is being tested")

    monkeypatch.setattr(node.shutil, "which", lambda name: r"C:\Program Files\nodejs\npm.cmd")
    monkeypatch.setattr(node.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError):
        node.run(node.PROJECTS[0], ["install"])
    assert seen["argv0"].endswith("npm.cmd")


def test_a_missing_npm_is_reported_rather_than_raised(monkeypatch):
    monkeypatch.setattr(node.shutil, "which", lambda name: None)
    ok, detail = node.run(node.PROJECTS[0], ["install"])
    assert not ok
    assert "npm is not installed" in detail
