import asyncio
from typing import Any, Dict, Optional, Tuple

from src.core.agent.tools import ToolRegistry
from src.core.skills.minecraft.building import register_building_tools
from src.core.skills.minecraft.client import MinecraftClient
from src.core.skills.minecraft.notebook import Notebook
from src.core.skills.minecraft.places import Places, server_of
from src.core.skills.minecraft.recipebook import PLAN_DESC, RecipeBook

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
          "look_at_player", "scan"}

# seconds the brain waits for an answer. Each is longer than the mod's own
# budget for the action, so the mod always gives up first and says why; the
# other way round, the brain moved on while the mod kept going, and its late
# answer landed on whatever was asked next
ACTION_TIMEOUTS: Dict[str, float] = {
    "find_block": 240.0, "build": 900.0, "move_to": 120.0, "smelt_item": 180.0,
    "mine_block": 70.0, "goto_player": 100.0, "give_item": 100.0, "move_away": 70.0,
    "go_to_surface": 130.0,
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
    "attack_entity": (
        "Fight something until it dies: a player by name, or the nearest mob of a type. She "
        "puts on armour and takes her best weapon. FAILURE_NOT_FOUND when there is none near, "
        "FAILURE_TARGET_TOO_FAR when it got away.", {
        "type": "object",
        "properties": {"target": {
            "type": "string",
            "description": "A player's name, or a mob type like 'zombie' — the nearest one wins.",
        }},
        "required": ["target"],
    }),
    "move_to": (
        "Walk to coordinates. She first looks for a way that breaks nothing (round a wall, "
        "through a door she opens); only when there is none does she dig, and never through "
        "doors, chests, beds, glass or torches. `range` is how close counts as there. The "
        "answer says where she stopped; FAILURE means she could not get there.", {
        "type": "object",
        "properties": {
            "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
            "range": {"type": "number", "minimum": 0, "maximum": 32,
                      "description": "Blocks from the target that count as arrived; defaults to 1.5 "
                                     "(the cell, or one next to it)."},
            "allowPillaring": _PILLARING, "allowBridging": _BRIDGING,
        },
        "required": ["x", "y", "z"],
    }),
    "move_away": (
        "Put `distance` blocks between you and where you stand, in whatever direction is open. "
        "FAILURE_BLOCKED says how far you got.", {
        "type": "object",
        "properties": {"distance": {"type": "number", "minimum": 2, "maximum": 64,
                                    "description": "Defaults to 20."}},
    }),
    "go_to_surface": (
        "Get out from underground to where you can see the sky: walking out if there is a way, "
        "else digging a staircase up, away from lava and water. Slow without a pickaxe. "
        "FAILURE_NO_SURFACE in the Nether.", {"type": "object", "properties": {}}),
    "stop_moving": ("Stop whatever the body is doing, at once; the answer names what was stopped.",
                    {"type": "object", "properties": {}}),
    "look_at": ("Turn the head to look at coordinates, without stopping what the body is doing.", {
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
    "scan": (
        "Where the nearest blocks of a kind are, up to 64 blocks away, without moving and "
        "without stopping what you are doing. The state already lists what is within 20 "
        "blocks; scan is for looking further, or for one kind. Names match like find_block "
        "('log' is any log). FAILURE_NONE_FOUND means there is none that close.",
        {
            "type": "object",
            "properties": {
                "block": {"type": "string"},
                "radius": {"type": "integer", "maximum": 64, "description": "Defaults to 32."},
                "count": {"type": "integer", "maximum": 20, "description": "How many to list; defaults to 5."},
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
    "pillar_up": ("Jump and place blocks under yourself to rise `height` blocks. FAILURE_NO_BLOCKS "
                  "when you carry nothing to stand on.", {
        "type": "object",
        "properties": {"height": {"type": "integer"}, "block": {"type": "string"}},
        "required": ["height"],
    }),
    "mine_down": ("Dig straight down `depth` blocks, falling as you go. She stops before lava, "
                  "fire, water or a drop deeper than 3 (FAILURE_DANGER says which).", {
        "type": "object",
        "properties": {"depth": {"type": "integer"}},
        "required": ["depth"],
    }),
    "bridge": ("From the edge you stand on, build `count` blocks out over a gap, walking backwards "
               "onto them. FAILURE_NO_EDGE when you are not at an edge facing that way, "
               "FAILURE_NO_BLOCKS when you carry nothing to build with.", {
        "type": "object",
        "properties": {
            "direction": {"type": "string", "enum": ["NORTH", "SOUTH", "EAST", "WEST"]},
            "count": {"type": "integer"},
        },
        "required": ["direction", "count"],
    }),
    "craft_item": (
        "Make `count` items (items, not crafts: count 5 sticks is two crafts, 8 sticks). A "
        "recipe that fits the 2x2 grid is made in your inventory; anything bigger at the nearest "
        "crafting table within 16 blocks, walking there, or at the one you carry, set down and "
        "picked back up. Fails with FAILURE_MISSING_INGREDIENTS (says what you are short of), "
        "FAILURE_NO_TABLE, FAILURE_NO_RECIPE (not unlocked yet) or FAILURE_UNREACHABLE; a "
        "failure comes with the crafting_plan from what you carry.", {
        "type": "object",
        "properties": {
            "item": {"type": "string"},
            "count": {"type": "integer", "minimum": 1,
                      "description": "How many items you want; defaults to one craft."},
        },
        "required": ["item"],
    }),
    "use_block": (
        "Right-click a block (a lever, a button, a door, a bed), walking into reach first. The "
        "answer says what changed. Chests, furnaces and tables have their own tools; a screen "
        "a click opens is closed again. FAILURE_OUT_OF_REACH, FAILURE_NOTHING_THERE.", {
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"}},
        "required": ["x", "y", "z"],
    }),
    "smelt_item": (
        "Smelt `count` of an item (raw_iron, sand, a log...) and wait for it: at the nearest "
        "furnace within 16 blocks, or at the one you carry, set down and picked back up. She "
        "puts in just enough fuel from what you carry (or `fuel`), takes out everything, and "
        "takes back what was not used. About 10 s per item, at most 10 per call. Fails with "
        "FAILURE_NO_FUEL, FAILURE_NO_FURNACE, FAILURE_FURNACE_BUSY (it holds someone else's "
        "smelt), FAILURE_NOT_SMELTABLE or FAILURE_STALLED.", {
        "type": "object",
        "properties": {
            "item": {"type": "string"},
            "count": {"type": "integer", "minimum": 1, "maximum": 10, "description": "Defaults to 1."},
            "fuel": {"type": "string", "description": "What to burn; left out, the least wasteful."},
        },
        "required": ["item"],
    }),
    "store_item": (
        "Put `count` of an item (all of it if left out) into a chest or barrel: the one at x, y, z, "
        "or the nearest within 32 blocks. She walks there, opens it, moves exactly that item and "
        "closes it; the answer says what the chest holds now. Fails with FAILURE_NO_CONTAINER, "
        "FAILURE_CONTAINER_FULL or FAILURE_NO_ITEM.", {
        "type": "object",
        "properties": {
            "item": {"type": "string"},
            "count": {"type": "integer", "minimum": 1},
            "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
        },
        "required": ["item"],
    }),
    "retrieve_item": (
        "Take `count` of an item (all of it if left out) out of a chest or barrel: the one at "
        "x, y, z, or the nearest within 32 blocks. Fails with FAILURE_NOT_IN_CONTAINER, "
        "FAILURE_NOT_ENOUGH (it held fewer), FAILURE_INVENTORY_FULL or FAILURE_NO_CONTAINER.", {
        "type": "object",
        "properties": {
            "item": {"type": "string"},
            "count": {"type": "integer", "minimum": 1},
            "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
        },
        "required": ["item"],
    }),
    "view_container": (
        "Look inside a chest or barrel: the one at x, y, z, or the nearest within 32 blocks. She "
        "walks there and opens it, so it takes the body like any walk.", {
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"}},
    }),
    "equip_item": (
        "Put something on: a tool in your hand, armour on your body, a shield in your "
        "off hand. Armour and a shield are what keep you alive — wear them. "
        "FAILURE_ITEM_NOT_FOUND when you have none.",
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
    "discard_item": ("Throw items on the ground. Omit `count` to drop every one you have. The name "
                     "is exact: 'stone' is stone, never a stone pickaxe. FAILURE_ITEM_NOT_FOUND.", {
        "type": "object",
        "properties": {
            "item": {"type": "string"},
            "count": {"type": "integer", "minimum": 1,
                      "description": "How many to drop; omit for all of them."},
        },
        "required": ["item"],
    }),
    "eat_food": ("Eat the best food you carry. FAILURE_NO_FOOD when there is none.",
                 {"type": "object", "properties": {}}),
    "check_death_log": ("Where, how and when you last died, and what you dropped.",
                        {"type": "object", "properties": {}}),
    # --- playing WITH people, not just near them ---
    "goto_player": (
        "Walk over to a specific player and stop next to them. They move, so she "
        "re-paths as they go. FAILURE_NOT_FOUND, FAILURE_UNREACHABLE.",
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}),
    "follow_player": (
        "Stay with a player, keeping a few blocks behind them, until you stop. "
        "Stops on its own if you lose them (FAILURE_LOST).",
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
                          surface: str = "game:mc", build_scripts: bool = True,
                          places: Optional[Places] = None) -> ToolRegistry:
    """Builds a registry whose handlers drive the mod and return observations.

    Also registers the local `update_notebook` tool, which mutates the agent's
    private working memory instead of talking to the mod, and the building
    tools worked out in the brain (`build_script` only when `build_scripts`),
    and, given a place book, `remember_place` and `go_to_place`.
    """
    registry = ToolRegistry()

    book = RecipeBook(client)

    def make_handler(tool_name: str):
        action, renames = _ALIASES.get(tool_name, (tool_name, {}))
        timeout = ACTION_TIMEOUTS.get(action, DEFAULT_TIMEOUT)

        async def handler(**kwargs):
            args = {renames.get(k, k): v for k, v in kwargs.items()}
            observation = await client.execute(action, args, timeout=timeout)
            if action == "craft_item" and str(observation).startswith("FAILURE"):
                # the mod sees one step; the plan shows the chain from what she carries
                plan = book.plan(str(args.get("item", "")), int(args.get("count") or 1))
                observation = f"{observation}\ncrafting_plan:\n{plan}"
            return observation
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
    registry.add(
        "crafting_plan",
        PLAN_DESC,
        {
            "type": "object",
            "properties": {"item": {"type": "string"},
                           "count": {"type": "integer", "minimum": 1, "description": "Defaults to 1."}},
            "required": ["item"],
        },
        lambda item="", count=1: book.plan(item, count),
        surface=surface,
    )
    register_building_tools(registry, client, surface, build_scripts)
    if places is not None:
        register_place_tools(registry, client, places, surface)

    return registry


def register_place_tools(registry: ToolRegistry, client: MinecraftClient, places: Places,
                         surface: str = "game:mc") -> None:
    """remember_place and go_to_place, over the places of the server she is on."""

    def where() -> Tuple[Optional[Tuple[float, float, float]], str, str]:
        state = client.latest_state or {}
        pos = (state.get("player") or {}).get("position") or {}
        world = state.get("world") or {}
        here = (float(pos["x"]), float(pos["y"]), float(pos["z"])) if {"x", "y", "z"} <= set(pos) else None
        return here, server_of(state), str(world.get("dimension") or "minecraft:overworld")

    async def remember_place(name: str) -> str:
        here, server, dimension = where()
        if here is None:
            return "ERROR: the game has not said where you are yet."
        if not str(name or "").strip():
            return "ERROR: a place needs a name."
        key = places.remember(server, name, *here, dimension=dimension)
        await asyncio.to_thread(places.save)
        p = places.get(server, key) or {}
        return f"remembered {key} at ({p.get('x')}, {p.get('y')}, {p.get('z')})."

    async def go_to_place(name: str, range: float = 0.0) -> str:
        here, server, dimension = where()
        p = places.get(server, name)
        if p is None:
            known = ", ".join(places.names(server)) or "none yet"
            return f"ERROR: you remember no place called {name}; you know: {known}."
        if p.get("dimension", dimension) != dimension:
            return (f"FAILURE_OTHER_DIMENSION: {name} is in {str(p['dimension']).split(':')[-1]}, "
                    f"and you are in {dimension.split(':')[-1]}.")
        args: Dict[str, Any] = {"x": p["x"], "y": p["y"], "z": p["z"]}
        if range:
            args["range"] = range
        return await client.execute("move_to", args, timeout=ACTION_TIMEOUTS["move_to"])

    registry.add("remember_place", (
        "Remember where you stand under a name (home, mine, the village), for this world. "
        "The same name again moves it. Your places are listed with the game state; where "
        "you last died is remembered for you as last_death."), {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }, remember_place, surface=surface)
    registry.add("go_to_place", (
        "Walk to a place you remembered (see remember_place), the way move_to walks."), {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "range": {"type": "number", "minimum": 0, "maximum": 32,
                      "description": "Blocks from it that count as arrived; defaults to 1.5."},
        },
        "required": ["name"],
    }, go_to_place, long_running=True, surface=surface)

