import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.skills.social.people import record_person
from src.utils.logger import get_logger

logger = get_logger("bea.skills.dream.dreamer")

DAY_SECONDS = 86400

# names the LLM tends to invent when nobody real is in the chat
_GENERIC_NAMES = {"user", "chat", "chatter", "someone", "audience", "viewer", "fan", "anon"}


class Dreamer:
    """The consolidation pass: turns raw conversations into durable memory.

    For each un-dreamed session it asks the LLM (Bea's subconscious) to extract a
    title, self-facts, per-person facts and hot facts, then writes them into the
    live stores (self-lore, people cards, recent) and titles the conversation.
    Idempotent: processed sessions are tracked so re-dreaming is a no-op.
    """

    def __init__(self, *, llm, history_manager, roster, people, selflore, recent,
                 sessions, conversations_dir: str = "data/conversations"):
        self.llm = llm
        self.history = history_manager
        self.roster = roster
        self.people = people
        self.selflore = selflore
        self.recent = recent
        self.sessions = sessions
        self.conversations_dir = Path(conversations_dir)
        self._prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        p = Path(__file__).parent / "dreamer_prompt.txt"
        try:
            return p.read_text(encoding="utf-8")
        except Exception:
            return "Summarize the conversation as JSON with title, self_facts, people, hot_facts."

    def _processed(self) -> set:
        return self.sessions.dreamed()

    def _mark_processed(self, session_id: str) -> None:
        self.sessions.mark_dreamed(session_id)

    async def run(self) -> Dict[str, Any]:
        """Consolidate every un-dreamed session except the active one."""
        if not self.llm:
            return {"ok": False, "error": "no llm"}

        done = self._processed()
        active = self.history.session_id
        sessions = sorted(self.conversations_dir.glob("session_*.json"))
        summary = {"sessions": 0, "people": 0, "self_facts": 0, "hot_facts": 0}

        for path in sessions:
            sid = path.stem
            if sid in done or sid == active:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            messages = data.get("messages", [])
            if len(messages) < 2:
                self._mark_processed(sid)
                continue

            result = await self._dream_session(messages)
            if result:
                self._apply(sid, result, summary)
            self._mark_processed(sid)
            summary["sessions"] += 1

        return {"ok": True, **summary}

    async def _dream_session(self, messages: List[Dict]) -> Optional[Dict]:
        convo = "\n".join(f"{m.get('role', '?')}: {m.get('content', '')}" for m in messages)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        system = self._prompt.replace("{date}", today)
        try:
            res = await self.llm.complete_json(f"CONVERSATION:\n{convo}", system)
            return res if isinstance(res, dict) else None
        except Exception as e:
            logger.error(f"Dreamer: generation failed: {e}")
            return None

    def _apply(self, sid: str, result: Dict, summary: Dict) -> None:
        title = (result.get("title") or "").strip()
        if title:
            self.history.set_session_title(sid, title)
            self.sessions.set_title(sid, title)

        # structured profile bits (e.g. birthday) the morning pass needs
        self.selflore.update_profile(result.get("profile") or {})

        for fact in result.get("self_facts", []) or []:
            if self.selflore.append_fact(str(fact)):
                summary["self_facts"] += 1

        for person in result.get("people", []) or []:
            if self._apply_person(person, sid):
                summary["people"] += 1

        for hot in result.get("hot_facts", []) or []:
            text = str(hot.get("text", "")).strip()
            ttl_days = float(hot.get("ttl_days", 3) or 3)
            if text:
                self.recent.add(text, ttl_days * DAY_SECONDS, source="dreamer")
                summary["hot_facts"] += 1

    def _apply_person(self, person: Dict, session_id: str) -> bool:
        name = str(person.get("name", "")).strip()
        if not name or name.lower() in _GENERIC_NAMES:
            return False
        facts = [str(f) for f in (person.get("facts") or [])]
        attitude = str(person.get("attitude", "")).strip()

        # build the tally; only earns a card at the real thresholds (no force).
        # first-timers stay as a cheap tally — facts are kept only for regulars.
        card = record_person(self.roster, self.people, name, session_id=session_id)
        if not card:
            return False

        for f in facts:
            self.people.add_fact(card.person_id, f)
        if attitude:
            self.people.set_attitude(card.person_id, attitude)
        return True
