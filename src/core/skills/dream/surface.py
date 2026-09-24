import asyncio
import datetime
import time
from typing import List, Optional

from src.core.agent.tools import Tool
from src.core.mind.handoff import HANDOFF_HEADER
from src.core.persona import persona_of
from src.core.skills.base import Skill
from src.core.skills.dream.dreamer import DAY_SECONDS, Dreamer
from src.core.skills.memory.memory import MemorySkill
from src.core.timeline import now_in_timezone
from src.utils.logger import get_logger

logger = get_logger("bea.skills.dream")

REGULAR_ABSENCE_DAYS = 10

# the date of the last nightly pass, so a restart inside the dreaming hour
# neither skips a night nor doubles one
LAST_NIGHT_KEY = "dream.last_night"

# the date of the last pass of any kind, nap or night: what the dashboard shows.
# Kept apart from the nightly guard, which a nap at 00:30 must not satisfy
LAST_DREAM_KEY = "dream.last_dream"



class DreamSkill(Skill):
    """Sleep and dream: self-knowledge, hot facts, offline consolidation.

    While active her self-lore and a few "right now" facts are always in
    context. `go_to_sleep` runs the dreamer and wakes her up again; the UI can
    trigger the same pass.
    """

    name = "dream"
    skill_name = "dream"

    def initialize(self) -> None:
        memory = self.brain.memory
        self.selflore = memory.selflore
        self.recent = memory.hot
        self.sessions = memory.sessions
        self.dreamer: Optional[Dreamer] = None
        self._dreaming = False
        self._night_task: Optional[asyncio.Task] = None
        # held, not fired and forgotten: the loop keeps only a weak reference,
        # so an unheld dream can be collected in the middle of consolidating
        self._dream_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        await super().start()
        if not self.active:
            return
        self._build_dreamer()
        # morning pass: refresh derived 'right now' facts at wake-up
        try:
            self.morning_pass()
        except Exception as e:
            logger.error(f"DreamSkill: morning pass failed: {e}")
        self._night_task = asyncio.create_task(self._nightly())

    async def stop(self) -> None:
        if self._night_task:
            self._night_task.cancel()
            self._night_task = None
        # a consolidation in progress is writing memory and using the background
        # model pool: left running it would race the final save in `cli.shutdown`
        # and keep a model busy that same shutdown is about to close. Cancelled
        # and consumed here rather than left to the loop's own cancel.
        dream = self._dream_task
        if dream is not None and not dream.done():
            dream.cancel()
            try:
                await dream
            except (asyncio.CancelledError, Exception):
                pass
        self._dream_task = None
        await super().stop()

    async def _nightly(self) -> None:
        """Dreams once a night, on its own.

        The hour is checked rather than a timer set, so a restart neither skips
        a night nor doubles one.
        """
        hour = int(self.config.skills.get("dream", {}).get("hour", 4))
        timezone = str(getattr(self.config, "timezone", "") or "")
        while self.active:
            await asyncio.sleep(300)
            now = now_in_timezone(timezone)
            if now.hour != hour or self._dreamed_tonight(now.date()):
                continue
            self._mark_dreamed_tonight(now.date())
            logger.info("DreamSkill: nightly consolidation starting.")
            try:
                await self.run_dream()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"DreamSkill: nightly dream failed: {e}")

    def _social(self):
        reg = getattr(self.context, "skill_registry", None)
        return reg.get("social") if reg else None

    def _build_dreamer(self) -> None:
        social = self._social()
        # the background pool: a dream pass is dozens of calls in a row and must
        # never take the mind's model (or its rate limit) hostage
        model_for = getattr(self.context, "model_for", None)
        llm = model_for("background") if model_for else None
        hm = getattr(self.context, "history_manager", None)
        if not (social and llm and hm):
            logger.warning("DreamSkill: dreamer not fully wired (need social + llm + history).")
            return
        self.dreamer = Dreamer(
            llm=llm, history_manager=hm,
            roster=social.roster, people=social.people,
            selflore=self.selflore, recent=self.recent, sessions=self.sessions,
            conversations=self.brain.memory.conversations,
            rag=getattr(self.brain.memory, "rag", None),
            persona=persona_of(self.config), language=self.config.language,
            timezone=str(getattr(self.config, "timezone", "") or ""),
        )

    # --- always-in-context --------------------------------------------------

    @property
    def context_section(self) -> Optional[str]:
        if not self.active:
            return None
        lore = self.selflore.render_for_prompt(max_facts=15)
        return f"## ABOUT YOU (your own evolving memory)\n{lore}" if lore else None

    def live_state(self) -> Optional[str]:
        if not self.active:
            return None
        return self.recent.render() or None

    # --- morning pass: derive volatile 'now' facts --------------------------

    def morning_pass(self) -> None:
        self.recent.clear_source("morning_pass")
        ttl = 1.2 * DAY_SECONDS  # refreshed every wake-up

        # 1. birthday countdown (from the structured profile)
        bday = self.selflore.profile().get("birthday")  # "MM-DD"
        timezone = str(getattr(self.config, "timezone", "") or "")
        days = _days_until(bday, timezone) if bday else None
        if days is not None:
            if days == 0:
                self.recent.add("today is your birthday!", ttl, "morning_pass")
            elif days <= 14:
                self.recent.add(f"your birthday is in {days} days", ttl, "morning_pass")

        # 2. how long since last stream
        gap = self._days_since_last_session()
        if gap is not None and gap >= 1:
            self.recent.add(f"you haven't streamed in {gap} day(s)", ttl, "morning_pass")

        # 3. what happened the last time round, from the dream's conversation
        # recaps: she should be able to pick a conversation up, not restart it
        # every day
        for line in self._yesterday():
            self.recent.add(line, ttl, "morning_pass")

        # 4. regulars who've gone missing
        social = self._social()
        if social:
            now = time.time()
            for entry in social.roster.all():
                if not entry.promoted:
                    continue
                away = (now - entry.last_seen) / DAY_SECONDS
                if away >= REGULAR_ABSENCE_DAYS:
                    self.recent.add(
                        f"{entry.display_name} hasn't shown up in {int(away)} days",
                        ttl, "morning_pass",
                    )

    def _yesterday(self, limit: int = 2) -> List[str]:
        """One line per conversation that was going somewhere recently.

        Reads the recaps the dreamer keeps per conversation key, newest first:
        the same thread the consolidation wrote last night is what the morning
        picks back up.
        """
        memory = getattr(self.context, "memory", None)
        if memory is None:
            return []
        try:
            rows = memory.db.query(
                "SELECT scope_key, text FROM memories "
                "WHERE scope = 'conversation' AND text != '' "
                "ORDER BY created_at DESC LIMIT ?", (limit,),
            )
        except Exception as e:
            logger.warning(f"DreamSkill: could not read the recaps: {e}")
            return []
        return [f"last time in {r['scope_key']}: {_first_line(r['text'])}"
                for r in rows]

    def _days_since_last_session(self) -> Optional[int]:
        active = getattr(getattr(self.context, "history_manager", None), "session_id", None)
        last = self.sessions.last_ended_at(exclude=active)
        if last is None:
            return None
        return int((time.time() - last) / DAY_SECONDS)

    # --- sleep & dream ------------------------------------------------------

    def tools(self) -> List[Tool]:
        if not self.active:
            return []
        return [Tool(
            "go_to_sleep",
            "Go to sleep. You stop reacting, your avatar shows you sleeping, and while "
            "you dream you tidy up your memories. Use it when you're tired, bored, or the "
            "stream is winding down.",
            {"type": "object", "properties": {
                "reason": {"type": "string", "description": "why you're going to sleep"}},
             "required": []},
            self._tool_go_to_sleep,
        )]

    async def _tool_go_to_sleep(self, reason: str = "") -> str:
        # falling asleep belongs to `run_dream` alone. Sleeping here and
        # queueing the dream separately meant a request that arrived mid-dream
        # bailed at the guard and then ran a second consolidation the moment
        # the first one released it
        if self._dreaming:
            return "Already asleep, dreaming."
        self._dream_task = asyncio.create_task(self.run_dream(reason or "tired"))
        self._dream_task.add_done_callback(self._dream_finished)
        return "Zzz... going to sleep."

    def _dream_finished(self, task: asyncio.Task) -> None:
        self._dream_task = None
        if not task.cancelled() and task.exception() is not None:
            logger.error(f"DreamSkill: the dream task died: {task.exception()}")

    async def run_dream(self, reason: str = "dreaming") -> dict:
        """Sleep -> consolidate -> refresh hot facts -> wake. Safe to call from UI."""
        if self._dreaming:
            return {"ok": False, "error": "already dreaming"}
        self._dreaming = True
        consc = getattr(self.context, "consciousness", None)
        if consc:
            consc.sleep(reason)
        summary = {"ok": True}
        try:
            if self.dreamer:
                summary = await self.dreamer.run()
                summary["pages"] = await self._write_pages(summary.get("sittings") or [])
                if summary.get("ok"):
                    self._mark_dreamed()
            self._start_over(str(summary.get("carry_over") or ""))
            self.morning_pass()
        except Exception as e:
            logger.error(f"DreamSkill: dream failed: {e}")
            summary = {"ok": False, "error": str(e)}
        finally:
            self._dreaming = False
            if consc:
                consc.wake()
        return summary

    async def _write_pages(self, session_ids: List[str]) -> int:
        """The diary phase: a page for every sitting the pass read.

        Before waking, so the rotation in `_start_over` finds the page of the
        sitting she slept in already written and has nothing left to queue.
        """
        reg = getattr(self.context, "skill_registry", None)
        memory = reg.get("memory") if reg else None
        if not session_ids or not isinstance(memory, MemorySkill):
            return 0
        try:
            return await memory.write_pages(session_ids)
        except Exception as e:
            logger.error(f"DreamSkill: the diary phase failed: {e}")
            return 0

    def _start_over(self, carry_over: str = "") -> None:
        """A new session and an empty window: waking up is the one reset.

        This is the only place the window is emptied. Everything in it has
        just been consolidated into cards, self-lore and the diary, so what
        she needs from the evening is what the pass said to carry — not the
        evening itself, replayed verbatim into a fresh morning.
        """
        rotate = getattr(self.context, "create_new_session", None)
        if callable(rotate):
            try:
                rotate()
            except Exception as e:
                logger.error(f"DreamSkill: could not start a new session: {e}")

        consc = getattr(self.context, "consciousness", None)
        forget = getattr(consc, "forget_window", None)
        if callable(forget):
            forget(f"{HANDOFF_HEADER}\n{carry_over}" if carry_over else "")

    # --- once a night, across restarts --------------------------------------

    def _dreamed_tonight(self, today: Optional[datetime.date] = None) -> bool:
        """Whether tonight's pass already ran.

        On disk rather than in a local: the hour is checked every five minutes,
        so a restart at 4:30 used to find an empty variable and dream the same
        night a second time.
        """
        if today is None:
            today = now_in_timezone(str(getattr(self.config, "timezone", "") or "")).date()
        return self._last_night() == today.isoformat()

    def _mark_dreamed_tonight(self, today: Optional[datetime.date] = None) -> None:
        if today is None:
            today = now_in_timezone(str(getattr(self.config, "timezone", "") or "")).date()
        memory = getattr(self.context, "memory", None)
        if memory is None:
            return
        memory.db.put_setting(LAST_NIGHT_KEY, today.isoformat())

    def _mark_dreamed(self) -> None:
        """Every pass, not only the nightly one: a nap is a dream too."""
        memory = getattr(self.context, "memory", None)
        if memory is None:
            return
        today = now_in_timezone(str(getattr(self.config, "timezone", "") or "")).date()
        memory.db.put_setting(LAST_DREAM_KEY, today.isoformat())

    def last_night(self) -> str:
        """The date of the last consolidation pass, `""` when she never dreamt."""
        memory = getattr(self.context, "memory", None)
        dreamt = str(memory.db.get_setting(LAST_DREAM_KEY)) if memory is not None else ""
        # both are ISO dates, so the later one is the larger string
        return max(dreamt, self._last_night())

    def _last_night(self) -> str:
        memory = getattr(self.context, "memory", None)
        if memory is None:
            return ""
        return str(memory.db.get_setting(LAST_NIGHT_KEY))


def _first_line(text: str, limit: int = 120) -> str:
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _days_until(mm_dd: str, timezone: str = "") -> Optional[int]:
    try:
        month, day = [int(x) for x in mm_dd.split("-")]
        today = now_in_timezone(timezone).date()
        target = datetime.date(today.year, month, day)
        if target < today:
            target = datetime.date(today.year + 1, month, day)
        return (target - today).days
    except Exception:
        return None
