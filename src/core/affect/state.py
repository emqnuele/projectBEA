"""What she feels, kept between turns and written down when someone caused it.

The state lives here and the decisions stay pure in `rules.py`, the same split
as `attention/`. There is no new sense and no new tool: the mood she already
picks for every line she speaks is the signal, and until now it only reached a
PNG.

Three things come out of one strong line, on three different clocks: the mood
itself (minutes), how she stands with whoever caused it (days), and a hot fact
so she can say what it was about.
"""

import json
import time
from typing import Callable, List, Optional

from src.core.affect.rules import (
    HALF_LIFE_SECONDS,
    PERSON_HALF_LIFE_SECONDS,
    Affect,
    decay,
    is_strong,
    render,
    stir,
)
from src.core.events import EventCategory
from src.core.mind.moods import vector_for
from src.core.skills.social.people import promotion_reason, should_promote
from src.utils.logger import get_logger

logger = get_logger("bea.affect")

SETTINGS_KEY = "affect.state"

# how far one strong line moves her standing with the person who caused it
WARMTH_WEIGHT = 0.40

# how much of the line goes into the hot fact: enough to know what it was about
QUOTED_CHARS = 100


class AffectState:
    """Her standing mood: read decayed, written when she speaks."""

    def __init__(self, config, memory, *, events=None,
                 clock: Optional[Callable[[], float]] = None):
        self.config = config
        self.memory = memory
        self.events = events
        self._clock = clock or time.time
        self._affect = self._load()
        self._shown = render(self._affect)

    # --- config -------------------------------------------------------------

    @property
    def _cfg(self) -> dict:
        return getattr(self.config, "affect", {}) or {}

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.get("enabled", True))

    @property
    def half_life(self) -> float:
        return float(self._cfg.get("half_life_minutes", HALF_LIFE_SECONDS / 60.0)) * 60.0

    @property
    def person_half_life(self) -> float:
        return float(
            self._cfg.get("person_half_life_hours", PERSON_HALF_LIFE_SECONDS / 3600.0)
        ) * 3600.0

    @property
    def memory_ttl(self) -> float:
        return float(self._cfg.get("memory_ttl_hours", 6.0)) * 3600.0

    # --- reading ------------------------------------------------------------

    @property
    def current(self) -> Affect:
        """Where she is now, with the time since the last line applied."""
        if not self.enabled:
            return Affect()
        return decay(self._affect, self._clock(), self.half_life)

    def render(self) -> str:
        return render(self.current) if self.enabled else ""

    # --- writing ------------------------------------------------------------

    def spoke(self, mood: str, batch: Optional[List] = None) -> Affect:
        """She just said something in `mood`. Returns where that leaves her."""
        if not self.enabled:
            return Affect()

        now = self._clock()
        vector = vector_for(mood)
        self._affect = stir(self._affect, vector, now=now, half_life=self.half_life)
        self._save()

        if is_strong(vector):
            self._blame(vector, batch or [], now)

        self._announce()
        return self._affect

    def _blame(self, vector, batch: List, now: float) -> None:
        """Pins a strong line on whoever caused it, when that is not a guess.

        One clear author or nothing: in a busy room the mood is the room's, and
        picking a face out of it would be inventing a grudge.
        """
        author = _lone_author(batch)
        if author is None:
            return
        card = self._card_for(author)
        if card is None:
            return

        delta = vector[0] * WARMTH_WEIGHT
        try:
            self.memory.people.nudge_warmth(
                card.person_id, delta, half_life=self.person_half_life, now=now
            )
            self.memory.hot.add(
                _what_happened(author.display_name or card.primary_name, batch, delta),
                self.memory_ttl, source="live",
            )
        except Exception as e:
            logger.warning(f"Could not record how {author.display_name} left her: {e}")
            return
        logger.info(f"affect: {author.display_name} moved her by {delta:+.2f}")

    def _card_for(self, author):
        """Their card, minting one if this is what made them worth remembering.

        Someone who got a real reaction out of her has made themselves matter,
        which is already what earns a card — so this marks them and lets the
        existing thresholds agree.
        """
        people, roster = self.memory.people, self.memory.roster
        card = people.get_by_identity(author.identity)
        if card is not None:
            return card

        entry = roster.mark(author.identity)
        if entry is None or entry.promoted or not should_promote(entry):
            return None
        card = people.create_from_entry(entry, reason=promotion_reason(entry))
        roster.set_promoted(entry.identity, card.person_id)
        logger.info(f"affect: {author.display_name} got a card ({promotion_reason(entry)}).")
        return card

    # --- persistence --------------------------------------------------------

    def _load(self) -> Affect:
        try:
            raw = self.memory.db.scalar(
                "SELECT value FROM settings WHERE key = ?", (SETTINGS_KEY,), default="",
            )
            data = json.loads(raw) if raw else {}
            return Affect(
                float(data.get("valence", 0.0)),
                float(data.get("arousal", 0.0)),
                float(data.get("updated_at", 0.0)),
            )
        except Exception as e:
            # a mood is not worth failing to start over
            logger.warning(f"Could not read her last mood ({e}); starting neutral.")
            return Affect()

    def _save(self) -> None:
        payload = json.dumps({
            "valence": round(self._affect.valence, 4),
            "arousal": round(self._affect.arousal, 4),
            "updated_at": self._affect.updated_at,
        })
        try:
            self.memory.db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (SETTINGS_KEY, payload),
            )
        except Exception as e:
            logger.warning(f"Could not save her mood: {e}")

    # --- the dashboard ------------------------------------------------------

    def _announce(self) -> None:
        """Only when it changed: a drifting value nobody can see is a bug farm."""
        line = self.render()
        if line == self._shown:
            return
        self._shown = line
        if self.events is None:
            return
        current = self.current
        self.events.publish(
            EventCategory.SYSTEM, "affect",
            line.replace("\n", " ") if line else "back to normal",
            metadata={
                "valence": round(current.valence, 3),
                "arousal": round(current.arousal, 3),
            },
        )


def _lone_author(batch: List):
    """The one person this batch is from, or None if it is a room."""
    authors = {}
    for p in batch:
        author = getattr(p, "author", None)
        if author is None or author.is_owner:
            continue
        authors[author.identity] = author
    return next(iter(authors.values())) if len(authors) == 1 else None


def _what_happened(name: str, batch: List, delta: float) -> str:
    """The hot fact, as a plain statement of what was said and by whom."""
    line = _last_line(batch)
    quoted = f' — "{line}"' if line else ""
    verb = "made your day" if delta > 0 else "got to you"
    return f"something {name} said {verb}{quoted}"


def _last_line(batch: List) -> str:
    for p in reversed(batch):
        text = " ".join(str(getattr(p, "content", "") or "").split())
        if not text:
            continue
        # perceptions arrive already rendered as "[marco] ..."; the name is
        # already in the sentence around this quote
        if text.startswith("["):
            _, sep, rest = text.partition("] ")
            text = rest if sep else text
        if len(text) > QUOTED_CHARS:
            text = text[: QUOTED_CHARS - 1] + "…"
        return text
    return ""
