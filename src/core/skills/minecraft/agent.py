"""The body, playing on its own for as long as the skill is on.

The mind decides an intention and the body pursues it: the body gets the
survival guide and all twenty-odd game tools, the mind gets seven and the
milestones worth hearing about.

It is one loop that never ends. It used to be a run of twenty-four steps that
finished and left her standing in a field until somebody told her to start
again — which made her the thing keeping her own body alive. Now the loop is
always there: idle and free when it has no goal, working when it has one, and
the only thing she supplies is what the goal should be.
"""

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional

from src.core.agent.messages import assistant_to_message, tool_result_message
from src.core.skills.minecraft.context import KEEP_ROUNDS, BodyContext
from src.core.skills.minecraft.goal import ABANDONED, DONE, RUNNING, STUCK, SUSPENDED, Goal
from src.core.skills.minecraft.state import render_state
from src.utils.logger import get_logger
from src.utils.prompts import compose

logger = get_logger("bea.skills.minecraft.agent")

# think->act->observe rounds one goal may spend before the body admits it is
# not getting there. It does not end the loop — it hands the problem back to her
STEPS_PER_GOAL = 40

# how often the body re-reads the world, in steps. Everything between is tool
# observations, which say what happened and not where it left her
REFRESH_EVERY = 3

# rounds ending badly, back to back, that mean it is failing the same way
MAX_FAILURES = 5

# breathing room between two rounds. Most of the pacing is the game itself —
# mining a block takes seconds and the body waits for it — and this is what
# stops a goal made only of instant tools from becoming a spin
TICK_SECONDS = 0.4

# the body's own words, kept short: this is a line she reads out, not a log
THOUGHT_LIMIT = 220

# the one game-state note in the window; a new one replaces it
STATE_TAG = "state"

OnMilestone = Callable[[str], None]
OnGoalClosed = Callable[[Goal], None]

_DONE_DESC = (
    "The goal is achieved — hand it back to her. `summary` is the one line she hears, "
    "so make it factual and worth reading. Call it the moment it is true."
)
_BLOCKED_DESC = (
    "You cannot get there, and `reason` says why. For the world being in the way — no "
    "iron anywhere, you keep dying to the same thing — not for one attempt that failed. "
    "She decides what happens next."
)


class GameAgent:
    """Plays, continuously, in the direction of whatever goal it was given."""

    def __init__(self, *, llm, registry, notebook, state_getter,
                 rules: str = "", on_milestone: Optional[OnMilestone] = None,
                 on_goal_closed: Optional[OnGoalClosed] = None,
                 steps_per_goal: int = STEPS_PER_GOAL,
                 tick_seconds: float = TICK_SECONDS,
                 keep_rounds: int = KEEP_ROUNDS,
                 refresh_every: int = REFRESH_EVERY):
        self.llm = llm
        self.registry = registry
        self.notebook = notebook
        self._state = state_getter
        self.rules = rules
        self.on_milestone = on_milestone
        self.on_goal_closed = on_goal_closed
        self.steps_per_goal = max(1, int(steps_per_goal))
        self.tick_seconds = max(0.0, float(tick_seconds))
        self.refresh_every = max(0, int(refresh_every))

        self.goal: Optional[Goal] = None
        self.last_thought: str = ""
        self.ctx = BodyContext(keep_rounds)

        self._loop_task: Optional[asyncio.Task] = None
        self._step_task: Optional[asyncio.Task] = None
        self._work = asyncio.Event()
        self._stopping = False
        # how many things the mind is doing with the body right now; the goal
        # resumes when the last of them gives it back
        self._borrowed = 0

        self._arm_goal_tools()

    def _arm_goal_tools(self) -> None:
        """The two ways a goal ends, as tools it has to reach for.

        Ending used to mean the model happening not to call anything, which is
        also what a model does when it is confused, has nothing to say, or
        answers in prose. Those are not the same event and the mind was being
        told they were.
        """
        self.registry.add(
            "goal_done", _DONE_DESC,
            {"type": "object", "properties": {"summary": {"type": "string"}},
             "required": ["summary"]},
            self._tool_done)
        self.registry.add(
            "goal_blocked", _BLOCKED_DESC,
            {"type": "object", "properties": {"reason": {"type": "string"}},
             "required": ["reason"]},
            self._tool_blocked)

    def _tool_done(self, summary: str = "") -> str:
        return self._declare(DONE, summary)

    def _tool_blocked(self, reason: str = "") -> str:
        return self._declare(STUCK, reason)

    # --- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        if self._loop_task is None or self._loop_task.done():
            self._stopping = False
            self._loop_task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stopping = True
        self._cancel_step()
        task, self._loop_task = self._loop_task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def run(self) -> None:
        """Idle when there is nothing to do, one round at a time when there is."""
        while not self._stopping:
            goal = self.goal
            if goal is None or goal.status != RUNNING:
                self._work.clear()
                await self._work.wait()
                continue

            try:
                self._step_task = asyncio.create_task(self._step(goal))
                await self._step_task
            except asyncio.CancelledError:
                # the loop itself going down, or the mind taking the body for
                # something of its own. Only the first one is the end
                if self._stopping:
                    raise
                continue
            except Exception as e:
                logger.error(f"The body's round failed: {e}", exc_info=True)
                goal.failures += 1
                self.ctx.observe(f"Your last round went wrong: {e}. Try another way.")
                self._check_health(goal)
            finally:
                self._step_task = None

            if self.tick_seconds:
                await asyncio.sleep(self.tick_seconds)

    # --- direction from the mind -------------------------------------------

    def set_goal(self, text: str) -> str:
        """She decided what the body should be doing. Takes effect immediately."""
        text = (text or "").strip()
        if not text:
            return "You didn't say what you wanted."

        previous = self.goal
        if previous is not None and previous.open:
            previous.status = ABANDONED
            logger.info(f"GameAgent: dropping '{previous.text}' for '{text}'")

        self.goal = Goal(text=text)
        self.last_thought = ""
        self.ctx.start(self._mission(self.goal))
        self._cancel_step()
        self._work.set()
        logger.info(f"GameAgent: pursuing '{text}'")
        was = f" (it was on: {previous.text})" if previous is not None and previous.text else ""
        return f"Your body is on it: {text}.{was}"

    def clear_goal(self, why: str = "she called it off") -> str:
        goal = self.goal
        if goal is None or not goal.open:
            return "Your body was already standing still."
        goal.status = ABANDONED
        goal.outcome = why
        self._cancel_step()
        logger.info(f"GameAgent: '{goal.text}' called off ({why})")
        return f"Your body stopped: {goal.text}."

    # --- the mind using the body for something of its own -------------------

    def borrow(self) -> None:
        """A reflex of hers takes the body: the goal waits rather than dying.

        It used to be cancelled outright, which is why looking at somebody who
        said hello cost her the house she was building.
        """
        self._borrowed += 1
        goal = self.goal
        if goal is not None and goal.status == RUNNING:
            goal.status = SUSPENDED
        self._cancel_step()

    def give_back(self, why: str = "") -> None:
        self._borrowed = max(0, self._borrowed - 1)
        if self._borrowed:
            return
        goal = self.goal
        if goal is None or goal.status != SUSPENDED:
            return
        goal.status = RUNNING
        note = f"You were taken off this for a moment{f' ({why})' if why else ''}."
        self.ctx.observe(f"{note} Re-read the state and carry on where you left off.")
        self._work.set()

    # --- what she can see ---------------------------------------------------

    @property
    def busy(self) -> bool:
        goal = self.goal
        return goal is not None and goal.open

    def describe(self) -> str:
        """One line for the mind's context: what the body is doing right now."""
        goal = self.goal
        if goal is None or not goal.open:
            return ""
        return goal.describe(self.steps_per_goal)

    def snapshot(self) -> Dict[str, Any]:
        """What the dashboard shows, in the shape it shows it."""
        goal = self.goal
        return {
            "goal": goal.text if goal else "",
            "status": goal.status if goal else "idle",
            "steps": goal.steps if goal else 0,
            "steps_budget": self.steps_per_goal,
            "elapsed": round(goal.elapsed, 1) if goal else 0.0,
            "outcome": goal.outcome if goal else "",
            "thought": self.last_thought,
            "notebook": self.notebook.content,
        }

    # --- one round ----------------------------------------------------------

    async def _step(self, goal: Goal) -> None:
        if goal.steps == 0 or (self.refresh_every and goal.steps % self.refresh_every == 0):
            self.ctx.observe(self._state_note(), tag=STATE_TAG)

        goal.steps += 1
        reply = await self.llm.complete(
            self.ctx.messages(self._system(goal)),
            tools=self.registry.schemas() or None,
        )

        if reply.content:
            self._think(reply.content)

        if not reply.tool_calls:
            # prose is the body talking to itself; the game heard none of it
            goal.failures += 1
            self.ctx.add_round(assistant_to_message(reply))
            self.ctx.observe(
                "[NOTHING HAPPENED — you wrote that instead of doing it. You act by "
                "calling tools. Call one now, or goal_done/goal_blocked if there is "
                "nothing left to do.]")
            self._check_health(goal)
            return

        results: List[Dict[str, Any]] = []
        bad = 0
        for call in reply.tool_calls:
            observation = await self.registry.dispatch(call)
            self._watch(call.name, observation)
            results.append(tool_result_message(call, observation))
            if _went_wrong(observation):
                bad += 1
        self.ctx.add_round(assistant_to_message(reply), results)

        if goal.status in (DONE, STUCK):
            return  # it said so itself, through goal_done / goal_blocked

        # one bad step is the game; every call in a row going wrong is a body
        # doing the same impossible thing and calling it progress
        goal.failures = goal.failures + 1 if bad == len(reply.tool_calls) else 0
        self._check_health(goal)

    def _declare(self, status: str, text: str) -> str:
        goal = self.goal
        if goal is None:
            return "There was no goal to close."
        self._close(goal, status, text)
        return "Noted — she has been told." if status == DONE else "Noted — she will pick it up."

    def _check_health(self, goal: Goal) -> None:
        if goal.failures >= MAX_FAILURES:
            self._close(goal, STUCK,
                        f"the same thing kept failing ({goal.failures} rounds in a row)")
        elif goal.steps >= self.steps_per_goal:
            self._close(goal, STUCK,
                        f"ran out of room after {goal.steps} steps without getting there")

    def _close(self, goal: Goal, status: str, outcome: str) -> None:
        goal.status = status
        goal.outcome = " ".join(str(outcome or "").split()) or (
            "finished" if status == DONE else "could not get there")
        logger.info(f"GameAgent: '{goal.text}' -> {status} ({goal.outcome})")
        if self.on_goal_closed is not None:
            try:
                self.on_goal_closed(goal)
            except Exception as e:
                logger.error(f"Telling her the goal closed failed: {e}")

    # --- prompts ------------------------------------------------------------

    def _system(self, goal: Goal) -> str:
        return compose(self.rules, "GOAL FROM BEA: " + goal.text)

    def _mission(self, goal: Goal) -> str:
        return (f"GOAL: {goal.text}\n\n"
                "Write or update your notebook first, then start. Call goal_done when "
                "you have it, goal_blocked when you genuinely cannot.")

    def _state_note(self) -> str:
        parts = ["GAME STATE (now):\n" + (render_state(self._state()) or "(nothing to see)")]
        parts.append("YOUR NOTEBOOK:\n" + self.notebook.render())
        return "\n\n".join(parts)

    # --- what the mind can hear --------------------------------------------

    def _think(self, content: str) -> None:
        """The body reasoning out loud, kept for whoever asks what it is doing.

        Not pushed anywhere: a thought per step would be a stream of interrupts.
        The surface reads the freshest one when it decides she should comment.
        """
        text = " ".join(str(content or "").split())
        if text:
            self.last_thought = _clip(text, THOUGHT_LIMIT)

    def _watch(self, name: str, observation: str) -> None:
        """Is this observation worth interrupting her for?

        Almost none are: she needs to hear what was finished or went badly
        wrong, not that a pathfind succeeded.
        """
        if self.on_milestone is None:
            return
        text = str(observation or "")
        if name in ("update_notebook", "goal_done", "goal_blocked"):
            return  # the first is private, the other two reach her whole

        if text.startswith("INTERRUPTED") or "died" in text.lower():
            self.on_milestone(f"your body was interrupted: {_clip(text)}")
        elif name in _MILESTONE_TOOLS and text.startswith("SUCCESS"):
            self.on_milestone(f"your body finished {name}: {_clip(text)}")
        elif text.startswith("FAILURE") and name in _MILESTONE_TOOLS:
            self.on_milestone(f"your body couldn't {name}: {_clip(text)}")

    def _cancel_step(self) -> None:
        task, self._step_task = self._step_task, None
        if task is not None and not task.done():
            task.cancel()


# tools whose outcome is a real step forward or setback; moving and looking are
# means, not results
_MILESTONE_TOOLS = frozenset({
    "craft_item", "smelt_item", "find_block", "mine_block", "place_block",
    "equip_item", "store_item", "retrieve_item", "attack_entity", "give_item",
})

_BAD = ("FAILURE", "FAILED", "ERROR", "TIMEOUT", "INTERRUPTED")


def _went_wrong(observation: str) -> bool:
    return str(observation or "").lstrip().upper().startswith(_BAD)


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
