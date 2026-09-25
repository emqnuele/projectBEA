"""The body's building tools that are worked out here, before the mod sees anything.

`build` itself is a mod action (tools.py). These sit in front of it: costing a
build against what she carries, the ready-made houses, and build scripts. Each
one ends, if it builds at all, in an ordinary `build`.
"""

import asyncio
import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.core.agent.tools import ToolRegistry
from src.core.skills.minecraft.blueprint import (
    BlueprintError,
    expand,
    from_template,
    items_needed,
    shortfall,
)
from src.core.skills.minecraft.buildscript import ScriptError, preview
from src.core.skills.minecraft.client import MinecraftClient
from src.core.skills.minecraft.state import count_items

TEMPLATES = Path(__file__).resolve().parents[4] / "data" / "minecraft" / "blueprints"
BUILD_TIMEOUT = 900.0
_OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}

_ORIGIN = {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"},
                                            "z": {"type": "integer"}},
           "required": ["x", "y", "z"]}
_ROTATION = {"type": "integer", "enum": [0, 90, 180, 270],
             "description": "Clockwise seen from above; defaults to 0."}

_PLAN_DESC = (
    "Work out what a build takes before starting it: the same arguments as `build`, "
    "answered at once with the number of cells, the blocks it needs and what you are short "
    "of. It does not look at the world: to know what is already standing there, call "
    "`build` with dry_run."
)
_LIST_DESC = "The ready-made buildings you can put up with build_template, with their size and cost."
_TEMPLATE_DESC = (
    "Put up a ready-made building (see list_templates) with its ground floor at (x, y, z): "
    "stand on the ground and pass your feet's y. Wood and bed colour follow what you carry. "
    "list_templates says which side its door is on at rotation 0; rotation turns it "
    "clockwise. Whatever stands in its cells is broken to make way. dry_run only reports "
    "what is missing."
)
_SCRIPT_DESC = (
    "Draw a build with a short Python script, for shapes a template or ops cannot say "
    "(towers, stairs, domes, anything with loops or curves). The script only draws cells "
    "relative to its own (0, 0, 0), which lands on (x, y, z): set(x,y,z,block), "
    "fill(x1,y1,z1,x2,y2,z2,block,hollow=False), walls(x1,y1,z1,x2,y2,z2,block), "
    "line(x1,y1,z1,x2,y2,z2,block), circle(cx,y,cz,r,block,filled=False), get(x,y,z), "
    "note(...); maths: sin cos tan atan2 sqrt floor ceil radians hypot pi. No imports, no "
    "attributes (x.y), 3 s, 2000 cells. 'air' means empty; states like "
    "'oak_slab[type=top]' work. With confirm=false (the default) nothing is built: you get "
    "the box it fills and what it costs. Read it, gather, then send the same script with "
    "confirm=true. Your notes are not rotated with the build."
)


def load_templates() -> Dict[str, Dict[str, Any]]:
    """Every template shipped in data/minecraft/blueprints, by name."""
    out: Dict[str, Dict[str, Any]] = {}
    for path in sorted(TEMPLATES.glob("*.json")):
        template = json.loads(path.read_text(encoding="utf-8"))
        out[str(template.get("name") or path.stem)] = template
    return out


def door_facing(template: Dict[str, Any]) -> Optional[str]:
    """Which way a door placed from outside faces: into the house, away from its nearest edge.

    The templates name a door and nothing more, and a door takes its facing
    from where the player looks. Standing outside and looking in, the door
    faces into the house.
    """
    for layer in template["blocks"]:
        for z, row in enumerate(layer):
            for x, name in enumerate(row):
                if name != "door":
                    continue
                depth, width = len(layer), len(row)
                to_z = min(z, depth - 1 - z)
                to_x = min(x, width - 1 - x)
                if to_z <= to_x:
                    return "north" if z > (depth - 1) / 2 else "south"
                return "west" if x > (width - 1) / 2 else "east"
    return None


def with_door_facing(template: Dict[str, Any]) -> Dict[str, Any]:
    facing = door_facing(template)
    if facing is None:
        return template
    turned = copy.deepcopy(template)
    turned["blocks"] = [[[f"door[facing={facing}]" if n == "door" else n for n in row] for row in layer]
                        for layer in template["blocks"]]
    return turned


def describe_template(name: str, template: Dict[str, Any]) -> str:
    blocks = template["blocks"]
    height, depth, width = len(blocks), len(blocks[0]), len(blocks[0][0])
    cells = {(x, y, z): n for y, layer in enumerate(blocks) for z, row in enumerate(layer)
             for x, n in enumerate(row) if n}
    cost = ", ".join(f"{b} {n}" for b, n in sorted(items_needed(cells).items()))
    below = -int(template.get("offset", 0))
    sunk = f", its floor {below} below ground" if below else ""
    facing = door_facing(template)
    door = f", door on the {_OPPOSITE[facing]} side" if facing else ""
    return f"{name}: {width} wide (x) by {depth} deep (z) by {height} high{sunk}{door}; needs {cost}"


def nearest_log(state: Optional[Dict[str, Any]]) -> Optional[str]:
    """The kind of log nearest to her in the state's resources: the wood a build defaults to."""
    resources = (state or {}).get("resources") or {}
    logs = [(float((info.get("nearest") or {}).get("distance", 1e9)), name)
            for name, info in resources.items() if name.endswith("_log") and isinstance(info, dict)]
    return min(logs)[1] if logs else None


def _missing_line(items: Dict[str, int], inventory: Dict[str, int]) -> str:
    missing = shortfall(items, inventory)
    if not missing:
        return "you carry everything it needs"
    return "you are short of " + ", ".join(f"{n} {b}" for b, n in sorted(missing.items()))


def register_building_tools(registry: ToolRegistry, client: MinecraftClient, surface: str,
                            build_scripts: bool = True) -> None:
    """plan_build, list_templates, build_template and (when allowed) build_script."""

    def inventory() -> Dict[str, int]:
        return count_items(client.latest_state)

    def plan_build(**args: Any) -> str:
        try:
            bp = expand(args)
        except BlueprintError as e:
            return f"ERROR: {e}"
        items = ", ".join(f"{n} {b}" for b, n in sorted(bp.items.items())) or "nothing to place"
        cleared = sum(1 for b in bp.cells.values() if b == "air")
        empty = f", {cleared} to leave empty" if cleared else ""
        return f"{len(bp.cells)} cells{empty}; it takes {items}; {_missing_line(bp.items, inventory())}."

    def list_templates() -> str:
        templates = load_templates()
        if not templates:
            return "there are no templates."
        return "\n".join(describe_template(n, t) for n, t in templates.items())

    async def build_template(name: str, x: int, y: int, z: int, rotation: int = 0,
                             dry_run: bool = False) -> str:
        templates = load_templates()
        template = templates.get(str(name).strip())
        if template is None:
            return f"ERROR: no template '{name}'; there are {', '.join(templates)}."
        args = from_template(with_door_facing(template), int(x), int(y), int(z), int(rotation), inventory(),
                             nearest_log(client.latest_state))
        # a template's floor sits in the ground: whatever holds its cells makes way
        args["clear"] = True
        if dry_run:
            args["dry_run"] = True
        return await client.execute("build", args, timeout=BUILD_TIMEOUT)

    async def build_script(code: str, x: int, y: int, z: int, rotation: int = 0,
                           confirm: bool = False) -> str:
        try:
            args, _bp, text = await asyncio.to_thread(
                preview, str(code), int(x), int(y), int(z), int(rotation), inventory())
        except (ScriptError, BlueprintError) as e:
            return f"ERROR: {e}"
        if not confirm:
            return "PREVIEW (nothing built yet):\n" + text
        return await client.execute("build", args, timeout=BUILD_TIMEOUT)

    registry.add("plan_build", _PLAN_DESC, {
        "type": "object",
        "properties": {
            "origin": _ORIGIN, "rotation": _ROTATION,
            "palette": {"type": "object", "additionalProperties": {"type": "string"}},
            "layers": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
            "ops": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["origin"],
    }, plan_build, surface=surface)
    registry.add("list_templates", _LIST_DESC, {"type": "object", "properties": {}},
                 list_templates, surface=surface)
    registry.add("build_template", _TEMPLATE_DESC, {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
            "rotation": _ROTATION,
            "dry_run": {"type": "boolean"},
        },
        "required": ["name", "x", "y", "z"],
    }, build_template, long_running=True, surface=surface)
    if build_scripts:
        registry.add("build_script", _SCRIPT_DESC, {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
                "rotation": _ROTATION,
                "confirm": {"type": "boolean", "description": "true builds it; false (default) previews."},
            },
            "required": ["code", "x", "y", "z"],
        }, build_script, long_running=True, surface=surface)
