"""What she carries, counted the way the game state is read everywhere else."""


from src.core.skills.minecraft.state import count_items


def carrying(**items):
    """A state packet holding exactly these items, in the mod's shape."""
    return {
        "player": {"health": 20, "food": 20, "position": {"x": 0, "y": 64, "z": 0}},
        "inventory": {
            "hand_main": {"item": "minecraft:air", "count": 0},
            "hotbar": [{"item": f"minecraft:{n}", "count": c} for n, c in items.items()],
            "main": [],
        },
    }


# --- counting what she has ---------------------------------------------------


def test_what_she_carries_is_counted_by_short_name():
    assert count_items(carrying(iron_ingot=5))["iron_ingot"] == 5


def test_the_same_item_in_two_stacks_adds_up():
    state = carrying()
    state["inventory"]["hotbar"] = [{"item": "minecraft:oak_log", "count": 60},
                                    {"item": "minecraft:oak_log", "count": 4}]
    assert count_items(state)["oak_log"] == 64


def test_the_held_item_is_not_counted_twice():
    # hand_main is one of the hotbar slots, not a slot of its own
    state = carrying(stone_pickaxe=1)
    state["inventory"]["hand_main"] = {"item": "minecraft:stone_pickaxe", "count": 1}
    assert count_items(state)["stone_pickaxe"] == 1


def test_armour_she_is_wearing_still_counts_as_having_it():
    state = carrying()
    state["inventory"]["armor"] = [{"item": "minecraft:iron_chestplate", "count": 1}]
    state["inventory"]["hand_off"] = {"item": "minecraft:shield", "count": 1}
    counted = count_items(state)
    assert counted["iron_chestplate"] == 1 and counted["shield"] == 1
