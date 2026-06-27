from typing import Any, Dict, Tuple

from src.core.agent.tools import ToolRegistry
from src.modules.skills.minecraft.mc_client import MinecraftClient
from src.modules.skills.minecraft.notebook import Notebook

_NOTEBOOK_DESC = (
    "Rewrite your private notebook — your working memory and plan. It is NOT spoken; "
    "it persists across turns so you don't forget what you're doing. ALWAYS pass the FULL "
    "updated notebook (it overwrites the old one). Use it to: state your current goal; list "
    "the items/blocks you need; and crucially work out the CRAFTING DEPENDENCY CHAIN from what "
    "you have right now (e.g. wooden_pickaxe needs 3 planks + 2 sticks; sticks need 2 planks; "
    "planks need 1 log -> so check your inventory and figure out how many logs to gather). "
    "Keep a checklist with [ ] / [x] and update it as you progress, fail, or find new resources."
)

# actions the mod executes and reports back as completed (the agent awaits them)
# vs instant actions that return immediately with no completion event.
_INSTANT = {"request_screenshot", "check_death_log", "stop_moving", "chat"}

# name -> (description, json-schema parameters)
_TOOLS: Dict[str, Tuple[str, Dict[str, Any]]] = {
    "mine_block": ("Navigate to and mine a specific block.", {
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"}},
        "required": ["x", "y", "z"],
    }),
    "attack_entity": ("Attack a specific entity.", {
        "type": "object",
        "properties": {"target": {"type": "integer", "description": "Entity ID of the target."}},
        "required": ["target"],
    }),
    "move_to": ("Move to specific coordinates.", {
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"}},
        "required": ["x", "y", "z"],
    }),
    "stop_moving": ("Stop all movement immediately.", {"type": "object", "properties": {}}),
    "request_screenshot": ("Request a visual screenshot of the current view.", {"type": "object", "properties": {}}),
    "look_at": ("Look at specific coordinates.", {
        "type": "object",
        "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "z": {"type": "number"}},
        "required": ["x", "y", "z"],
    }),
    "place_block": ("Place a block at specific coordinates. Can specify block type.", {
        "type": "object",
        "properties": {
            "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
            "block": {"type": "string", "description": "Optional block name to place"},
        },
        "required": ["x", "y", "z"],
    }),
    "select_slot": ("Select a hotbar slot (0-8).", {
        "type": "object",
        "properties": {"slot": {"type": "integer", "minimum": 0, "maximum": 8}},
        "required": ["slot"],
    }),
    "find_block": ("Find the nearest block of a given type.", {
        "type": "object",
        "properties": {
            "block": {"type": "string"},
            "max_distance": {"type": "integer", "default": 100, "description": "Maximum search radius."},
        },
        "required": ["block"],
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
        "properties": {"item": {"type": "string"}},
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
    "equip_item": ("Equip an item from inventory to main hand.", {
        "type": "object",
        "properties": {"item": {"type": "string"}},
        "required": ["item"],
    }),
    "discard_item": ("Discard (throw away) items.", {
        "type": "object",
        "properties": {
            "item": {"type": "string"},
            "all": {"type": "boolean", "description": "Discard all stacks of this item?"},
        },
        "required": ["item"],
    }),
    "eat_food": ("Eat the best available food.", {"type": "object", "properties": {}}),
    "check_death_log": ("Check the last death details.", {"type": "object", "properties": {}}),
    "chat": ("Send a chat message in-game.", {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }),
}


def build_minecraft_tools(client: MinecraftClient, notebook: Notebook) -> ToolRegistry:
    """Builds a registry whose handlers drive the mod and return observations.

    Also registers the local `update_notebook` tool, which mutates the agent's
    private working memory instead of talking to the mod.
    """
    registry = ToolRegistry()

    def make_handler(action: str, instant: bool):
        async def handler(**kwargs):
            return await client.execute(action, kwargs, instant=instant)
        return handler

    for name, (description, parameters) in _TOOLS.items():
        instant = name in _INSTANT
        # long-running body actions run async (single-slot) so they never block reasoning
        registry.add(name, description, parameters, make_handler(name, instant), long_running=not instant)

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

    return registry
