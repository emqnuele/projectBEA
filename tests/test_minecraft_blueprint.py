"""Blueprint expansion: the same vectors BeaCraft's BuildSkill is tested against."""

import json
import re
from pathlib import Path

import pytest

from src.core.skills.minecraft.blueprint import (
    BlueprintError,
    expand,
    from_template,
    items_needed,
    resolve_generic,
    rotate,
    satisfied,
    shortfall,
)

ROOT = Path(__file__).resolve().parents[1]
VECTOR_DIR = ROOT / "tests" / "fixtures" / "minecraft_blueprints"
VECTORS = sorted(VECTOR_DIR.glob("*.json"))
# BeaCraft's copy of the vectors, when its checkout sits next to this one
MOD_VECTORS = ROOT.parent / "beacraft" / "src" / "test" / "resources" / "blueprints"
TEMPLATES = ROOT / "data" / "minecraft" / "blueprints"


def _cells(bp):
    return {f"{x},{y},{z}": b for (x, y, z), b in bp.cells.items()}


@pytest.mark.parametrize("path", VECTORS, ids=lambda p: p.stem)
def test_shared_vectors(path):
    vector = json.loads(path.read_text())
    if "error" in vector:
        with pytest.raises(BlueprintError, match=re.escape(vector["error"])):
            expand(vector["args"])
        return
    bp = expand(vector["args"])
    assert _cells(bp) == vector["cells"]
    assert bp.items == vector["items"]


def test_rotation_is_clockwise_from_above():
    assert rotate(1, 0, 0, 90) == (0, 0, 1)      # east -> south
    assert rotate(0, 0, 1, 90) == (-1, 0, 0)     # south -> west
    assert rotate(2, 5, 3, 180) == (-2, 5, -3)
    assert rotate(1, 0, 0, 270) == (0, 0, -1)    # east -> north


def test_rotating_a_non_square_template_keeps_every_cell():
    tpl = json.loads((TEMPLATES / "small_wood_house.json").read_text())
    base = expand(from_template(tpl, 0, 64, 0, 0, {}))
    for r in (90, 180, 270):
        turned = expand(from_template(tpl, 0, 64, 0, r, {}))
        assert len(turned.cells) == len(base.cells)
        assert turned.items == base.items


def test_unknown_argument_is_named():
    with pytest.raises(BlueprintError, match="unknown argument: size"):
        expand({"origin": {"x": 0, "y": 0, "z": 0}, "size": 3, "ops": []})


def test_a_door_and_a_bed_cost_one_item_each():
    cells = {(0, 0, 0): "oak_door", (0, 1, 0): "oak_door",
             (2, 0, 0): "red_bed", (2, 0, 1): "red_bed"}
    assert items_needed(cells) == {"oak_door": 1, "red_bed": 1}


def test_template_costs_what_mindcraft_lists():
    tpl = json.loads((TEMPLATES / "small_wood_house.json").read_text())
    args = from_template(tpl, 10, 64, 10, 0, {"spruce_log": 5})
    assert args["origin"]["y"] == 63                   # offset -1: the floor sits in the ground
    bp = expand(args)
    assert bp.items == {"spruce_planks": 55, "spruce_log": 8, "torch": 4, "white_bed": 1,
                        "spruce_door": 1, "chest": 1}


def test_generic_names_follow_the_inventory():
    assert resolve_generic("planks", {"dark_oak_log": 3, "oak_planks": 1}) == "dark_oak_planks"
    assert resolve_generic("planks", {}, nearest_log="dark_oak_log") == "dark_oak_planks"
    assert resolve_generic("planks", {}) == "oak_planks"
    assert resolve_generic("bed", {"red_wool": 3}) == "red_bed"
    assert resolve_generic("cobblestone", {}) == "cobblestone"


def test_shortfall_counts_any_wood_for_generic_planks():
    assert shortfall({"planks": 10, "cobblestone": 4}, {"birch_planks": 6, "oak_planks": 1}) == {
        "planks": 3, "cobblestone": 4}


def test_what_is_already_there_counts():
    assert satisfied("dirt", "grass_block")
    assert satisfied("torch", "minecraft:wall_torch")
    assert satisfied("planks", "cherry_planks")
    assert not satisfied("cobblestone", "stone")
    assert satisfied("air", "cave_air")


@pytest.mark.skipif(not MOD_VECTORS.is_dir(), reason="no beacraft checkout next to this one")
def test_the_mod_tests_against_the_same_vectors():
    mine = {p.name: p.read_bytes() for p in VECTORS}
    theirs = {p.name: p.read_bytes() for p in sorted(MOD_VECTORS.glob("*.json"))}
    assert sorted(theirs) == sorted(mine), "copy tests/fixtures/minecraft_blueprints/ into beacraft again"
    for name, data in mine.items():
        assert theirs[name] == data, f"{name} differs in beacraft"


def test_null_optional_arguments_are_absent():
    bp = expand({"origin": {"x": 0, "y": 0, "z": 0}, "rotation": None, "palette": None, "layers": None,
                 "ops": [{"op": "set", "at": [0, 0, 0], "block": "stone"}]})
    assert bp.cells == {(0, 0, 0): "stone"}


def test_block_states_turn_with_the_build():
    args = {"origin": {"x": 0, "y": 0, "z": 0}, "rotation": 90,
            "palette": {"D": "oak_door[facing=south]", "L": "oak_log[axis=x]"}, "layers": [["DL"]]}
    bp = expand(args)
    assert bp.cells == {(0, 0, 0): "oak_door[facing=west]", (0, 0, 1): "oak_log[axis=z]"}
    assert bp.items == {"oak_door": 1, "oak_log": 1}
    assert satisfied("oak_door[facing=west]", "oak_door")


def test_bad_block_state_is_named():
    with pytest.raises(BlueprintError, match="bad block state"):
        expand({"origin": {"x": 0, "y": 0, "z": 0}, "palette": {"D": "oak_door[facing]"}, "layers": [["D"]]})
