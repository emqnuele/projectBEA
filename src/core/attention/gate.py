"""Attention: what matters most right now, ordered — never filtered.

One loop, one context: every perception reaches the mind in the same frame,
sorted by the priority `annotate` assigns. Addressed and follow-up always 1.0;
everything else is the raw score clamped to [0, 1]. The model itself decides
what deserves an answer — there is no threshold, no dice, no digest buffer, no
second regime.

State lives here (activity counters, when she last spoke per key); the
decisions live in `rules.py` and stay pure. `clock` is injected so the whole
thing is deterministic under test. The follow-up question ("are they answering
me") reads the tagged entries of the one sliding window, never SQLite.
"""

import time
from collections import deque
from datetime import datetime
from typing import Callable, Deque, Dict, List, Optional, Sequence, Tuple

from src.core.attention.followup import Turn, is_followup
from src.core.attention.rules import is_addressed, score
from src.core.mind.routing import conversation_key
from src.core.perception.types import Perception, PerceptionKind
from src.core.persona import persona_of
from src.utils.logger import get_logger

logger = get_logger("bea.attention")

# window over which "how alive is this surface" is measured
ACTIVITY_WINDOW_SECONDS = 120.0

# the bucket for "wherever she is", as opposed to one specific conversation
ANYWHERE = "*"


class Attention:
    """Assigns a priority to every perception. Nothing is ever dropped here."""

    def __init__(
        self,
        config,
        roster=None,
        *,
        clock: Optional[Callable[[], float]] = None,
        window=None,
    ) -> None:
        self.config = config
        self.roster = roster
        self.window = window
        self._clock = clock or time.time

        # keyed by conversation, not by surface: all discord channels share one
        # surface, and a busy channel must not drag her into a quiet one
        self._activity: Dict[str, Deque[float]] = {}
        self._last_spoke: Dict[str, float] = {}

    # --- config -------------------------------------------------------------

    @property
    def _cfg(self) -> dict:
        return getattr(self.config, "attention", {}) or {}

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.get("enabled", True))

    @property
    def trigger_words(self) -> Sequence[str]:
        # derived from her name unless someone set them explicitly
        return persona_of(self.config).trigger_words

    @property
    def hot_names(self) -> Sequence[str]:
        return list(self.trigger_words) + list(self._cfg.get("hot_names", []))

    @property
    def cooldown(self) -> float:
        return float(self._cfg.get("cooldown_seconds", 20.0))

    @property
    def voice_cooldown(self) -> float:
        """The one for a live call, where 20 seconds is an eternity.

        In chat a pause between her turns reads as restraint. In a call it reads
        as absence: by the time the general cooldown lets her back in, the
        conversation she could have joined is two topics further on.
        """
        return float(self._cfg.get("voice_cooldown_seconds", 5.0))

    def cooldown_for(self, p: Perception) -> float:
        return self.voice_cooldown if p.kind is PerceptionKind.VOICE else self.cooldown

    @property
    def followup_enabled(self) -> bool:
        return bool(self._cfg.get("followup_enabled", True))

    @property
    def quiet_hours(self) -> Tuple[int, int]:
        q = self._cfg.get("quiet_hours", [3, 9])
        return int(q[0]), int(q[1])

    # --- the priority -------------------------------------------------------

    def annotate(self, batch: List[Perception]) -> List[Tuple[Perception, float]]:
        """Priority per perception, deterministic: no threshold, no dice.

        Addressed and follow-up always 1.0; everything else is the raw score
        clamped to [0, 1]. The single loop orders the frame by it instead of
        dropping the quiet half of the room.
        """
        out: List[Tuple[Perception, float]] = []
        for p in batch:
            self._record_activity(p)
            reason = is_addressed(
                p, trigger_words=self.trigger_words, self_ids=self._cfg.get("self_ids", [])
            )
            if reason:
                out.append((p, 1.0))
                continue
            if self._is_followup(p, self._key(p)):
                out.append((p, 1.0))
                continue
            base = score(
                salience=p.salience,
                text=p.content,
                author_known=self._author_known(p),
                author_promoted=self._author_promoted(p),
                donation=self._donation(p),
                hot_names=self.hot_names,
                seconds_since_spoke=self.seconds_since_spoke(self._key(p)),
                recent_activity=self.activity(self._key(p)),
                hour=self._hour(),
                quiet=self.quiet_hours,
                cooldown_seconds=self.cooldown_for(p),
            )
            out.append((p, max(0.0, min(1.0, base))))
        # highest priority first: what pulls hardest is read first
        out.sort(key=lambda item: item[1], reverse=True)
        return out

    def _is_followup(self, p: Perception, key: str) -> bool:
        """Is this person answering something she said to them?

        Deterministic and cooldown-free on purpose: see `followup.py`. Reads
        the tagged entries of the one window — never SQLite.
        """
        if not self.followup_enabled or self.window is None or p.author is None:
            return False
        conversation = conversation_key(p)
        try:
            raw = self.window.turns_for(
                conversation, limit=int(self._cfg.get("followup_lookback", 30)))
            history = [Turn(role=t["role"], identity=t["identity"],
                            addressee=t["addressee"], content=t["content"]) for t in raw]
            since = self.window.seconds_since_bea(conversation, now=self._clock())
            activity = self.window.activity_count(conversation, now=self._clock())
        except Exception as e:
            logger.debug(f"follow-up lookup failed for '{conversation}': {e}")
            return False

        return is_followup(
            history,
            identity=p.author.identity,
            seconds_since_bea=since,
            recent_activity=activity,
            window_seconds=float(self._cfg.get("followup_window_seconds", 180)),
            max_turns=int(self._cfg.get("followup_max_turns", 3)),
            max_interposed=int(self._cfg.get("followup_max_interposed", 3)),
            active_bonus=int(self._cfg.get("followup_active_bonus", 5)),
            trigger_words=self.trigger_words,
        )

    # --- state --------------------------------------------------------------

    def mark_spoke(self, key: str = ANYWHERE) -> None:
        """She just said something. `key` scopes it to one conversation.

        A written reply records only under its key: typing in one channel is not
        a reason to go quiet everywhere. Speaking on stage is, so it lands on
        ANYWHERE, which every key without its own stamp falls back to.
        """
        if key in self._last_spoke:
            del self._last_spoke[key]
        self._last_spoke[key] = self._clock()
        if len(self._last_spoke) > 1000:
            self._last_spoke.pop(next(iter(self._last_spoke)))

    def seconds_since_spoke(self, key: str = ANYWHERE) -> Optional[float]:
        stamp = self._last_spoke.get(key, self._last_spoke.get(ANYWHERE))
        return None if stamp is None else self._clock() - stamp

    def activity(self, key: str) -> int:
        """How many perceptions this conversation produced in the recent window."""
        stamps = self._activity.get(key)
        if not stamps:
            return 0
        cutoff = self._clock() - ACTIVITY_WINDOW_SECONDS
        while stamps and stamps[0] < cutoff:
            stamps.popleft()
        return len(stamps)

    @staticmethod
    def _key(p: Perception) -> str:
        key = conversation_key(p)
        # everything on the stage shares one rhythm; channels get their own
        return p.surface if key == "stage" else key

    def _record_activity(self, p: Perception) -> None:
        if p.kind is PerceptionKind.IDLE:
            return
        key = self._key(p)
        q = self._activity.pop(key, None)
        if q is None:
            q = deque(maxlen=200)
        q.append(self._clock())
        self._activity[key] = q
        if len(self._activity) > 1000:
            self._activity.pop(next(iter(self._activity)))

    def _roster_entry(self, p: Perception):
        if self.roster is None or p.author is None:
            return None
        try:
            return self.roster.get(p.author.identity)
        except Exception as e:
            logger.debug(f"roster lookup failed: {e}")
            return None

    def _author_known(self, p: Perception) -> bool:
        return self._roster_entry(p) is not None

    def _author_promoted(self, p: Perception) -> bool:
        entry = self._roster_entry(p)
        return bool(entry and entry.promoted)

    @staticmethod
    def _donation(p: Perception) -> float:
        if p.author is None:
            return 0.0
        return float(p.author.extra.get("amount", 0) or 0)

    def _hour(self) -> int:
        return datetime.fromtimestamp(self._clock()).hour
