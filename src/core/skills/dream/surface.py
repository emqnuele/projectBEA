import asyncio
import datetime
import time
from typing import List, Optional

from src.core.agent.tools import Tool
from src.core.skills.base import Skill
from src.core.skills.dream.dreamer import DAY_SECONDS, Dreamer
from src.utils.logger import get_logger

logger = get_logger("bea.skills.dream")

REGULAR_ABSENCE_DAYS = 10


class DreamSkill(Skill):
    """Sleep and dream: self-knowledge, hot facts, offline consolidation.

    While active her self-lore and a few "right now" facts are always in
    context. `go_to_sleep` runs the dreamer and wakes her up again; the UI can
    trigger the same pass.
    """

    name = "dream"
    skill_name = "dream"

    def initialize(self) -> None:
        memory = self.context.memory
        self.selflore = memory.selflore
        self.recent = memory.hot
        self.sessions = memory.sessions
        self.dreamer: Optional[Dreamer] = None
        self._dreaming = False
        self._night_task: Optional[asyncio.Task] = None

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
        await super().stop()

    async def _nightly(self) -> None:
        """Dreams once a night, on its own.

        The hour is checked rather than a timer set, so a restart neither skips
        a night nor doubles one.
        """
        hour = int(self.config.skills.get("dream", {}).get("hour", 4))
        last_dreamed_on = None
        while self.active:
            await asyncio.sleep(300)
            now = datetime.datetime.now()
            if now.hour != hour or last_dreamed_on == now.date():
                continue
            last_dreamed_on = now.date()
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
        days = _days_until(bday) if bday else None
        if days is not None:
            if days == 0:
                self.recent.add("today is your birthday!", ttl, "morning_pass")
            elif days <= 14:
                self.recent.add(f"your birthday is in {days} days", ttl, "morning_pass")

        # 2. how long since last stream
        gap = self._days_since_last_session()
        if gap is not None and gap >= 1:
            self.recent.add(f"you haven't streamed in {gap} day(s)", ttl, "morning_pass")

        # 3. what happened the last time round, from the rolling summaries: she
        # should be able to pick a conversation up, not restart it every day
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
        """One line per conversation that was going somewhere recently."""
        memory = getattr(self.context, "memory", None)
        if memory is None:
            return []
        try:
            rows = memory.db.query(
                "SELECT conversation_key, summary FROM summaries "
                "WHERE summary != '' ORDER BY updated_at DESC LIMIT ?", (limit,),
            )
        except Exception as e:
            logger.warning(f"DreamSkill: could not read the summaries: {e}")
            return []
        return [f"last time in {r['conversation_key']}: {_first_line(r['summary'])}"
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
        consc = getattr(self.context, "consciousness", None)
        if consc:
            consc.sleep(reason or "tired")
        asyncio.create_task(self.run_dream())
        return "Zzz... going to sleep."

    async def run_dream(self) -> dict:
        """Sleep -> consolidate -> refresh hot facts -> wake. Safe to call from UI."""
        if self._dreaming:
            return {"ok": False, "error": "already dreaming"}
        self._dreaming = True
        consc = getattr(self.context, "consciousness", None)
        if consc and not consc.sleeping:
            consc.sleep("dreaming")
        summary = {"ok": True}
        try:
            if self.dreamer:
                summary = await self.dreamer.run()
            self.morning_pass()
        except Exception as e:
            logger.error(f"DreamSkill: dream failed: {e}")
            summary = {"ok": False, "error": str(e)}
        finally:
            self._dreaming = False
            if consc:
                consc.wake()
        return summary


def _first_line(text: str, limit: int = 120) -> str:
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _days_until(mm_dd: str) -> Optional[int]:
    try:
        month, day = [int(x) for x in mm_dd.split("-")]
        today = datetime.date.today()
        target = datetime.date(today.year, month, day)
        if target < today:
            target = datetime.date(today.year + 1, month, day)
        return (target - today).days
    except Exception:
        return None
