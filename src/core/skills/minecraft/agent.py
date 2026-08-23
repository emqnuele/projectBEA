"""The body, pursuing a goal on its own.

Before this, the mind drove the game tick by tick: every `FINISHED: SUCCESS`,
every state JSON, every failed pathfind landed in the same context as the
conversation. On a server with people talking, her personality drowned in game
logs — and she was spending her reasoning on where to put her feet.

So the mind decides an **intention** and the body pursues it. The body gets the
survival guide, the crafting chains and all twenty-odd game tools; the mind gets
seven tools and the milestones that are actually worth hearing about.

It runs on the `background` model on purpose: figuring out that a pickaxe needs
sticks is not what her good model is for, and it must never compete with the
part of her that talks to people.
"""

import asyncio
import json
import time
from typing import Any, Callable, Dict, List, Optional

from src.core.agent.runner import AgentHooks, AgentRunner
from src.core.skills.minecraft.state import render_state
from src.utils.logger import get_logger
from src.utils.prompts import compose

logger = get_logger("bea.skills.minecraft.agent")

# how many think→act→observe cycles one goal gets before it reports back. A goal
# that has not landed in this many steps is stuck, and saying so is more useful
# than grinding on.
MAX_STEPS = 24

# how often the body re-reads the world, in steps
REFRESH_EVERY = 3

OnMilestone = Callable[[str], None]


class GameAgent:
    """Pursues one goal at a time using the game tools and the notebook."""

    def __init__(self, *, llm, registry, notebook, state_getter,
                 rules: str = "", on_milestone: Optional[OnMilestone] = None,
                 max_steps: int = MAX_STEPS):
        self.llm = llm
        self.registry = registry
        self.notebook = notebook
        self._state = state_getter
        self.rules = rules
        self.on_milestone = on_milestone
        self.max_steps = max_steps

        self.goal: str = ""
        self.started_at: float = 0.0
        self._task: Optional[asyncio.Task] = None

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    def describe(self) -> str:
        """One line for the mind's context: what the body is doing right now."""
        if not self.busy:
            return ""
        elapsed = int(time.time() - self.started_at)
        return f"working on: {self.goal} ({elapsed}s so far)"

    # --- running a goal -----------------------------------------------------

    async def pursue(self, goal: str) -> str:
        """Runs `goal` to completion (or exhaustion) and reports one line back."""
        goal = (goal or "").strip()
        if not goal:
            return "You didn't say what you wanted."

        self.goal = goal
        self.started_at = time.time()
        logger.info(f"GameAgent: pursuing '{goal}'")

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": self._frame(goal, first=True)},
        ]

        runner = AgentRunner(
            self.llm, tools=self.registry, max_steps=self.max_steps,
            hooks=AgentHooks(on_tool_result=self._observe),
        )
        try:
            final = await runner.run(messages)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"GameAgent failed on '{goal}': {e}")
            return f"Your body gave up on '{goal}': {e}"

        report = (final.content or "").strip()
        return report or f"Your body stopped working on '{goal}'."

    def _system_prompt(self) -> str:
        return compose(self.rules, "GOAL FROM BEA: " + self.goal)

    def _frame(self, goal: str, first: bool = False) -> str:
        parts = [f"GOAL: {goal}"]
        state = render_state(self._state())
        if state:
            parts.append("GAME STATE:\n" + state)
        parts.append("YOUR NOTEBOOK:\n" + self.notebook.render())
        if first:
            parts.append("Write or update the notebook first, then start.")
        return "\n\n".join(parts)

    # --- milestones ---------------------------------------------------------

    def _observe(self, name: str, observation: str) -> None:
        """Decides whether an observation is worth interrupting her for.

        Almost none are. She does not need to hear that a pathfind succeeded —
        she needs to hear when something was finished, or went badly wrong.
        """
        if self.on_milestone is None:
            return
        text = str(observation or "")
        if name == "update_notebook":
            return

        if text.startswith("INTERRUPTED") or "died" in text.lower():
            self.on_milestone(f"your body was interrupted: {_clip(text)}")
        elif name in _MILESTONE_TOOLS and text.startswith("SUCCESS"):
            self.on_milestone(f"your body finished {name}: {_clip(text)}")
        elif text.startswith("FAILURE") and name in _MILESTONE_TOOLS:
            self.on_milestone(f"your body couldn't {name}: {_clip(text)}")


# tools whose outcome is a real step forward (or a real setback). Movement and
# looking are means, not results: she does not need to hear about them.
_MILESTONE_TOOLS = frozenset({
    "craft_item", "smelt_item", "find_block", "mine_block", "place_block",
    "equip_item", "store_item", "retrieve_item", "attack_entity", "give_item",
})


def _clip(text: str, limit: int = 120) -> str:
    text = " ".join(str(text).split())
    if len(text) > limit:
        return text[: limit - 1] + "…"
    # observations are sometimes json blobs; the useful half is usually the message
    try:
        data = json.loads(text)
        return str(data.get("message", text)) if isinstance(data, dict) else text
    except (ValueError, TypeError):
        return text
