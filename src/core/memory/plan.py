"""The stream plan: what the owner asked Bea to do today.

Not a memory — an instruction. The owner writes it from the dashboard, it is
injected into every prompt, and Bea closes the items herself as she gets through
them.
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional

from src.core.memory.db import Database

DIRECTIVE_KEY = "plan.directive"

TODO = "todo"
DOING = "doing"
DONE = "done"
DROPPED = "dropped"

STATUSES = (TODO, DOING, DONE, DROPPED)

# closed objectives still shown, so she can say what she already got through
MAX_CLOSED_SHOWN = 3


@dataclass
class Objective:
    """One thing the owner wants done on this stream."""

    id: int
    text: str
    detail: str = ""
    status: str = TODO
    outcome: str = ""
    position: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def open(self) -> bool:
        return self.status in (TODO, DOING)

    def render(self) -> str:
        mark = {TODO: "[ ]", DOING: "[~]", DONE: "[x]", DROPPED: "[-]"}.get(self.status, "[ ]")
        line = f"{mark} #{self.id} {self.text}"
        if self.detail:
            line += f" — {self.detail}"
        if self.outcome:
            line += f" (you said: {self.outcome})"
        return line

    def as_dict(self) -> dict:
        return {
            "id": self.id, "text": self.text, "detail": self.detail,
            "status": self.status, "outcome": self.outcome, "position": self.position,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


class StreamPlan:
    """The owner's plan for the stream, and Bea's progress through it."""

    def __init__(self, db: Database):
        self.db = db

    # --- the headline -------------------------------------------------------

    @property
    def directive(self) -> str:
        return str(self.db.scalar(
            "SELECT value FROM settings WHERE key = ?", (DIRECTIVE_KEY,), default="",
        ))

    def set_directive(self, text: str) -> None:
        self.db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (DIRECTIVE_KEY, (text or "").strip()),
        )

    # --- the objectives -----------------------------------------------------

    def add(self, text: str, detail: str = "") -> Optional[Objective]:
        text = (text or "").strip()
        if not text:
            return None
        now = time.time()
        position = int(self.db.scalar("SELECT MAX(position) FROM objectives", default=0) or 0) + 1
        oid = self.db.execute(
            "INSERT INTO objectives (text, detail, position, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (text, (detail or "").strip(), position, now, now),
        )
        return self.get(oid)

    def get(self, objective_id: int) -> Optional[Objective]:
        row = self.db.query_one("SELECT * FROM objectives WHERE id = ?", (objective_id,))
        return _objective(row) if row else None

    def all(self) -> List[Objective]:
        rows = self.db.query("SELECT * FROM objectives ORDER BY position, id")
        return [_objective(r) for r in rows]

    def open(self) -> List[Objective]:
        return [o for o in self.all() if o.open]

    def update(self, objective_id: int, *, text: Optional[str] = None,
               detail: Optional[str] = None, status: Optional[str] = None,
               outcome: Optional[str] = None) -> Optional[Objective]:
        current = self.get(objective_id)
        if current is None:
            return None
        if status is not None and status not in STATUSES:
            raise ValueError(f"unknown status '{status}'")
        self.db.execute(
            "UPDATE objectives SET text = ?, detail = ?, status = ?, outcome = ?, "
            "updated_at = ? WHERE id = ?",
            (
                (text if text is not None else current.text).strip() or current.text,
                (detail if detail is not None else current.detail).strip(),
                status if status is not None else current.status,
                (outcome if outcome is not None else current.outcome).strip(),
                time.time(), objective_id,
            ),
        )
        return self.get(objective_id)

    def remove(self, objective_id: int) -> bool:
        current = self.get(objective_id)
        self.db.execute("DELETE FROM objectives WHERE id = ?", (objective_id,))
        return current is not None

    def reorder(self, ordered_ids: List[int]) -> None:
        for position, objective_id in enumerate(ordered_ids, start=1):
            self.db.execute("UPDATE objectives SET position = ? WHERE id = ?",
                            (position, int(objective_id)))

    def clear(self) -> None:
        """A new stream: the previous plan goes away entirely."""
        with self.db.cursor() as cur:
            cur.execute("DELETE FROM objectives")
            cur.execute("DELETE FROM settings WHERE key = ?", (DIRECTIVE_KEY,))

    # --- what the mind sees -------------------------------------------------

    def render(self) -> str:
        """The plan block injected into every prompt, or "" when there is none."""
        directive = self.directive
        objectives = self.all()
        if not directive and not objectives:
            return ""

        lines = ["[TODAY'S PLAN — set by your owner, not a suggestion]"]
        if directive:
            lines.append(directive)
        if objectives:
            closed = [o for o in objectives if not o.open]
            shown = [o for o in objectives if o.open] + closed[-MAX_CLOSED_SHOWN:]
            shown.sort(key=lambda o: (o.position, o.id))
            lines.extend(o.render() for o in shown)
        return "\n".join(lines)


def _objective(row) -> Objective:
    return Objective(
        id=int(row["id"]),
        text=row["text"],
        detail=row["detail"] or "",
        status=row["status"],
        outcome=row["outcome"] or "",
        position=int(row["position"]),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )
