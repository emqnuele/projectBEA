import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from version_bumped import parse, verdict  # noqa: E402


def pyproject(version: str) -> str:
    return (f'[project]\nname = "projectbea"\nversion = "{version}"\n\n'
            f'[tool.ruff]\ntarget-version = "py310"\n')


def test_code_changed_without_a_bump_is_refused():
    problem = verdict(["src/core/brain.py"], pyproject("2.6.0"), pyproject("2.6.0"))
    assert problem is not None
    assert "2.6.1" in problem and "2.7.0" in problem


def test_code_changed_with_a_bump_passes():
    assert verdict(["src/core/brain.py"], pyproject("2.6.0"), pyproject("2.6.1")) is None


def test_a_version_going_down_is_refused():
    assert verdict(["src/core/brain.py"], pyproject("2.6.0"), pyproject("2.5.9")) is not None


def test_minor_beats_a_larger_patch():
    assert verdict(["data/prompts/soul.md"], pyproject("2.6.9"), pyproject("2.7.0")) is None


@pytest.mark.parametrize("path", ["tests/test_brain.py", ".github/workflows/ci.yml",
                                  "docs/setup.md", "README.md", "tools/bench.py"])
def test_what_nobody_runs_needs_no_bump(path):
    assert verdict([path], pyproject("2.6.0"), pyproject("2.6.0")) is None


@pytest.mark.parametrize("path", ["data/prompts/minecraft.md", "uv.lock", "config.example.json"])
def test_data_dependencies_and_example_config_ship(path):
    assert verdict([path], pyproject("2.6.0"), pyproject("2.6.0")) is not None


def test_the_ruff_target_is_not_taken_for_the_version():
    text = '[tool.ruff]\ntarget-version = "py310"\n\n[project]\nversion = "2.6.0"\n'
    assert parse(text) == (2, 6, 0)


def test_the_real_pyproject_has_a_version():
    assert parse((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
