"""Extract Minecraft's crafting/smelting recipes and item tags into one compact JSON.

    uv run python tools/mc_recipes.py 26.2                  # downloads the jar from Mojang
    uv run python tools/mc_recipes.py path/to/server.jar 26.2

Writes data/minecraft/recipes/<version>.json. One file per supported version:
the brain picks the one matching the `mc_version` the mod announces.

Accepts the vanilla server jar as downloaded from Mojang (a bundler jar whose
real game jar sits at META-INF/versions/<v>/server-<v>.jar) or the inner jar.
Only what the planner uses is kept: crafting_shaped, crafting_shapeless and
smelting. Names are short (no `minecraft:` prefix); a tag is `#name`.
"""

import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import IO, Any, Dict, FrozenSet, List, Union

MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "minecraft" / "recipes"

RECIPE_DIR = "data/minecraft/recipe/"
TAG_DIR = "data/minecraft/tags/item/"
KEPT = {"minecraft:crafting_shaped", "minecraft:crafting_shapeless", "minecraft:smelting"}


def short(name: str) -> str:
    tag = name.startswith("#")
    bare = name.lstrip("#").removeprefix("minecraft:")
    return f"#{bare}" if tag else bare


def option_key(ingredient: Any) -> str:
    """One grid slot: an item, a tag, or a list of alternatives joined by `|`."""
    if isinstance(ingredient, list):
        return "|".join(sorted(short(i) for i in ingredient))
    return short(ingredient)


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def download_server_jar(version: str) -> io.BytesIO:
    versions = json.loads(_get(MANIFEST))["versions"]
    entry = next((v for v in versions if v["id"] == version), None)
    if entry is None:
        raise SystemExit(f"Mojang has no Minecraft {version}")
    meta = json.loads(_get(entry["url"]))
    return io.BytesIO(_get(meta["downloads"]["server"]["url"]))


def game_jar(source: Union[str, Path, IO[bytes]]) -> zipfile.ZipFile:
    outer = zipfile.ZipFile(source)
    inner = [n for n in outer.namelist() if n.startswith("META-INF/versions/") and n.endswith(".jar")]
    if inner:
        return zipfile.ZipFile(io.BytesIO(outer.read(inner[0])))
    return outer


def convert(recipe: Dict[str, Any]) -> Dict[str, Any]:
    kind = recipe["type"]
    ingredients: Dict[str, int] = {}
    if kind == "minecraft:crafting_shaped":
        pattern: List[str] = recipe["pattern"]
        width, height = max(len(row) for row in pattern), len(pattern)
        for row in pattern:
            for ch in row:
                if ch != " ":
                    key = option_key(recipe["key"][ch])
                    ingredients[key] = ingredients.get(key, 0) + 1
        # the shape decides, not the count: a slab is three planks in a row
        grid = "2x2" if width <= 2 and height <= 2 else "3x3"
    elif kind == "minecraft:crafting_shapeless":
        for ing in recipe["ingredients"]:
            key = option_key(ing)
            ingredients[key] = ingredients.get(key, 0) + 1
        grid = "2x2" if len(recipe["ingredients"]) <= 4 else "3x3"
    else:
        ingredients[option_key(recipe["ingredient"])] = 1
        grid = "furnace"
    return {
        "type": kind.removeprefix("minecraft:"),
        "grid": grid,
        "ingredients": ingredients,
        "count": int(recipe["result"].get("count", 1)),
    }


def extract(jar: zipfile.ZipFile) -> Dict[str, Any]:
    recipes: Dict[str, List[Dict[str, Any]]] = {}
    raw_tags: Dict[str, List[str]] = {}
    for name in sorted(jar.namelist()):
        if name.startswith(RECIPE_DIR) and name.endswith(".json"):
            data = json.loads(jar.read(name))
            if data.get("type") not in KEPT:
                continue
            entry = convert(data)
            entry["id"] = name[len(RECIPE_DIR):-5]
            recipes.setdefault(short(data["result"]["id"]), []).append(entry)
        elif name.startswith(TAG_DIR) and name.endswith(".json"):
            values = json.loads(jar.read(name))["values"]
            raw_tags[name[len(TAG_DIR):-5]] = [v if isinstance(v, str) else v["id"] for v in values]
    return {"recipes": recipes, "tags": {t: flatten(t, raw_tags) for t in sorted(raw_tags)}}


def flatten(tag: str, raw: Dict[str, List[str]], seen: FrozenSet[str] = frozenset()) -> List[str]:
    """Tags point at other tags (`logs` -> `#logs_that_burn` -> `#oak_logs`); resolve to items."""
    out: List[str] = []
    for value in raw.get(tag, []):
        if value.startswith("#"):
            inner = short(value)[1:]
            if inner not in seen:
                out += flatten(inner, raw, seen | {tag})
        else:
            out.append(short(value))
    return sorted(set(out))


def main() -> None:
    if len(sys.argv) == 2:
        version, source = sys.argv[1], download_server_jar(sys.argv[1])
    elif len(sys.argv) == 3:
        source, version = sys.argv[1], sys.argv[2]
    else:
        raise SystemExit(__doc__)
    data = extract(game_jar(source))
    data["version"] = version
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dst = OUT_DIR / f"{version}.json"
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"), sort_keys=True)
    n = sum(len(v) for v in data["recipes"].values())
    print(f"{n} recipes for {len(data['recipes'])} items, {len(data['tags'])} tags -> {dst}")


if __name__ == "__main__":
    main()
