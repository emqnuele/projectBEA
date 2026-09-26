"""The recipes in the brain: `crafting_plan`, and the plan behind a failed craft.

The mod only knows the recipes she has unlocked, and only one step at a time.
The planner (crafting.py) knows every recipe of the game she is in and walks
the whole chain from what she carries, so this is where "what does a stone
pickaxe take from here" gets answered, instantly, without touching the mod.
"""

import difflib
from typing import Dict, Optional

from src.core.skills.minecraft.client import MinecraftClient
from src.core.skills.minecraft.crafting import Recipes, describe
from src.core.skills.minecraft.state import count_items

PLAN_DESC = (
    "What it takes to make an item from what you carry right now: what is missing, every "
    "craft and smelt in order (with the crafting table or furnace each needs), the fuel, "
    "and what is left over. Instant, and it does not move you. Use it before a craft_item "
    "chain, or when one fails."
)


class RecipeBook:
    """The recipes of the Minecraft version the mod announced, loaded once per version."""

    def __init__(self, client: MinecraftClient):
        self.client = client
        self._version = ""
        self._recipes: Optional[Recipes] = None

    def recipes(self) -> Recipes:
        version = str(getattr(self.client, "mc_version", "") or "")
        if self._recipes is None or version != self._version:
            try:
                self._recipes = Recipes.load(version)
            except FileNotFoundError:
                # a game we have no data for yet, or no handshake: the newest data is the best guess
                self._recipes = Recipes.load(Recipes.supported()[-1])
            self._version = version
        return self._recipes

    def plan(self, item: str, count: int = 1) -> str:
        recipes = self.recipes()
        name = _normalize(item)
        if name not in recipes.recipes and name.endswith("s") and name[:-1] in recipes.recipes:
            name = name[:-1]
        note = self._version_note(recipes)
        if name not in recipes.recipes:
            return note + _unknown(recipes, name)
        inventory: Dict[str, int] = count_items(self.client.latest_state)
        return note + describe(recipes.plan(name, max(1, int(count)), inventory), inventory)

    def _version_note(self, recipes: Recipes) -> str:
        wanted = self._version
        if wanted and wanted != "unknown" and recipes.version != wanted:
            return f"(recipes from Minecraft {recipes.version}; the game is {wanted})\n"
        return ""


def _normalize(item: str) -> str:
    name = str(item or "").strip().lower().replace(" ", "_")
    return name.removeprefix("minecraft:")


def _unknown(recipes: Recipes, name: str) -> str:
    """Nothing makes it: it is gathered, or the name is off."""
    known = set(recipes.recipes)
    for items in recipes.tags.values():
        known.update(items)
    for entries in recipes.recipes.values():
        for recipe in entries:
            for key in recipe["ingredients"]:
                known.update(recipes.options(key))
    if name in known:
        return f"nothing crafts or smelts {name}: it is mined, gathered or dropped."
    close = difflib.get_close_matches(name, sorted(known), n=5, cutoff=0.6)
    hint = f"; did you mean {', '.join(close)}?" if close else "."
    return f"there is no item called {name}{hint}"
