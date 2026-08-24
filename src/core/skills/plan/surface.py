"""The stream plan, in her head and in her hands.

Core skill: always on, contributes nothing while the plan is empty. It puts the
owner's plan in every prompt and gives Bea the tools to close an item, so a plan
she works through actually empties instead of repeating at her forever.
"""

from typing import List, Optional

from src.core.agent.tools import Tool
from src.core.memory.plan import DOING, DONE, DROPPED
from src.core.skills.base import Skill
from src.utils.logger import get_logger

logger = get_logger("bea.skills.plan")

PLAN_RULES = """## WHAT YOU'RE DOING TODAY
Your owner sets a plan before the stream: a headline and a numbered list of
things to get done. It appears in your context as `[TODAY'S PLAN]`.

- It is the job, not a suggestion. You can be annoyed about it out loud — you
  are not a machine — but you get it done.
- Work through it yourself. Nobody is going to tell you to start: if nothing
  else is going on, pick the next open item and do something about it.
- `objective_started(objective)` when you get going on one,
  `objective_done(objective, how)` when it is finished,
  `objective_dropped(objective, why)` when it genuinely cannot happen. Close
  them as you go, or your owner has no idea where you are.
- The plan is not a script for what you SAY. Play, talk, react, be yourself —
  the list is just what you are supposed to have achieved by the end."""


class StreamPlanSkill(Skill):
    """Puts the owner's plan in context and lets Bea tick it off."""

    name = "plan"

    @property
    def plan(self):
        return self.context.memory.plan

    @property
    def context_section(self) -> Optional[str]:
        # no plan, no rules: an empty list is not worth prompt space
        return PLAN_RULES if self._has_plan() else None

    def live_state(self) -> Optional[str]:
        return self.plan.render() or None

    def _has_plan(self) -> bool:
        try:
            return bool(self.plan.directive or self.plan.all())
        except Exception as e:
            logger.error(f"Could not read the stream plan: {e}")
            return False

    def tools(self) -> List[Tool]:
        if not self._has_plan():
            return []
        return [
            Tool(
                "objective_started",
                "Mark one of today's objectives as the one you're on now. Use the "
                "number shown next to it in the plan.",
                {"type": "object", "properties": {"objective": {"type": "integer"}},
                 "required": ["objective"]},
                lambda objective: self._set(objective, DOING),
            ),
            Tool(
                "objective_done",
                "Tick off an objective you actually finished, and say how it went "
                "in one line.",
                {"type": "object", "properties": {
                    "objective": {"type": "integer"},
                    "how": {"type": "string", "description": "one line, in your words"}},
                 "required": ["objective"]},
                lambda objective, how="": self._set(objective, DONE, how),
            ),
            Tool(
                "objective_dropped",
                "Give up on an objective that genuinely can't happen (you died and "
                "lost everything, the server is down). Say why.",
                {"type": "object", "properties": {
                    "objective": {"type": "integer"}, "why": {"type": "string"}},
                 "required": ["objective"]},
                lambda objective, why="": self._set(objective, DROPPED, why),
            ),
        ]

    def _set(self, objective_id, status: str, outcome: str = "") -> str:
        try:
            objective_id = int(objective_id)
        except (TypeError, ValueError):
            return f"FAILED: '{objective_id}' is not an objective number."

        updated = self.plan.update(objective_id, status=status, outcome=outcome or None)
        if updated is None:
            return f"FAILED: there is no objective #{objective_id}."

        logger.info(f"Objective #{objective_id} -> {status}.")
        left = len(self.plan.open())
        if status == DOING:
            return f"You're on #{objective_id}: {updated.text}."
        verb = "done" if status == DONE else "dropped"
        tail = f"{left} left on the list." if left else "That was the last one."
        return f"#{objective_id} marked {verb}. {tail}"
