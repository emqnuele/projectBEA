"""What it takes to make an item, from what she carries.

A pure planner over `data/minecraft/recipes/<version>.json` (made by
tools/mc_recipes.py, one file per Minecraft version she supports).
It walks the recipe tree the way mindcraft's getDetailedCraftingPlan does
(src/utils/mcdata.js#L464-L572) and adds what that one leaves out: tags and
alternative ingredients, a choice between several recipes for one item,
smelting with fuel, and whether a crafting table or a furnace is needed.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RECIPES_DIR = Path(__file__).resolve().parents[4] / "data" / "minecraft" / "recipes"

# Items a furnace burn smelts, read from FuelValues.vanillaBurnTimes in the 26.2
# server jar (burn ticks / 200 ticks per smelt). Tags are expanded on load.
FUEL = {
    "lava_bucket": 100.0, "coal_block": 80.0, "blaze_rod": 12.0,
    "coal": 8.0, "charcoal": 8.0,
    "#logs": 1.5, "#planks": 1.5, "#wooden_stairs": 1.5, "#wooden_slabs": 0.75,
    "stick": 0.5, "#saplings": 0.5,
}
# FuelValues ends with `.remove(ItemTags.NON_FLAMMABLE_WOOD)`: crimson and warped wood don't burn.
NOT_FUEL_TAG = "non_flammable_wood"
# preferred picks when several items would do equally well
COMMON = ("oak_log", "oak_planks", "cobblestone", "coal", "stick", "raw_iron")
MAX_DEPTH = 12


@dataclass
class Step:
    item: str
    recipe: str
    kind: str          # "craft" | "smelt"
    grid: str          # "2x2" | "3x3" | "furnace"
    times: int         # how many crafts / smelts
    makes: int         # items produced in total
    uses: Dict[str, int]


@dataclass
class Plan:
    item: str
    count: int
    steps: List[Step] = field(default_factory=list)
    missing: Dict[str, int] = field(default_factory=dict)
    leftovers: Dict[str, int] = field(default_factory=dict)
    fuel: Dict[str, int] = field(default_factory=dict)
    smelts: int = 0

    @property
    def needs_table(self) -> bool:
        return any(s.grid == "3x3" for s in self.steps)

    @property
    def needs_furnace(self) -> bool:
        return self.smelts > 0

    @property
    def cost(self) -> Tuple[int, int]:
        return sum(self.missing.values()), len(self.steps)


class Recipes:
    def __init__(self, data: Dict[str, Any]):
        self.version: str = str(data.get("version", ""))
        self.recipes: Dict[str, List[Dict[str, Any]]] = data["recipes"]
        self.tags: Dict[str, List[str]] = data["tags"]
        blocked = set(self.tags.get(NOT_FUEL_TAG, []))
        self.fuel: Dict[str, float] = {}
        for key, value in FUEL.items():
            for item in self.options(key):
                if item not in blocked:
                    self.fuel.setdefault(item, value)

    @classmethod
    def load(cls, version: str, folder: Path = RECIPES_DIR) -> "Recipes":
        """The recipes of the game she is in; else the newest older version we have.

        `version` is the `mc_version` the mod announces in its handshake.
        """
        path = folder / f"{version}.json"
        if not path.exists():
            older = [p for p in folder.glob("*.json") if _key(p.stem) <= _key(version)]
            if not older:
                raise FileNotFoundError(f"no recipe data for Minecraft {version} or older")
            path = max(older, key=lambda p: _key(p.stem))
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @staticmethod
    def supported(folder: Path = RECIPES_DIR) -> List[str]:
        return sorted((p.stem for p in folder.glob("*.json")), key=_key)

    def options(self, key: str) -> List[str]:
        """`#planks` -> every plank; `coal|charcoal` -> both; `stick` -> [stick]."""
        out: List[str] = []
        for part in key.split("|"):
            out += self.tags.get(part[1:], []) if part.startswith("#") else [part]
        return out

    def plan(self, item: str, count: int, inventory: Dict[str, int]) -> Plan:
        inv = {k: v for k, v in inventory.items() if v > 0}
        plan = Plan(item, count)
        self._need(item, count, inv, plan, (), 0)
        self._add_fuel(plan, inv)
        plan.steps = _merge(plan.steps)
        plan.leftovers = {k: v for k, v in plan.leftovers.items() if v > 0}
        return plan

    # -- the walk -------------------------------------------------------

    def _need(self, item: str, count: int, inv: Dict[str, int], plan: Plan,
              stack: Tuple[str, ...], depth: int) -> None:
        have = inv.get(item, 0)
        take = min(have, count)
        if take:
            inv[item] = have - take
            if plan.leftovers.get(item):
                plan.leftovers[item] = max(0, plan.leftovers[item] - take)
        short = count - take
        if short <= 0:
            return
        best: Optional[Tuple[Tuple[int, int, int, str], Dict[str, int], Plan]] = None
        for recipe in self.recipes.get(item, []) if depth < MAX_DEPTH else []:
            if self._reversible(item, recipe) and not any(
                    inv.get(o) for k in recipe["ingredients"] for o in self.options(k)):
                continue  # unpacking a block she doesn't have is never the easy way
            if _uses_ore(recipe) and not any(inv.get(k) for k in recipe["ingredients"]):
                continue  # mining the ore already drops coal / raw_iron / diamond
            trial_inv, trial = dict(inv), _fork(plan)
            if not self._apply(item, recipe, short, trial_inv, trial, stack + (item,), depth):
                continue
            rank = (*trial.cost, _uses_ore(recipe), str(recipe["id"]))
            if best is None or rank < best[0]:
                best = (rank, trial_inv, trial)
        if best is None:
            plan.missing[item] = plan.missing.get(item, 0) + short
            return
        _, trial_inv, trial = best
        inv.clear()
        inv.update(trial_inv)
        _adopt(plan, trial)

    def _apply(self, item: str, recipe: Dict[str, Any], short: int, inv: Dict[str, int],
               plan: Plan, stack: Tuple[str, ...], depth: int) -> bool:
        times = math.ceil(short / recipe["count"])
        uses: Dict[str, int] = {}
        for key, per in recipe["ingredients"].items():
            options = self.options(key)
            # spent items stay in inv at 0, so "carried" means a positive count
            if any(o in stack for o in options) and all(o in stack or not inv.get(o) for o in options):
                return False  # the recipe loops back (iron_ingot <- iron_block <- iron_ingot)
            for name, n in self._pick(options, per * times, inv, stack).items():
                self._need(name, n, inv, plan, stack, depth + 1)
                uses[name] = uses.get(name, 0) + n
        made = times * recipe["count"]
        kind = "smelt" if recipe["grid"] == "furnace" else "craft"
        plan.steps.append(Step(item, recipe["id"], kind, recipe["grid"], times, made, uses))
        if kind == "smelt":
            plan.smelts += times
        if made > short:
            plan.leftovers[item] = plan.leftovers.get(item, 0) + made - short
            inv[item] = inv.get(item, 0) + made - short
        return True

    def _reversible(self, item: str, recipe: Dict[str, Any]) -> bool:
        """iron_block -> 9 iron_ingot and back: a storage pair, not a way to make things."""
        if len(recipe["ingredients"]) != 1:
            return False
        for option in self.options(next(iter(recipe["ingredients"]))):
            for back in self.recipes.get(option, []):
                if list(back["ingredients"]) == [item]:
                    return True
        return False

    def _pick(self, options: List[str], n: int, inv: Dict[str, int],
              stack: Tuple[str, ...]) -> Dict[str, int]:
        """Split `n` over interchangeable items: what she has first, then one to make."""
        if len(options) == 1:
            return {options[0]: n}
        chosen: Dict[str, int] = {}
        for name in sorted(options, key=lambda o: -inv.get(o, 0)):
            if n <= 0 or inv.get(name, 0) <= 0:
                break
            use = min(inv[name], n)
            chosen[name] = use
            n -= use
        if n > 0:
            usable = [o for o in options if o not in stack]
            rest = min(usable or options, key=lambda o: self._rank_option(o, n, inv, stack))
            chosen[rest] = chosen.get(rest, 0) + n
        return chosen

    def _rank_option(self, name: str, n: int, inv: Dict[str, int],
                     stack: Tuple[str, ...]) -> Tuple[int, int, int, int, str]:
        trial = Plan(name, n)
        self._need(name, n, dict(inv), trial, stack, MAX_DEPTH - 3)
        family = sum(v for k, v in inv.items() if _family(k) and _family(k) == _family(name))
        return (*trial.cost, -family, 0 if name in COMMON else 1, name)

    def _add_fuel(self, plan: Plan, inv: Dict[str, int]) -> None:
        """The fuel the mod's smelt_item will pick: one kind, the least burn left over.

        A furnace's fuel slot holds one kind, so the mod burns one kind per
        smelt: the one that covers every smelt with the least waste (a plank
        rather than a whole coal for one raw iron), else the longest-burning
        one for as far as it goes, and coal is missing for the rest. A lava
        bucket leaves its bucket behind, so it is never picked unasked.
        """
        need = plan.smelts
        if need <= 0:
            return
        options = [(name, n, self.fuel[name]) for name, n in inv.items()
                   if n > 0 and self.fuel.get(name, 0) > 0 and name != "lava_bucket"]
        covering = [(math.ceil(need / value) * value - need, -value, name)
                    for name, n, value in options if n * value >= need]
        if covering:
            _, neg_value, name = min(covering)
            plan.fuel[name] = math.ceil(need / -neg_value)
            inv[name] -= plan.fuel[name]
            return
        covered = 0
        if options:
            name, n, value = max(options, key=lambda o: (o[1] * o[2], o[2], o[0]))
            covered = math.floor(n * value)
            if covered > 0:
                plan.fuel[name] = math.ceil(covered / value)
                inv[name] -= plan.fuel[name]
        plan.missing["coal"] = plan.missing.get("coal", 0) + math.ceil((need - covered) / 8)


def _key(version: str) -> Tuple[int, ...]:
    """"26.2" < "26.10"; anything that is not a number sorts first."""
    return tuple(int(p) if p.isdigit() else -1 for p in version.split("."))


def _fork(plan: Plan) -> Plan:
    return Plan(plan.item, plan.count, [], {}, dict(plan.leftovers), {}, 0)


def _adopt(plan: Plan, trial: Plan) -> None:
    plan.steps += trial.steps
    for k, v in trial.missing.items():
        plan.missing[k] = plan.missing.get(k, 0) + v
    plan.leftovers = trial.leftovers
    plan.smelts += trial.smelts


def _merge(steps: List[Step]) -> List[Step]:
    """Two crafts of one recipe become one, at the earlier (already safe) position."""
    merged: Dict[str, Step] = {}
    out: List[Step] = []
    for s in steps:
        first = merged.get(s.recipe)
        if first is None:
            merged[s.recipe] = s
            out.append(s)
            continue
        first.times += s.times
        first.makes += s.makes
        for k, v in s.uses.items():
            first.uses[k] = first.uses.get(k, 0) + v
    return out


def _uses_ore(recipe: Dict[str, Any]) -> int:
    """Mining an ore without silk touch drops the raw item, so prefer recipes on those."""
    return int(any(k.endswith("_ore") for k in recipe["ingredients"]))


def _family(name: str) -> str:
    for wood in ("dark_oak", "pale_oak", "oak", "spruce", "birch", "jungle", "acacia",
                 "mangrove", "cherry", "bamboo", "crimson", "warped"):
        if name.startswith(wood + "_"):
            return wood
    return ""


def describe(plan: Plan, inventory: Dict[str, int]) -> str:
    """The plan as the body reads it."""
    lines: List[str] = []
    if plan.missing:
        lines.append("missing: " + ", ".join(f"{n} {k}" for k, n in plan.missing.items()))
    else:
        lines.append(f"you have everything for {plan.count} {plan.item}")
    for i, s in enumerate(plan.steps, 1):
        uses = " + ".join(f"{n} {k}" for k, n in s.uses.items())
        where = {"3x3": " (crafting table)", "furnace": " (furnace)"}.get(s.grid, "")
        lines.append(f"{i}. {s.kind} {uses} -> {s.makes} {s.item}{where}")
    if plan.needs_table and not inventory.get("crafting_table"):
        lines.append("needs a crafting table: carry one or stand near one")
    if plan.needs_furnace:
        fuel = ", ".join(f"{n} {k}" for k, n in plan.fuel.items()) or "none in inventory"
        lines.append(f"needs a furnace; fuel: {fuel}")
    if plan.leftovers:
        lines.append("left over: " + ", ".join(f"{n} {k}" for k, n in plan.leftovers.items()))
    return "\n".join(lines)
