"""Build scripts: what the body may write, and what it may not."""

import tracemalloc

import pytest

from src.core.skills.minecraft import buildscript
from src.core.skills.minecraft.blueprint import expand, rotate
from src.core.skills.minecraft.buildscript import ScriptError, check, preview, run, to_build_args

TOWER = """
for y in range(6):
    walls(0, y, 0, 4, y, 4, 'cobblestone')
fill(0, 6, 0, 4, 6, 4, 'oak_planks')
set(2, 0, 0, 'air')
set(2, 1, 0, 'air')
"""


def test_a_tower_in_six_lines():
    cells, notes = run(TOWER)
    assert len(cells) == 6 * 16 + 25
    assert cells[(2, 0, 0)] == "air" and cells[(0, 3, 0)] == "cobblestone"
    assert notes == []


def test_cells_become_the_same_build_the_mod_already_takes():
    cells, _ = run("line(-2, 0, 3, 2, 4, 3, 'stone')\ncircle(0, 0, 0, 3, 'glass')")
    for rotation in (0, 90, 180, 270):
        args = to_build_args(cells, 100, 64, -20, rotation)
        want = {(100 + rx, 64 + ry, -20 + rz): b
                for (cx, cy, cz), b in cells.items()
                for rx, ry, rz in [rotate(cx, cy, cz, rotation)]}
        assert expand(args).cells == want


def test_preview_says_size_cost_and_what_is_missing():
    args, bp, text = preview(TOWER, 10, 64, 10, 0, {"cobblestone": 50})
    assert text.splitlines()[0].startswith("121 cells in a 5x7x5 box")
    assert "cobblestone x94" in text and "oak_planks x25" in text
    assert "missing: cobblestone x44, oak_planks x25" in text
    assert args["origin"] == {"x": 10, "y": 64, "z": 10}


def test_maths_and_notes_are_available():
    cells, notes = run("r = 4\nfor a in range(0, 360, 30):\n"
                       "    set(round(r * cos(radians(a))), 0, round(r * sin(radians(a))), 'stone')\n"
                       "note('ring of', len(range(0, 360, 30)))")
    assert (4, 0, 0) in cells and (-4, 0, 0) in cells
    assert notes == ["ring of 12"]


@pytest.mark.parametrize("source, error", [
    ("import os", "Import is not allowed"),
    ("from os import system", "ImportFrom is not allowed"),
    ("().__class__.__bases__", "Attribute is not allowed"),
    ("x = 'a'.upper()", "Attribute is not allowed"),
    ("f'{x.__class__}'", "Attribute is not allowed"),
    ("__import__('os')", "names starting with _"),
    ("def _f(): pass", "names starting with _"),
    ("lambda: 1", "Lambda is not allowed"),
    ("with open('x') as f: pass", "With is not allowed"),
    ("try:\n    pass\nexcept Exception:\n    pass", "Try is not allowed"),
    ("class A: pass", "ClassDef is not allowed"),
    ("global x", "Global is not allowed"),
    ("x = (yield)", "Yield is not allowed"),
    ("fill(0,0,0,1,1,1, 'stone'", "line 1:"),
])
def test_refused_before_running(source, error):
    with pytest.raises(ScriptError, match=error):
        check(source)


@pytest.mark.parametrize("source, error", [
    ("open('/etc/passwd')", "NameError: name 'open' is not defined"),
    ("eval('1')", "NameError: name 'eval' is not defined"),
    ("getattr(1, 'real')", "NameError: name 'getattr' is not defined"),
    ("while True:\n    pass", "longer than 3 s"),
    ("fill(0, 0, 0, 20, 20, 20, 'stone')", "more than 2000 cells"),
    ("set(0, 0, 0, 5)", "block must be a name"),
    ("set(0, 0, 0, 'Stone Bricks')", "is not a block name"),
    ("x = 1", "drew nothing"),
    ("set(0, 0, 0, 'stone')\nfill(0, 0)", "line 2: TypeError"),
    ("x = [0] * 10**10", "MemoryError|crashed|more than 512 MB"),
    ("x = [[0] * 10**6 for i in range(10**6)]", "MemoryError|more than 512 MB"),
])
def test_refused_while_running(source, error):
    with pytest.raises(ScriptError, match=error):
        run(source)


def test_long_scripts_are_refused():
    with pytest.raises(ScriptError, match="keep it under"):
        check("x = 1\n" * 1000)


@pytest.mark.parametrize("far", [(1200, 64, -900), (3000, 300, -3000)])
def test_absolute_and_relative_mixed_up_is_refused_before_any_grid(far):
    # these two cells used to become a dense grid of hundreds of millions of cells in the brain
    tracemalloc.start()
    try:
        with pytest.raises(ScriptError, match="spans .* blocks along x .*relative to the origin"):
            to_build_args({(0, 0, 0): "stone", far: "stone"}, 0, 0, 0)
        assert tracemalloc.get_traced_memory()[1] < 2**20
    finally:
        tracemalloc.stop()


def test_a_long_diagonal_stays_a_few_rows_of_text():
    cells = {(i, i, i): "stone" for i in range(256)}
    args = to_build_args(cells, 0, 0, 0)
    assert len(args["layers"]) == 256
    assert sum(len(row) for layer in args["layers"] for row in layer) == sum(range(1, 257))
    assert expand(args).cells == {c: "stone" for c in cells}


def test_the_script_gets_none_of_the_brains_environment(monkeypatch):
    monkeypatch.setattr(buildscript.sys, "platform", "darwin")
    assert buildscript._child_env() == {}
    monkeypatch.setattr(buildscript.sys, "platform", "win32")
    monkeypatch.setenv("SYSTEMROOT", "C:\\Windows")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert buildscript._child_env() == {"SYSTEMROOT": "C:\\Windows"}


def test_a_parser_that_runs_out_of_stack_is_a_script_error(monkeypatch):
    def overflow(source):
        raise RecursionError("maximum recursion depth exceeded during compilation")

    monkeypatch.setattr(buildscript.ast, "parse", overflow)
    with pytest.raises(ScriptError, match="nested too deeply"):
        check("x = 1")
