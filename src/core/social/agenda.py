"""Things Bea means to do later, and the pass that makes her do them.

Without this she can only act inside the turn she is already in: the moment a
conversation ends, the thought ends with it. "I'll ask you tomorrow how it
went" was a thing she could say and never a thing she could do.

An intention is deliberately thin — a note and a time. What to actually say is
decided when the moment comes, with the conversation in front of her, not
frozen into a canned line hours earlier.
"""

import time
from dataclasses import dataclass
from typing import List, Optional

from src.utils.logger import get_logger

logger = get_logger("bea.social.agenda")

# a note is a reminder to herself, not a script
MAX_NOTE_CHARS = 300

# past this a reminder is not a plan any more, it is a haunting
EXPIRES_AFTER = 7 * 86400.0

# how many she is shown at once, so the prompt never fills with to-do list
MAX_RENDERED = 5


@dataclass(frozen=True)
class AgendaItem:
    id: int
    note: str
    due_ts: float
    created_at: float
    person_id: str = ""
    conversation_key: str = ""


class Agenda:
    """Her own intentions, kept in the same file as everything else she knows."""

    def __init__(self, db):
        self.db = db

    def add(self, note: str, *, due_ts: float, person_id: str = "",
            conversation_key: str = "") -> Optional[int]:
        note = (note or "").strip()[:MAX_NOTE_CHARS]
        if not note:
            return None
        with self.db.cursor() as cur:
            cur.execute(
                "INSERT INTO agenda (note, person_id, conversation_key, due_ts, "
                "created_at, done) VALUES (?, ?, ?, ?, ?, 0)",
                (note, person_id, conversation_key, float(due_ts), time.time()),
            )
            return cur.lastrowid

    def _items(self, rows) -> List[AgendaItem]:
        return [
            AgendaItem(
                id=r["id"], note=r["note"], due_ts=r["due_ts"],
                created_at=r["created_at"], person_id=r["person_id"] or "",
                conversation_key=r["conversation_key"] or "",
            )
            for r in rows
        ]

    def pending(self) -> List[AgendaItem]:
        return self._items(self.db.query(
            "SELECT * FROM agenda WHERE done = 0 ORDER BY due_ts ASC"
        ))

    def due(self, now: Optional[float] = None) -> List[AgendaItem]:
        now = time.time() if now is None else now
        return self._items(self.db.query(
            "SELECT * FROM agenda WHERE done = 0 AND due_ts <= ? AND due_ts > ? "
            "ORDER BY due_ts ASC",
            (now, now - EXPIRES_AFTER),
        ))

    def mark_done(self, item_id: int) -> None:
        self.db.execute("UPDATE agenda SET done = 1 WHERE id = ?", (item_id,))

    # dropping and finishing look the same from the outside; the difference is
    # only who decided, and nothing downstream cares
    cancel = mark_done

    def render(self, now: Optional[float] = None) -> str:
        """`[YOU MEANT TO]` for a prompt. Everything still open, soonest first."""
        items = self.pending()[:MAX_RENDERED]
        if not items:
            return ""
        now = time.time() if now is None else now
        lines = [f"- {i.note}{_when(i.due_ts - now)}" for i in items]
        return "[YOU MEANT TO]\n" + "\n".join(lines)


def _when(seconds: float) -> str:
    if seconds <= 0:
        return " (now)"
    if seconds < 3600:
        return f" (in {int(seconds // 60)} min)"
    if seconds < 86400:
        return f" (in {int(seconds // 3600)}h)"
    return f" (in {int(seconds // 86400)}d)"


class AgendaRunner:
    """Turns what is due into a conversation she actually opens."""

    def __init__(self, *, agenda: Agenda, conversations, reach=None):
        self.agenda = agenda
        self.conversations = conversations
        self.reach = reach

    def _key_for(self, item: AgendaItem) -> str:
        if item.conversation_key:
            return item.conversation_key
        if not (item.person_id and self.reach):
            return ""
        usable = [c for c in self.reach.channels(item.person_id) if c.reachable]
        return f"{usable[0].platform}:{usable[0].native_id}" if usable else ""

    async def run_once(self, now: Optional[float] = None) -> int:
        """Acts on everything due. Returns how many conversations she opened."""
        acted = 0
        for item in self.agenda.due(now):
            key = self._key_for(item)
            if not key:
                # retrying every tick forever is worse than forgetting
                logger.info(f"Dropping an intention with nowhere to go: {item.note!r}")
                self.agenda.cancel(item.id)
                continue
            try:
                await self.conversations.turn_now(
                    key, [], initiative=True, frame=_frame(item.note),
                )
            except Exception as e:
                logger.error(f"Acting on an intention failed ({item.note!r}): {e}")
                continue
            self.agenda.mark_done(item.id)
            acted += 1
        return acted


def _frame(note: str) -> str:
    return (
        "[YOU MEANT TO DO THIS]\n"
        f"Earlier you decided: {note}\n\n"
        "Nobody has written to you — you are the one picking this up. Say it the "
        "way it makes sense now, not the way you phrased it to yourself. If it has "
        "stopped making sense, `say_nothing` and let it go."
    )
