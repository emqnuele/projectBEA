"""The building tools the brain works out before the mod sees anything."""

import asyncio
import json

import pytest

from src.core.skills.minecraft.blueprint import expand
from src.core.skills.minecraft.building import door_facing, load_templates
from src.core.skills.minecraft.notebook import Notebook
from src.core.skills.minecraft.tools import build_minecraft_tools


class FakeClient:
    """Records what reaches the mod; carries whatever inventory the test gives it."""

    def __init__(self, items=None):
        slots = [{"item": f"minecraft:{name}", "count": n} for name, n in (items or {}).items()]
        self.latest_state = {"inventory": {"hotbar": slots, "main": []}}
        self.sent = []

    async def execute(self, action, params, timeout=None):
        self.sent.append((action, params, timeout))
        return "SUCCESS: built it."


def run(coro):
    return asyncio.run(coro) if asyncio.iscoroutine(coro) else coro


def tools(items=None, build_scripts=True):
    client = FakeClient(items)
    return build_minecraft_tools(client, Notebook(), build_scripts=build_scripts), client


def call(registry, tool, **args):
    return run(registry.get(tool).handler(**args))


def test_build_scripts_are_only_there_when_the_owner_allows_them():
    on, _ = tools()
    off, _ = tools(build_scripts=False)
    assert on.get("build_script") is not None
    assert off.get("build_script") is None
    # templates and ops stay either way
    for name in ("build", "plan_build", "list_templates", "build_template"):
        assert off.get(name) is not None, name


def test_plan_build_costs_against_what_she_carries():
    registry, client = tools({"cobblestone": 10})
    text = call(registry, "plan_build", origin={"x": 0, "y": 64, "z": 0},
                ops=[{"op": "fill", "from": [0, 0, 0], "to": [4, 2, 0], "block": "cobblestone"}])
    assert text == "15 cells; it takes 15 cobblestone; you are short of 5 cobblestone."
    assert client.sent == []


def test_plan_build_names_a_mistake():
    registry, _ = tools()
    text = call(registry, "plan_build", origin={"x": 0, "y": 0, "z": 0}, layers=[["#X"]],
                palette={"#": "stone"})
    assert text.startswith("ERROR: ") and "'X' is not in the palette" in text


def test_the_three_templates_are_listed_with_their_door_side():
    registry, _ = tools()
    text = call(registry, "list_templates")
    lines = text.splitlines()
    assert [line.split(":")[0] for line in lines] == ["dirt_shelter", "small_stone_house", "small_wood_house"]
    assert all("door on the south side" in line for line in lines)
    assert "small_wood_house: 5 wide (x) by 7 deep (z) by 4 high, its floor 1 below ground" in text


def test_every_template_says_where_it_came_from():
    for name, template in load_templates().items():
        assert template["_source"].startswith("mindcraft-bots/mindcraft@5f3acc87"), name
        assert "MIT" in template["_source"]


def test_a_door_placed_from_outside_faces_into_the_house():
    templates = load_templates()
    assert door_facing(templates["small_wood_house"]) == "north"
    assert door_facing(templates["dirt_shelter"]) == "north"


def test_build_template_sends_one_build_in_her_wood():
    registry, client = tools({"spruce_log": 5})
    answer = call(registry, "build_template", name="small_wood_house", x=10, y=64, z=10)
    assert answer == "SUCCESS: built it."
    (action, args, timeout), = client.sent
    assert action == "build" and timeout == 900.0
    assert args["origin"] == {"x": 10, "y": 63, "z": 10}
    assert args["clear"] is True
    blocks = set(args["palette"].values())
    assert {"spruce_planks", "spruce_log", "spruce_door[facing=north]", "white_bed", "torch"} <= blocks
    assert expand(args).items == {"spruce_planks": 55, "spruce_log": 8, "torch": 4, "white_bed": 1,
                                  "spruce_door": 1, "chest": 1}


def test_a_rotated_template_turns_its_door_too():
    registry, client = tools()
    call(registry, "build_template", name="small_wood_house", x=0, y=64, z=0, rotation=90, dry_run=True)
    (_, args, _), = client.sent
    assert args["dry_run"] is True
    doors = {b for b in expand(args).cells.values() if "door" in b}
    assert doors == {"oak_door[facing=east]"}


def test_an_unknown_template_is_named():
    registry, client = tools()
    text = call(registry, "build_template", name="castle", x=0, y=0, z=0)
    assert text.startswith("ERROR: no template 'castle'") and "small_wood_house" in text
    assert client.sent == []


TOWER = """
for y in range(6):
    walls(0, y, 0, 4, y, 4, 'cobblestone')
fill(0, 6, 0, 4, 6, 4, 'oak_planks')
set(2, 0, 0, 'air')
set(2, 1, 0, 'air')
"""


def test_a_script_is_previewed_before_anything_is_built():
    registry, client = tools({"cobblestone": 50})
    text = call(registry, "build_script", code=TOWER, x=10, y=64, z=10)
    assert text.startswith("PREVIEW (nothing built yet):\n121 cells in a 5x7x5 box")
    assert "cobblestone x44" in text
    assert client.sent == []


def test_a_confirmed_script_is_an_ordinary_build():
    registry, client = tools()
    call(registry, "build_script", code=TOWER, x=10, y=64, z=10, confirm=True)
    (action, args, _), = client.sent
    assert action == "build"
    assert len(expand(args).cells) == 121


def test_a_broken_script_comes_back_with_its_line():
    registry, client = tools()
    text = call(registry, "build_script", code="set(0, 0, 0, 'stone')\nx.y = 1", x=0, y=0, z=0, confirm=True)
    assert text.startswith("ERROR: line 2:")
    assert client.sent == []


@pytest.mark.parametrize("path", sorted(__import__("pathlib").Path(__file__).parent.joinpath(
    "fixtures", "minecraft_blueprints").glob("09_*.json")), ids=lambda p: p.stem)
def test_the_template_vector_is_what_build_template_sends(path):
    """09 is the house as build_template would send it: the mod's JUnit expands the same file."""
    vector = json.loads(path.read_text())
    registry, client = tools({"spruce_log": 5})
    call(registry, "build_template", name="small_wood_house", x=0, y=-57, z=0, rotation=90)
    (_, args, _), = client.sent
    assert args == vector["args"]
