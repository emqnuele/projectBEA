from typing import Any, Dict, Tuple

from src.core.agent.tools import ToolRegistry
from src.core.skills.minecraft.building import register_building_tools
from src.core.skills.minecraft.client import MinecraftClient
from src.core.skills.minecraft.notebook import Notebook

_NOTEBOOK_DESC = (
    "Rewrite your private notebook — your working memory and plan. It is NOT spoken; "
    "it persists across turns so you don't forget what you're doing. ALWAYS pass the FULL "
    "updated notebook (it overwrites the old one). Use it to: state your current goal; list "
    "the items/blocks you need; and crucially work out the CRAFTING DEPENDENCY CHAIN from what "
    "you have right now (e.g. wooden_pickaxe needs 3 planks + 2 sticks; sticks need 2 planks; "
    "planks need 1 log -> so check your inventory and figure out how many logs to gather). "
    "Keep a checklist with [ ] / [x] and update it as you progress, fail, or find new resources."
)

# answered in a moment: they read, speak or stop, and never walk anywhere
_QUICK = {"request_screenshot", "check_death_log", "stop_moving", "chat", "look_at",
          "look_at_player"}

# seconds the brain waits for an answer. Each is longer than the mod's own
# budget for the action, so the mod always gives up first and says why; the
# other way round, the brain moved on while the mod kept going, and its late
# answer landed on whatever was asked next
ACTION_TIMEOUTS: Dict[str, float] = {
    "find_block": 240.0, "build": 900.0, "move_to": 120.0, "smelt_item": 180.0,
    "mine_block": 70.0, "goto_player": 100.0, "give_item": 100.0,
}
DEFAULT_TIMEOUT = 60.0

# tool name -> (mod action, argument renames). Looking at a person is the same
# mod skill as looking at a coordinate, told who to look at instead of where.
_ALIASES = {
    "look_at_player": ("look_at", {"name": "player"}),
}

_PILLARING = {"type": "boolean",
              "description": "May tower straight up on placed blocks to get there."}
_BRIDGING = {"type": "boolean",
             "description": "May bridge out over a gap to get there."}

# name -> (description, json-schema parameters)
_TOOLS: Dict[str, Tuple[str, Dict[str, Any]]] = {
    "mine_block": (
        "Walk into reach of a block and break it, with the rest of its tree or ore vein, then "
        "pick up the drops. The answer says what was mined, what was picked up and what was "
        "left out of reach; FAILURE_WRONG_TOOL names the tool the block needs.", {
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"}},
        "required": ["x", "y", "z"],
    }),
    "attack_entity": ("Attack something: a player by name, or the nearest mob of a type.", {
        "type": "object",
        "properties": {"target": {
            "type": "string",
            "description": "A player's name, or a mob type like 'zombie' — the nearest one wins.",
        }},
        "required": ["target"],
    }),
    "move_to": ("Move to specific coordinates.", {
        "type": "object",
        "properties": {
            "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
            "allowPillaring": _PILLARING, "allowBridging": _BRIDGING,
        },
        "required": ["x", "y", "z"],
    }),
    "stop_moving": ("Stop all movement immediately.", {"type": "object", "properties": {}}),
    "request_screenshot": ("Request a visual screenshot of the current view.", {"type": "object", "properties": {}}),
    "look_at": ("Look at specific coordinates.", {
        "type": "object",
        "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["x", "y", "z"],
    }),
    "place_block": (
        "Place one block at exact coordinates: she walks into reach, takes it from anywhere in "
        "her inventory and places it against a solid neighbour, then checks it is there. A "
        "state like oak_door[facing=south] or oak_log[axis=x] sets how it sits. Fails with "
        "FAILURE_OCCUPIED (something is in the cell; mine it, or pass replace), "
        "FAILURE_NO_SUPPORT (nothing to place it against), FAILURE_NO_ITEM, "
        "FAILURE_OUT_OF_REACH, FAILURE_BODY_IN_THE_WAY or FAILURE_NOT_PLACED.", {
        "type": "object",
        "properties": {
            "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
            "block": {"type": "string",
                      "description": "e.g. cobblestone, oak_stairs[facing=east,half=top]; "
                                     "omit for the block in your hand"},
            "facing": {"type": "string", "enum": ["north", "south", "east", "west", "up", "down"],
                       "description": "Shorthand for [facing=...] in the block name."},
            "replace": {"type": "boolean",
                        "description": "Break whatever is in the cell first. Default false."},
        },
        "required": ["x", "y", "z"],
    }),
    "build": (
        "Build a whole structure in one action: she clears the cells that must be empty, "
        "places the rest bottom-up from what already holds them, walking as she needs, and "
        "answers cell by cell with what is still wrong and what was missing. Describe it as "
        "`layers` + `palette` (bottom layer first; each layer is a list of rows along +z, each "
        "row a string of palette characters along +x; a space leaves the cell as it is; a "
        "palette entry 'air' means empty it) and/or `ops`, relative to `origin`. `rotation` "
        "turns it clockwise seen from above. `dry_run` only reports what is already right and "
        "what you are missing. At most 2000 cells.", {
        "type": "object",
        "properties": {
            "origin": {"type": "object", "description": "Where relative (0, 0, 0) goes.",
                       "properties": {"x": {"type": "integer"}, "y": {"type": "integer"},
                                      "z": {"type": "integer"}},
                       "required": ["x", "y", "z"]},
            "rotation": {"type": "integer", "enum": [0, 90, 180, 270]},
            "palette": {"type": "object", "additionalProperties": {"type": "string"},
                        "description": 'One character -> block, e.g. {"#": "cobblestone", '
                                       '"D": "oak_door[facing=north]", ".": "air"}.'},
            "layers": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
            "ops": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": ["fill", "walls", "set", "roof"],
                           "description": "fill a box (hollow: only its shell), walls = the "
                                          "sides of a box, set one cell, roof = a fill"},
                    "from": {"type": "array", "items": {"type": "integer"}},
                    "to": {"type": "array", "items": {"type": "integer"}},
                    "at": {"type": "array", "items": {"type": "integer"}},
                    "block": {"type": "string"},
                    "hollow": {"type": "boolean"},
                },
                "required": ["op", "block"],
            }},
            "clear": {"type": "boolean",
                      "description": "Left out: only cells meant to be 'air' are emptied. "
                                     "true: also break blocks in the way of a different "
                                     "block. false: break nothing."},
            "dry_run": {"type": "boolean"},
        },
        "required": ["origin"],
    }),
    "select_slot": ("Select a hotbar slot (0-8).", {
        "type": "object",
        "properties": {"slot": {"type": "integer", "minimum": 0, "maximum": 8}},
        "required": ["slot"],
    }),
    "find_block": (
        "Collect `count` items of a block kind: find the nearest ones (open ones first), mine "
        "them and pick up the drops, until you carry that many more. FAILURE_NOT_ENOUGH says "
        "how many you got when there is no more nearby; FAILURE_NONE_REACHABLE and "
        "FAILURE_NONE_FOUND mean look somewhere else.",
        {
            "type": "object",
            "properties": {
                "block": {"type": "string"},
                "radius": {"type": "integer", "default": 48, "maximum": 100,
                           "description": "How far to search."},
                "count": {"type": "integer", "description": "How many to gather; defaults to 7."},
            },
            "required": ["block"],
        }),
    "pickup_items": (
        "Walk over the items lying on the ground around you, nearest first, and pick them up. "
        "The answer lists what ended up in your inventory.",
        {
            "type": "object",
            "properties": {"radius": {"type": "number", "description": "How far to look; defaults to 6."}},
        }),
    "pillar_up": ("Pillar up a certain height.", {
        "type": "object",
        "properties": {"height": {"type": "integer"}, "block": {"type": "string"}},
        "required": ["height"],
    }),
    "mine_down": ("Mine downwards a certain depth.", {
        "type": "object",
        "properties": {"depth": {"type": "integer"}},
        "required": ["depth"],
    }),
    "bridge": ("Build a bridge in a direction.", {
        "type": "object",
        "properties": {
            "direction": {"type": "string", "enum": ["NORTH", "SOUTH", "EAST", "WEST"]},
            "count": {"type": "integer"},
        },
        "required": ["direction", "count"],
    }),
    "craft_item": ("Craft an item using a nearby crafting table or inventory.", {
        "type": "object",
        "properties": {
            "item": {"type": "string"},
            "quantity": {"type": "integer", "minimum": 1,
                         "description": "How many to make; defaults to 1."},
        },
        "required": ["item"],
    }),
    "use_block": ("Interact (right click) with a block at coordinates.", {
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"}},
        "required": ["x", "y", "z"],
    }),
    "smelt_item": ("Smelt an item in a furnace.", {
        "type": "object",
        "properties": {"input_item": {"type": "string"}, "fuel_item": {"type": "string"}},
        "required": ["input_item", "fuel_item"],
    }),
    "store_item": ("Store items in a container.", {
        "type": "object",
        "properties": {"item": {"type": "string"}},
        "required": ["item"],
    }),
    "retrieve_item": ("Retrieve items from a container.", {
        "type": "object",
        "properties": {"item": {"type": "string"}},
        "required": ["item"],
    }),
    "equip_item": (
        "Put something on: a tool in your hand, armour on your body, a shield in your "
        "off hand. Armour and a shield are what keep you alive — wear them.",
        {
            "type": "object",
            "properties": {
                "item": {"type": "string"},
                "destination": {
                    "type": "string", "enum": ["mainhand", "armor", "offhand"],
                    "description": "Where it goes; defaults to your main hand.",
                },
            },
            "required": ["item"],
        }),
    "discard_item": ("Discard (throw away) items. Omit `count` to drop every one you have.", {
        "type": "object",
        "properties": {
            "item": {"type": "string"},
            "count": {"type": "integer", "minimum": 1,
                      "description": "How many to drop; omit for all of them."},
        },
        "required": ["item"],
    }),
    "eat_food": ("Eat the best available food.", {"type": "object", "properties": {}}),
    "check_death_log": ("Check the last death details.", {"type": "object", "properties": {}}),
    # --- playing WITH people, not just near them ---
    "goto_player": (
        "Walk over to a specific player and stop next to them. They move, so she "
        "re-paths as they go.",
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}),
    "follow_player": (
        "Stay with a player, keeping a few blocks behind them, until you stop. "
        "Stops on its own if you lose them.",
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}),
    "look_at_player": (
        "Turn and look at a player. Staring at someone is communication — use it "
        "when you want them to know you noticed.",
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}),
    "give_item": (
        "Take something to a player: walk over and drop it at their feet (vanilla "
        "has no direct give). Omit `count` to hand over everything you have of it.",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "item": {"type": "string"},
                "count": {"type": "integer", "description": "how many; omit for all"},
            },
            "required": ["name", "item"],
        }),
    "chat": (
        "TYPE a message in the game chat. The other players read this — it is a "
        "different audience from your voice. Your voice (`speak`) is heard by your "
        "stream; this is what the people in the game see. You can use both in the "
        "same turn, and often should: comment out loud for your audience, and "
        "answer in chat for whoever is standing there.",
        {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        }),
}


def build_minecraft_tools(client: MinecraftClient, notebook: Notebook,
                          surface: str = "game:mc", build_scripts: bool = True) -> ToolRegistry:
    """Builds a registry whose handlers drive the mod and return observations.

    Also registers the local `update_notebook` tool, which mutates the agent's
    private working memory instead of talking to the mod, and the building
    tools worked out in the brain (`build_script` only when `build_scripts`).
    """
    registry = ToolRegistry()

    def make_handler(tool_name: str):
        action, renames = _ALIASES.get(tool_name, (tool_name, {}))
        timeout = ACTION_TIMEOUTS.get(action, DEFAULT_TIMEOUT)

        async def handler(**kwargs):
            args = {renames.get(k, k): v for k, v in kwargs.items()}
            return await client.execute(action, args, timeout=timeout)
        return handler

    for name, (description, parameters) in _TOOLS.items():
        registry.add(name, description, parameters, make_handler(name),
                     long_running=name not in _QUICK, surface=surface)

    registry.add(
        "update_notebook",
        _NOTEBOOK_DESC,
        {
            "type": "object",
            "properties": {"notes": {"type": "string", "description": "The full new notebook content."}},
            "required": ["notes"],
        },
        lambda notes="": notebook.update(notes),
    )
    register_building_tools(registry, client, surface, build_scripts)

    return registry
