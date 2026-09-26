"""A build, turned into the blocks it asks for.

The same arguments the body's `build` action takes (origin, rotation, palette,
layers, ops) become a map `(x, y, z) -> block`, plus what it costs against
what she carries. Pure: BeaCraft's BuildSkill must expand the same way, and
the vectors in tests/fixtures/minecraft_blueprints/ hold both sides to it.

Templates use mindcraft's format (src/agent/npc/construction/*.json in
mindcraft-bots/mindcraft, MIT): `blocks[y][z][x]`, "" for "leave as it is",
generic names like "planks" resolved from the inventory.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

Cell = Tuple[int, int, int]

MAX_CELLS = 2000
# blocks from one end of a build to the other, along any axis: more is coordinates
# given as absolute where they were meant relative to the origin
MAX_SPAN = 256
ROTATIONS = (0, 90, 180, 270)
OPS = {"fill", "walls", "set", "roof"}
KEYS = {"origin", "rotation", "palette", "layers", "ops", "clear", "dry_run"}
# overworld woods; dark_oak and pale_oak first so "oak" never swallows them
WOODS = ("dark_oak", "pale_oak", "oak", "spruce", "birch", "jungle", "acacia",
         "mangrove", "cherry")
# mindcraft's MATCHING_WOOD_BLOCKS (src/utils/mcdata.js#L21-L34)
WOODEN = ("log", "planks", "sign", "boat", "fence_gate", "door", "fence", "slab",
          "stairs", "button", "pressure_plate", "trapdoor")
FACINGS = ("north", "east", "south", "west")   # clockwise from above
COLORS = ("white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray",
          "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black")


class BlueprintError(ValueError):
    pass


_INTEGER = re.compile(r"[+-]?[0-9]+")


@dataclass
class Blueprint:
    cells: Dict[Cell, str]                     # absolute position -> block ("air" = clear it)
    items: Dict[str, int] = field(default_factory=dict)   # what placing it all takes

    def to_place(self) -> Dict[Cell, str]:
        return {c: b for c, b in self.cells.items() if split_state(b)[0] != "air"}


def rotate(x: int, y: int, z: int, rotation: int) -> Cell:
    """Clockwise seen from above (+x east, +z south): east turns south at 90."""
    if rotation == 90:
        return (-z, y, x)
    if rotation == 180:
        return (-x, y, -z)
    if rotation == 270:
        return (z, y, -x)
    return (x, y, z)


def split_state(block: str) -> Tuple[str, Dict[str, str]]:
    """"oak_door[facing=south,half=lower]" -> ("oak_door", {"facing": "south", "half": "lower"})."""
    if "[" not in block:
        return block, {}
    name, _, rest = block.partition("[")
    if not rest.endswith("]"):
        raise BlueprintError(f"bad block state: {block}")
    props = {}
    for pair in filter(None, rest[:-1].split(",")):
        key, eq, value = pair.partition("=")
        if not eq:
            raise BlueprintError(f"bad block state: {block}")
        props[key.strip()] = value.strip()
    return name, props


def rotate_state(block: str, rotation: int) -> str:
    """Turn `facing` and `axis` with the build, so a rotated house keeps its door on the front."""
    name, props = split_state(block)
    if not props or rotation == 0:
        return block
    steps = rotation // 90
    if props.get("facing") in FACINGS:
        props["facing"] = FACINGS[(FACINGS.index(props["facing"]) + steps) % 4]
    if props.get("axis") in ("x", "z") and steps % 2:
        props["axis"] = "z" if props["axis"] == "x" else "x"
    return name + "[" + ",".join(f"{k}={v}" for k, v in props.items()) + "]"


def expand(args: Dict[str, Any]) -> Blueprint:
    """The cells a build asks for. Every malformed argument is a BlueprintError whose
    text is the same one BeaCraft's Blueprint.java gives for it."""
    unknown = set(args) - KEYS
    if unknown:
        raise BlueprintError(f"unknown argument: {sorted(unknown)[0]}")
    origin = args.get("origin")
    try:
        if not isinstance(origin, dict):
            raise TypeError
        ox, oy, oz = _int(origin["x"]), _int(origin["y"]), _int(origin["z"])
    except (KeyError, TypeError, ValueError):
        raise BlueprintError("origin needs x, y and z") from None
    try:
        rotation = 0 if args.get("rotation") is None else _int(args["rotation"])
    except (TypeError, ValueError):
        rotation = -1
    if rotation not in ROTATIONS:
        raise BlueprintError("rotation must be 0, 90, 180 or 270")

    relative: Dict[Cell, str] = {}
    raw_palette = args.get("palette")
    if raw_palette is None:
        raw_palette = {}
    if not isinstance(raw_palette, dict):
        raise BlueprintError("palette must map one character to a block, like {\"#\": \"cobblestone\"}")
    palette: Dict[str, str] = {}
    for key, value in raw_palette.items():
        if len(key) != 1:
            raise BlueprintError(f"palette key '{key}' must be one character")
        palette[key] = _block(value, f"palette['{key}']")
    layers = args.get("layers")
    if layers is None:
        layers = []
    if not isinstance(layers, list):
        raise BlueprintError("layers must be a list of layers, each a list of rows (strings)")
    for y, layer in enumerate(layers):
        if not isinstance(layer, list):
            raise BlueprintError(f"layers[{y}] must be a list of rows (strings)")
        for z, row in enumerate(layer):
            if not isinstance(row, str):
                raise BlueprintError(f"layers[{y}][{z}] must be a string")
            for x, ch in enumerate(row):
                if ch == " ":
                    continue
                if ch not in palette:
                    raise BlueprintError(f"layer {y} row {z}: '{ch}' is not in the palette")
                relative[(x, y, z)] = palette[ch]
    ops = args.get("ops")
    if ops is None:
        ops = []
    if not isinstance(ops, list):
        raise BlueprintError("ops must be a list of objects")
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            raise BlueprintError(f"ops[{i}] must be an object")
        for cell, block in _op(op, i):
            relative[cell] = block
    if len(relative) > MAX_CELLS:
        raise BlueprintError(f"{len(relative)} cells; the most a build takes is {MAX_CELLS}")
    if not relative:
        raise BlueprintError("nothing to build: give layers or ops")
    check_span(relative)

    cells: Dict[Cell, str] = {}
    for (x, y, z), block in relative.items():
        rx, ry, rz = rotate(x, y, z, rotation)
        cells[(ox + rx, oy + ry, oz + rz)] = rotate_state(block, rotation)
    return Blueprint(cells, items_needed(cells))


def check_span(cells: Iterable[Cell]) -> None:
    """A build fits in MAX_SPAN blocks along each axis; the usual reason it does not is a
    coordinate given as absolute (x=1200) next to relative ones (x=0)."""
    points = list(cells)
    for axis, name in enumerate("xyz"):
        low = min(p[axis] for p in points)
        high = max(p[axis] for p in points)
        if high - low + 1 > MAX_SPAN:
            raise BlueprintError(
                f"the build spans {high - low + 1} blocks along {name} (from {low} to {high}); the most is "
                f"{MAX_SPAN}: are some coordinates absolute where they should be relative to the origin?")


def _op(op: Dict[str, Any], i: int) -> Iterable[Tuple[Cell, str]]:
    kind = op.get("op")
    if not isinstance(kind, str) or kind not in OPS:
        raise BlueprintError(f"ops[{i}]: op must be one of {sorted(OPS)}")
    block = _block(op.get("block"), f"ops[{i}]")
    if kind == "set":
        x, y, z = _vec(op, "at", i)
        yield (x, y, z), block
        return
    (x1, y1, z1), (x2, y2, z2) = _vec(op, "from", i), _vec(op, "to", i)
    hollow = _flag(op.get("hollow"), f"ops[{i}]: hollow")
    xs = range(min(x1, x2), max(x1, x2) + 1)
    ys = range(min(y1, y2), max(y1, y2) + 1)
    zs = range(min(z1, z2), max(z1, z2) + 1)
    if len(xs) * len(ys) * len(zs) > MAX_CELLS:
        raise BlueprintError(f"ops[{i}] covers more than {MAX_CELLS} cells")
    for y in ys:
        for z in zs:
            for x in xs:
                edge = x in (xs[0], xs[-1]) or z in (zs[0], zs[-1])
                shell = edge or y in (ys[0], ys[-1])
                if kind == "walls" and not edge:
                    continue
                if kind == "fill" and hollow and not shell:
                    yield (x, y, z), "air"
                    continue
                yield (x, y, z), block      # "roof" is a fill kept for readability


def _vec(op: Mapping[str, Any], key: str, i: int) -> Cell:
    v = op.get(key)
    try:
        if not isinstance(v, list) or len(v) != 3:
            raise ValueError
        return _int(v[0]), _int(v[1]), _int(v[2])
    except ValueError:
        raise BlueprintError(f"ops[{i}]: {key} must be [x, y, z]") from None


def _int(value: Any) -> int:
    """A whole number as JSON gives it: 5, 5.0 (cut to 5) or "5"; never true, never out of an int."""
    if isinstance(value, bool):
        raise ValueError(value)
    if isinstance(value, int):
        n = value
    elif isinstance(value, float) and math.isfinite(value):
        n = int(value)
    elif isinstance(value, str) and _INTEGER.fullmatch(value):
        n = int(value)
    else:
        raise ValueError(value)
    if not -2**31 <= n < 2**31:
        raise ValueError(value)
    return n


def _flag(value: Any, where: str) -> bool:
    """true/false, 0/1 or "true"/"false"; anything else is a mistake worth saying."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise BlueprintError(f"{where} must be true or false")


def _block(value: Any, where: str) -> str:
    if value is None or value == "":
        raise BlueprintError(f"{where}: missing block")
    if not isinstance(value, str):
        raise BlueprintError(f"{where}: a block is a name like 'cobblestone'")
    name = value.removeprefix("minecraft:")
    if not name:
        raise BlueprintError(f"{where}: missing block")
    return name


def _name(block: Any) -> str:
    return str(block or "").removeprefix("minecraft:")


# -- what it costs ------------------------------------------------------

def items_needed(cells: Dict[Cell, str]) -> Dict[str, int]:
    """One item per cell, except the halves a single item fills: a door's top, a bed's foot."""
    out: Dict[str, int] = {}
    paired: set = set()
    for (x, y, z), block in sorted(cells.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
        block = split_state(block)[0]
        if block == "air" or (x, y, z) in paired:
            continue
        if _is(block, "door") and split_state(cells.get((x, y + 1, z), ""))[0] == block:
            paired.add((x, y + 1, z))
        elif _is(block, "bed"):
            for dx, dz in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                other = (x + dx, y, z + dz)
                if split_state(cells.get(other, ""))[0] == block and other not in paired:
                    paired.add(other)
                    break
        out[block] = out.get(block, 0) + 1
    return out


def _is(block: str, kind: str) -> bool:
    return block == kind or block.endswith("_" + kind)


def shortfall(items: Dict[str, int], inventory: Dict[str, int]) -> Dict[str, int]:
    """What is still missing, with generic names ("planks") met by any wood."""
    missing: Dict[str, int] = {}
    left = dict(inventory)
    for block, n in sorted(items.items()):
        for name in [k for k in left if satisfies_item(block, k)]:
            take = min(left[name], n)
            left[name] -= take
            n -= take
        if n > 0:
            missing[block] = n
    return missing


def satisfies_item(block: str, item: str) -> bool:
    if block in WOODEN:
        return item.endswith("_" + block) and any(item.startswith(w + "_") for w in WOODS)
    if block == "bed":
        return item.endswith("_bed")
    return item == block


# -- the world side -----------------------------------------------------

def satisfied(target: str, current: str) -> bool:
    """Is the block already there good enough? mindcraft npc/utils.js#L73-L84, plus walls."""
    current = split_state(_name(current))[0]
    target = split_state(target)[0]
    if target == "air":
        return current in ("air", "cave_air", "void_air")
    if target == "dirt":
        return current in ("dirt", "grass_block")
    if target in WOODEN:
        return current.endswith("_" + target)
    if target == "bed":
        return current.endswith("_bed")
    if target == "torch":
        return current in ("torch", "wall_torch")
    return current == target


def resolve_generic(block: str, inventory: Dict[str, int],
                    nearest_log: Optional[str] = None) -> str:
    """"planks" -> the wood she carries most of; "bed" -> the wool colour she has most of.

    Port of mindcraft's getTypeOfGeneric (npc/utils.js#L5-L70) with its two slips
    fixed: `item.includes('oak')` also counted dark_oak, and
    `name.split('_')[0]` turned dark_oak_log into "dark".
    """
    if block in WOODEN:
        counts: Dict[str, int] = {}
        for item, n in inventory.items():
            wood = _wood(item)
            if wood:
                counts[wood] = counts.get(wood, 0) + n
        if counts:
            return f"{max(sorted(counts), key=lambda w: counts[w])}_{block}"
        wood = _wood(nearest_log or "")
        return f"{wood or 'oak'}_{block}"
    if block == "bed":
        wool = {c: inventory.get(f"{c}_wool", 0) for c in COLORS}
        best = max(COLORS, key=lambda c: wool[c])
        return f"{best if wool[best] else 'white'}_bed"
    return block


def _wood(name: str) -> str:
    return next((w for w in WOODS if name.startswith(w + "_")), "")


def from_template(template: Dict[str, Any], x: int, y: int, z: int, rotation: int,
                  inventory: Dict[str, int], nearest_log: Optional[str] = None) -> Dict[str, Any]:
    """A mindcraft template placed with its ground floor at (x, y, z), as `build` arguments."""
    palette: Dict[str, str] = {}
    chars = iter("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
    layers: List[List[str]] = []
    for layer in template["blocks"]:
        rows = []
        for row in layer:
            line = ""
            for name in row:
                if not name:
                    line += " "
                    continue
                generic, props = split_state(name)
                block = resolve_generic(generic, inventory, nearest_log)
                if props:
                    block += "[" + ",".join(f"{k}={v}" for k, v in props.items()) + "]"
                if block not in palette:
                    palette[block] = next(chars)
                line += palette[block]
            rows.append(line)
        layers.append(rows)
    return {
        "origin": {"x": x, "y": y + int(template.get("offset", 0)), "z": z},
        "rotation": rotation,
        "palette": {ch: block for block, ch in palette.items()},
        "layers": layers,
    }
