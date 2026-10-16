"""The recipes of the Minecraft versions before 26.2, and the extractor that reads their jars."""

import importlib.util
from pathlib import Path

import pytest

from src.core.skills.minecraft.crafting import Recipes

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ["1.21.1", "26.1", "26.2"]


@pytest.fixture(scope="module")
def extractor():
    spec = importlib.util.spec_from_file_location("mc_recipes", ROOT / "tools" / "mc_recipes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_an_ingredient_reads_the_same_in_both_formats(extractor):
    assert extractor.option_key("minecraft:stick") == extractor.option_key({"item": "minecraft:stick"}) == "stick"
    assert extractor.option_key("#minecraft:planks") == extractor.option_key({"tag": "minecraft:planks"}) == "#planks"
    assert extractor.option_key(["minecraft:coal", "minecraft:charcoal"]) == "charcoal|coal"
    assert extractor.option_key([{"item": "minecraft:coal"}, {"item": "minecraft:charcoal"}]) == "charcoal|coal"


def test_a_1_21_shaped_recipe_converts(extractor):
    recipe = {
        "type": "minecraft:crafting_shaped",
        "key": {"#": {"item": "minecraft:stick"}, "X": {"tag": "minecraft:stone_tool_materials"}},
        "pattern": ["XXX", " # ", " # "],
        "result": {"count": 1, "id": "minecraft:stone_pickaxe"},
    }
    assert extractor.convert(recipe) == {
        "type": "crafting_shaped", "grid": "3x3", "count": 1,
        "ingredients": {"#stone_tool_materials": 3, "stick": 2},
    }


def test_a_1_21_smelting_recipe_converts(extractor):
    recipe = {
        "type": "minecraft:smelting",
        "ingredient": {"item": "minecraft:raw_iron"},
        "result": {"id": "minecraft:iron_ingot"},
    }
    assert extractor.convert(recipe) == {
        "type": "smelting", "grid": "furnace", "count": 1, "ingredients": {"raw_iron": 1},
    }


def test_each_game_gets_its_own_recipes():
    assert Recipes.supported() == VERSIONS
    for version in VERSIONS:
        assert Recipes.load(version).version == version


def test_a_tool_is_only_craftable_where_the_game_has_it():
    assert "copper_pickaxe" not in Recipes.load("1.21.1").recipes
    assert "copper_pickaxe" in Recipes.load("26.2").recipes


def test_1_21_1_plans_a_stone_pickaxe_from_its_own_tag():
    recipes = Recipes.load("1.21.1")
    assert recipes.recipes["stone_pickaxe"][0]["ingredients"] == {"#stone_tool_materials": 3, "stick": 2}
    plan = recipes.plan("stone_pickaxe", 1, {"oak_log": 2, "cobblestone": 3})
    assert plan.missing == {}
    assert [s.item for s in plan.steps] == ["oak_planks", "stick", "stone_pickaxe"]
    assert plan.needs_table


def test_1_21_1_shapes_decide_the_grid():
    recipes = Recipes.load("1.21.1")
    assert recipes.recipes["oak_slab"][0]["grid"] == "3x3"
    assert recipes.recipes["crafting_table"][0]["grid"] == "2x2"
    assert "oak_log" in recipes.options("#logs")


@pytest.mark.parametrize("version", ["1.21.1", "26.1"])
def test_every_item_plans_in_the_older_versions(version):
    recipes = Recipes.load(version)
    for item in recipes.recipes:
        recipes.plan(item, 1, {})
