"""What the mod sends has to survive the trip to the model.

The packets here are shaped the way GameStateGatherer builds them. The rule the
whole file is about: every argument a tool requires must be obtainable from the
rendered state. A model told to mine a block, and never shown a coordinate, can
only invent one.
"""

import re

import pytest

from src.core.skills.minecraft.state import render_state
from src.core.skills.minecraft.tools import _TOOLS

COORD = re.compile(r"\(-?\d+, ?-?\d+, ?-?\d+\)")


def packet(**overrides):
    """A game-state packet in the mod's own shape."""
    state = {
        "player": {"health": 14.0, "food": 9, "is_alive": True,
                   "position": {"x": 112.5, "y": 31.0, "z": -48.2}},
        "inventory": {
            "hand_main": {"item": "minecraft:stone_pickaxe", "count": 1},
            "hotbar": [{"item": "minecraft:cobblestone", "count": 42},
                       {"item": "minecraft:torch", "count": 7}],
            "main": [{"item": "minecraft:oak_log", "count": 5},
                     {"item": "minecraft:raw_iron", "count": 3}],
            "context": {"craftable_2x2": [{"item": "minecraft:stick"}]},
        },
        "lidar": {
            "radius": 4,
            "blocks": [
                {"x": 114, "y": 31, "z": -47, "name": "minecraft:iron_ore", "distance": 2.2},
                {"x": 110, "y": 29, "z": -50, "name": "minecraft:lava", "distance": 4.1},
                {"x": 113, "y": 32, "z": -48, "name": "minecraft:torch", "distance": 1.4},
            ],
            "surrounded_by": {"stone": 512, "dirt": 48, "gravel": 12},
            "standing_on": "stone",
            "above_head": "air",
        },
        "entities": [
            {"id": 77, "type": "minecraft:zombie", "name": "Zombie", "distance": 6.0,
             "pos": {"x": 118.0, "y": 31.0, "z": -44.0}},
            {"id": 12, "type": "minecraft:player", "name": "Notch", "is_player": True,
             "distance": 12.0, "pos": {"x": 100.0, "y": 31.0, "z": -40.0}},
        ],
        "gui_state": {"is_open": False},
    }
    state.update(overrides)
    return state


def test_a_notable_block_arrives_with_the_coordinates_you_could_mine_it_at():
    rendered = render_state(packet())
    assert "iron_ore (114, 31, -47)" in rendered
    assert "2.2m" in rendered


def test_the_ground_and_the_ceiling_reach_her():
    rendered = render_state(packet())
    assert "standing on stone" in rendered
    # air over her head is headroom to jump, and it is the mod that knows
    assert "air" in rendered


def test_the_census_is_the_one_the_mod_counted():
    # `blocks` holds only notable blocks, so bulk can never be derived from it
    rendered = render_state(packet())
    assert "stone×512" in rendered
    assert "dirt×48" in rendered


def test_the_nearest_thing_is_named_first():
    rendered = render_state(packet())
    nearby = next(line for line in rendered.splitlines() if "iron_ore" in line)
    assert nearby.index("torch") < nearby.index("iron_ore") < nearby.index("lava")


def test_a_crowd_of_one_kind_cannot_hide_the_ore():
    torches = [{"x": 100 + i, "y": 31, "z": -48, "name": "minecraft:torch", "distance": 0.5 + i * 0.1}
               for i in range(30)]
    ore = {"x": 114, "y": 31, "z": -47, "name": "minecraft:diamond_ore", "distance": 4.0}
    state = packet()
    state["lidar"]["blocks"] = torches + [ore]
    assert "diamond_ore (114, 31, -47)" in render_state(state)


def test_nothing_from_an_empty_packet():
    assert render_state({}) == ""
    assert render_state(None) == ""


def test_a_packet_with_no_lidar_still_renders():
    state = packet()
    del state["lidar"]
    assert "health 14/20" in render_state(state)


@pytest.mark.parametrize("tool", sorted(
    name for name, (_d, schema) in _TOOLS.items()
    if {"x", "y", "z"} <= set(schema.get("required") or ())))
def test_every_tool_that_needs_a_coordinate_can_read_one_off_the_state(tool):
    assert COORD.search(render_state(packet())), (
        f"{tool} requires x/y/z and the state shows no coordinate to use")


def test_the_target_attack_wants_is_a_name_the_state_shows():
    rendered = render_state(packet())
    assert "Zombie" in rendered and "Notch" in rendered


# --- resources and the world -------------------------------------------------


def _with(**parts):
    state = {"player": {"health": 20, "food": 20, "position": {"x": 0, "y": -57, "z": 0}}}
    state.update(parts)
    return state


def test_a_tree_seven_blocks_away_is_in_sight_with_where_to_go():
    """The reported gap: the lidar stopped at four blocks, and a tree at seven did not exist."""
    text = render_state(_with(
        resources={"oak_log": {"count": 5, "nearest": {"x": 7, "y": -57, "z": 0, "distance": 7.0},
                               "nearest_exposed": {"x": 7, "y": -57, "z": 0, "distance": 7.0}}},
        resources_scan={"radius": 20, "ms": 4.1}))
    assert "- resources in sight (within 20 blocks): oak_log×5 (7, -57, 0) 7.0m" in text


def test_ores_come_first_and_a_buried_one_says_so():
    text = render_state(_with(resources={
        "stone": {"count": 900, "nearest": {"x": 0, "y": -58, "z": 0, "distance": 1.0},
                  "nearest_exposed": {"x": 0, "y": -58, "z": 0, "distance": 1.0}},
        "iron_ore": {"count": 1, "nearest": {"x": 12, "y": -60, "z": -3, "distance": 12.7}},
    }))
    line = next(x for x in text.splitlines() if x.startswith("- resources"))
    assert line == "- resources in sight: iron_ore×1 (12, -60, -3) 12.7m buried, stone×900 (0, -58, 0) 1.0m"


def test_only_eight_kinds_are_named():
    many = {f"k{i}": {"count": 1, "nearest": {"x": i, "y": 0, "z": 0, "distance": float(i)}} for i in range(12)}
    line = next(x for x in render_state(_with(resources=many)).splitlines() if x.startswith("- resources"))
    assert line.count("×") == 8 and "k0×1" in line and "k11" not in line


def test_night_and_the_dark_reach_her():
    assert "- time: night (hostiles spawn in the dark), raining, no light where you stand" in render_state(
        _with(world={"is_night": True, "raining": True, "block_light": 0, "dimension": "minecraft:overworld"}))
    assert "- time: day" in render_state(_with(world={"is_night": False, "block_light": 0}))
    assert "in the the_nether" in render_state(_with(world={"dimension": "minecraft:the_nether"}))


def test_the_real_packet_shows_the_tree_and_the_ore_the_old_one_hid():
    """Recorded from the mod: the setup that used to render only the crafting table."""
    import json
    from pathlib import Path
    real = json.loads((Path(__file__).parent / "fixtures/minecraft_packets/game_state.json").read_text())
    text = render_state(real)
    assert "oak_log×5 (7, -57, 0) 7.0m" in text
    assert "iron_ore×1 (12, -57, -3) 12.4m" in text
    assert "- time: day" in text
