"""Where she is in time, contributed like any other awareness.

A skill rather than plumbing: `live_state()` is already collected into every
system message, so this needs no wiring beyond being registered. Core and
always on — not knowing what day it is was never a capability to toggle.
"""

import time
from datetime import datetime
from typing import Optional

from src.core.skills.base import Skill
from src.core.timeline import now_block, resolve_timezone


class ClockSkill(Skill):
    """Tells her the day, the time, and how long she has been up."""

    name = "clock"
    skill_name = None  # core: always on

    @property
    def _timezone(self) -> str:
        return str(getattr(self.config, "timezone", "") or "")

    def now(self) -> datetime:
        return datetime.now(resolve_timezone(self._timezone))

    def _awake_seconds(self) -> Optional[float]:
        memory = getattr(self.context, "memory", None)
        history = getattr(self.context, "history_manager", None)
        session = getattr(history, "session_id", None)
        if memory is None:
            return None
        try:
            started = memory.sessions.started_at(session) if session else None
            if started is None:
                started = memory.db.scalar("SELECT MAX(started_at) FROM sessions", default=None)
            return None if started is None else time.time() - float(started)
        except Exception:
            # not knowing how long she has been up must never cost her the clock
            return None

    def live_state(self) -> Optional[str]:
        if not self.active:
            return None
        return now_block(
            self.now(),
            awake_seconds=self._awake_seconds(),
            timezone=self._timezone,
        )
