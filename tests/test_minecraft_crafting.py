"""The crafting planner, against the real 26.2 recipe data."""

import pytest

from src.core.skills.minecraft.crafting import Recipes, describe


@pytest.fixture(scope="module")
def recipes():
    return Recipes.load("26.2")


def test_extracted_data_matches_the_jar(recipes):
    assert len(recipes.recipes) == 961
    assert len(recipes.tags) == 224
    assert recipes.recipes["oak_slab"][0]["grid"] == "3x3"      # "###" is 3 wide
    assert recipes.recipes["crafting_table"][0]["grid"] == "2x2"
    assert recipes.recipes["torch"][0]["ingredients"] == {"charcoal|coal": 1, "stick": 1}
    assert "oak_log" in recipes.options("#logs")                 # tag of tags, flattened


def test_one_log_short_for_a_wooden_pickaxe(recipes):
    plan = recipes.plan("wooden_pickaxe", 1, {"oak_log": 1})
    assert plan.missing == {"oak_log": 1}
    assert [s.item for s in plan.steps] == ["oak_planks", "stick", "wooden_pickaxe"]
    assert plan.steps[0].times == 2          # merged: one step, two crafts
    assert plan.needs_table


def test_wood_follows_what_she_carries(recipes):
    plan = recipes.plan("wooden_pickaxe", 1, {"birch_log": 2})
    assert plan.missing == {}
    assert plan.steps[0].item == "birch_planks"


def test_mixed_planks_fill_one_tag_slot(recipes):
    plan = recipes.plan("crafting_table", 1, {"oak_planks": 2, "birch_planks": 2})
    assert plan.missing == {}
    assert plan.steps[0].uses == {"oak_planks": 2, "birch_planks": 2}
    assert not plan.needs_table


def test_iron_comes_from_raw_iron_not_from_unpacking_a_block(recipes):
    plan = recipes.plan("iron_ingot", 5, {})
    assert plan.missing == {"raw_iron": 5, "coal": 1}
    assert plan.needs_furnace


def test_smelting_burns_what_she_has(recipes):
    plan = recipes.plan("iron_ingot", 3, {"raw_iron": 3, "oak_planks": 2})
    assert plan.missing == {}
    assert plan.fuel == {"oak_planks": 2}      # 1.5 smelts each


def test_one_smelt_burns_a_plank_not_a_coal(recipes):
    # the same pick the mod makes: the fuel slot holds one kind, and waste is burn nobody uses
    plan = recipes.plan("iron_ingot", 1, {"raw_iron": 1, "coal": 3, "oak_planks": 4})
    assert plan.fuel == {"oak_planks": 1}
    plan = recipes.plan("iron_ingot", 8, {"raw_iron": 8, "coal": 3, "oak_planks": 4})
    assert plan.fuel == {"coal": 1}


def test_fuel_that_runs_short_leaves_coal_missing(recipes):
    plan = recipes.plan("iron_ingot", 5, {"raw_iron": 5, "oak_planks": 2})
    assert plan.fuel == {"oak_planks": 2}          # three smelts' worth
    assert plan.missing == {"coal": 1}


def test_the_block_is_used_when_she_carries_it(recipes):
    plan = recipes.plan("iron_ingot", 5, {"iron_block": 1})
    assert plan.missing == {}
    assert plan.leftovers == {"iron_ingot": 4}


def test_coal_is_mined_not_smelted(recipes):
    plan = recipes.plan("torch", 8, {"oak_log": 1, "coal": 1})
    assert plan.missing == {"coal": 1}


def test_nether_wood_is_not_fuel(recipes):
    assert "crimson_planks" not in recipes.fuel
    assert recipes.fuel["oak_planks"] == 1.5 and recipes.fuel["coal"] == 8


def test_ingots_short_for_a_block_are_smelted_not_unpacked(recipes):
    plan = recipes.plan("iron_block", 2, {"iron_ingot": 9})
    assert [s.item for s in plan.steps] == ["iron_ingot", "iron_block"]
    assert plan.missing == {"raw_iron": 9, "coal": 2}


def test_the_game_version_picks_the_data(tmp_path):
    for v in ("26.1", "26.2", "26.10"):
        (tmp_path / f"{v}.json").write_text('{"version": "%s", "recipes": {}, "tags": {}}' % v)
    assert Recipes.load("26.2", tmp_path).version == "26.2"
    assert Recipes.load("26.3", tmp_path).version == "26.2"      # newest older one
    assert Recipes.load("26.11", tmp_path).version == "26.10"    # 10 > 2, not text order
    assert Recipes.supported(tmp_path) == ["26.1", "26.2", "26.10"]
    with pytest.raises(FileNotFoundError):
        Recipes.load("25.9", tmp_path)


def test_every_item_plans(recipes):
    for item in recipes.recipes:
        recipes.plan(item, 1, {})


def test_describe_reads_like_a_plan(recipes):
    inv = {"cobblestone": 3, "oak_planks": 1}
    text = describe(recipes.plan("stone_pickaxe", 1, inv), inv)
    assert text.splitlines()[0] == "missing: 1 oak_log"
    assert "needs a crafting table" in text


# -- the tools the body sees ----------------------------------------------------

class FakeClient:
    """Answers every action with `answer`; carries whatever inventory the test gives it."""

    def __init__(self, items=None, answer="SUCCESS: crafted it.", mc_version="26.2"):
        slots = [{"item": f"minecraft:{name}", "count": n} for name, n in (items or {}).items()]
        self.latest_state = {"inventory": {"hotbar": slots, "main": []}}
        self.mc_version = mc_version
        self.answer = answer
        self.sent = []

    async def execute(self, action, params, timeout=None):
        self.sent.append((action, params, timeout))
        return self.answer


def _tools(**kw):
    import asyncio

    from src.core.skills.minecraft.notebook import Notebook
    from src.core.skills.minecraft.tools import build_minecraft_tools

    client = FakeClient(**kw)
    registry = build_minecraft_tools(client, Notebook())

    def call(tool, **args):
        out = registry.get(tool).handler(**args)
        return asyncio.run(out) if asyncio.iscoroutine(out) else out
    return call, client


def test_crafting_plan_answers_from_what_she_carries_without_the_mod():
    call, client = _tools(items={"cobblestone": 3, "oak_planks": 1})
    text = call("crafting_plan", item="stone_pickaxe")
    assert text.splitlines()[0] == "missing: 1 oak_log"
    assert client.sent == []


def test_a_failed_craft_comes_with_the_plan():
    call, client = _tools(items={"oak_planks": 1, "stick": 2},
                          answer="FAILURE_MISSING_INGREDIENTS: 1 wooden_pickaxe takes 3 planks and 2 stick")
    text = call("craft_item", item="wooden_pickaxe", count=1)
    assert text.startswith("FAILURE_MISSING_INGREDIENTS")
    assert "\ncrafting_plan:\nmissing: 1 oak_log" in text
    assert client.sent[0][:2] == ("craft_item", {"item": "wooden_pickaxe", "count": 1})


def test_a_craft_that_worked_is_left_alone():
    call, _ = _tools(items={"oak_log": 1})
    assert call("craft_item", item="oak_planks", count=4) == "SUCCESS: crafted it."


def test_names_that_nothing_makes():
    call, _ = _tools()
    assert call("crafting_plan", item="oak_log") == "nothing crafts or smelts oak_log: it is mined, gathered or dropped."
    assert "did you mean" in call("crafting_plan", item="woden_pickaxe")
    assert call("crafting_plan", item="sticks").startswith("missing: 1 oak_log")


def test_a_newer_game_says_whose_recipes_it_used():
    call, _ = _tools(mc_version="26.3")
    assert call("crafting_plan", item="stick").startswith("(recipes from Minecraft 26.2; the game is 26.3)\n")
