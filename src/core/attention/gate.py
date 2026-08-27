"""The attention gate: what wakes the mind, and what merely gets noticed.

State lives here (activity counters, when she last spoke, the digest buffer);
the decisions live in `rules.py` and stay pure. `rng` and `clock` are injected
so the whole thing is deterministic under test.
"""

import random
import time
from collections import deque
from datetime import datetime
from typing import Callable, Deque, Dict, List, Optional, Sequence, Tuple

from src.core.attention.followup import is_followup
from src.core.attention.rules import in_quiet_hours, is_addressed, score
from src.core.attention.types import Reaction, Verdict
from src.core.mind.routing import conversation_key
from src.core.perception.types import Perception, PerceptionKind
from src.utils.logger import get_logger

logger = get_logger("bea.attention")

# window over which "how alive is this surface" is measured
ACTIVITY_WINDOW_SECONDS = 120.0

# how much a digest line may carry: it is peripheral awareness, not a transcript
DIGEST_LINE_CHARS = 140

# past this, a surface gets one aggregated line instead of one line per item
AGGREGATE_AFTER = 2

# the bucket for "wherever she is", as opposed to one specific conversation
ANYWHERE = "*"

OnVerdict = Callable[[Perception, Verdict], None]


class Attention:
    """Splits a perception batch into "react now" and "just noticed"."""

    def __init__(
        self,
        config,
        roster=None,
        *,
        rng: Optional[random.Random] = None,
        clock: Optional[Callable[[], float]] = None,
        on_verdict: Optional[OnVerdict] = None,
        conversations=None,
    ) -> None:
        self.config = config
        self.roster = roster
        self.conversations = conversations
        self._rng = rng or random.Random()
        self._clock = clock or time.time
        self._on_verdict = on_verdict

        # keyed by conversation, not by surface: all discord channels share one
        # surface, and a busy channel must not drag her into a quiet one
        self._activity: Dict[str, Deque[float]] = {}
        self._last_spoke: Dict[str, float] = {}
        self._noted: List[Tuple[str, str]] = []      # (surface, rendered line)

    # --- config -------------------------------------------------------------

    @property
    def _cfg(self) -> dict:
        return getattr(self.config, "attention", {}) or {}

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.get("enabled", True))

    @property
    def trigger_words(self) -> Sequence[str]:
        return self._cfg.get("trigger_words", ["bea"])

    @property
    def hot_names(self) -> Sequence[str]:
        return list(self.trigger_words) + list(self._cfg.get("hot_names", []))

    @property
    def threshold(self) -> float:
        return float(self._cfg.get("interject_threshold", 0.45))

    @property
    def cooldown(self) -> float:
        return float(self._cfg.get("cooldown_seconds", 20.0))

    @property
    def followup_enabled(self) -> bool:
        return bool(self._cfg.get("followup_enabled", True))

    @property
    def quiet_hours(self) -> Tuple[int, int]:
        q = self._cfg.get("quiet_hours", [3, 9])
        return int(q[0]), int(q[1])

    # --- the decision -------------------------------------------------------

    def judge(self, batch: List[Perception]) -> Tuple[List[Perception], List[Perception]]:
        """Returns (react, noted). Records activity as it goes."""
        if not batch:
            return [], []
        if not self.enabled:
            return list(batch), []

        react: List[Perception] = []
        noted: List[Perception] = []

        for p in batch:
            self._record_activity(p)
            verdict = self._judge_one(p)
            if self._on_verdict:
                self._on_verdict(p, verdict)

            if verdict.reaction is Reaction.REACT:
                react.append(p)
            elif verdict.reaction is Reaction.NOTE:
                noted.append(p)

        # a reaction drags the rest of its batch along: same moment, same context
        if react and noted:
            react = sorted(react + noted, key=lambda p: p.ts)
            noted = []
        return react, noted

    def _judge_one(self, p: Perception) -> Verdict:
        # the bus only emits IDLE after `idle_after` seconds of nothing: the
        # timer is already the gate
        if p.kind is PerceptionKind.IDLE:
            if in_quiet_hours(self._hour(), *self.quiet_hours):
                return Verdict(Reaction.DROP, 0.0, "idle:quiet-hours")
            return Verdict(Reaction.REACT, 1.0, "idle:timer")

        # flagged by the sense itself: already in live state, no digest line needed
        if p.meta.get("noise"):
            return Verdict(Reaction.DROP, 0.0, "noise")

        reason = is_addressed(
            p, trigger_words=self.trigger_words, self_ids=self._cfg.get("self_ids", [])
        )
        if reason:
            return Verdict(Reaction.REACT, 1.0, reason)

        key = self._key(p)
        if self._is_followup(p, key):
            return Verdict(Reaction.REACT, 1.0, "addressed:follow-up")
        base = score(
            salience=p.salience,
            text=p.content,
            author_known=self._author_known(p),
            author_promoted=self._author_promoted(p),
            donation=self._donation(p),
            hot_names=self.hot_names,
            seconds_since_spoke=self.seconds_since_spoke(key),
            recent_activity=self.activity(key),
            hour=self._hour(),
            quiet=self.quiet_hours,
            cooldown_seconds=self.cooldown,
        )
        if base <= 0.0:
            return Verdict(Reaction.NOTE, 0.0, self._zero_reason(key))

        # human variance: ±0.1 before comparing, so she is not a step function
        effective = base + self._rng.uniform(-0.10, 0.10)
        if effective >= self.threshold:
            return Verdict(Reaction.REACT, base, f"score:{base:.2f}")
        return Verdict(Reaction.NOTE, base, f"score:{base:.2f}")

    def _is_followup(self, p: Perception, key: str) -> bool:
        """Is this person answering something she said to them?

        Deterministic and cooldown-free on purpose: see `followup.py`.
        """
        if not self.followup_enabled or self.conversations is None or p.author is None:
            return False
        conversation = conversation_key(p)
        try:
            history = self.conversations.turns(
                conversation, limit=int(self._cfg.get("followup_lookback", 30))
            )
            since = self.conversations.seconds_since_bea_spoke(conversation)
            activity = self.conversations.recent_activity(conversation)
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

    def _zero_reason(self, key: str = ANYWHERE) -> str:
        since = self.seconds_since_spoke(key)
        if since is not None and since < self.cooldown:
            return "cooldown"
        if in_quiet_hours(self._hour(), *self.quiet_hours):
            return "quiet-hours"
        return "score:0.00"

    # --- state --------------------------------------------------------------

    def mark_spoke(self, key: str = ANYWHERE) -> None:
        """She just said something. `key` scopes it to one conversation.

        A scoped reply records only under its key: typing in one channel is not
        a reason to go quiet everywhere. Speaking on stage is, so it lands on
        ANYWHERE, which every key without its own stamp falls back to.
        """
        self._last_spoke[key] = self._clock()

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
        self._activity.setdefault(self._key(p), deque(maxlen=200)).append(self._clock())

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

    # --- the digest ---------------------------------------------------------

    def remember(self, noted: List[Perception]) -> None:
        """Files noted perceptions into peripheral awareness."""
        for p in noted:
            self._noted.append((p.surface, _one_line(p)))

    def digest(self, max_lines: Optional[int] = None) -> str:
        """What happened while she wasn't paying attention. Consumed on read.

        Peripheral awareness, not memory: capped, emptied on read, gone after
        the turn.
        """
        if not self._noted:
            return ""
        cap = max_lines if max_lines is not None else int(self._cfg.get("digest_max_lines", 8))

        by_surface: Dict[str, List[str]] = {}
        for surface, line in self._noted:
            by_surface.setdefault(surface, []).append(line)

        lines: List[str] = []
        for surface, entries in by_surface.items():
            if len(entries) > AGGREGATE_AFTER:
                lines.append(f"- {surface}: {len(entries)} messages, last — {entries[-1]}")
            else:
                lines.extend(f"- {surface}: {e}" for e in entries)

        self._noted.clear()

        if not lines:
            return ""
        if len(lines) > cap:
            hidden = len(lines) - cap
            lines = lines[-cap:]
            lines.insert(0, f"- (+{hidden} more you didn't catch)")
        return "[WHILE YOU WERE BUSY]\n" + "\n".join(lines)

    def pending(self) -> int:
        """How many noted items are waiting in the digest (for the dashboard)."""
        return len(self._noted)


def _one_line(p: Perception) -> str:
    text = " ".join((p.content or "").split())
    if len(text) > DIGEST_LINE_CHARS:
        text = text[: DIGEST_LINE_CHARS - 1] + "…"
    return text
