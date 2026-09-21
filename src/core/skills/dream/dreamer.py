import datetime
from typing import Any, Dict, List, Optional

from src.core.language import write_in
from src.core.memory.rag import SOURCE_PERSON
from src.core.memory.transcript import MIN_SPOKEN_LINES, render_stream, spoken_count
from src.core.persona import Persona
from src.core.skills.social.people import record_person
from src.utils.logger import get_logger
from src.utils.prompts import load_text

logger = get_logger("bea.skills.dream.dreamer")

DAY_SECONDS = 86400

DEFAULT_PROMPT_PATH = "data/prompts/dreamer.md"

FALLBACK = "Summarize the conversation as JSON with title, self_facts, people, hot_facts."

# names the LLM tends to invent when nobody real is in the chat
_GENERIC_NAMES = {"user", "chat", "chatter", "someone", "audience", "viewer", "fan", "anon"}


class Dreamer:
    """The consolidation pass: turns the stream into durable memory.

    For each un-dreamed session it reads everything that happened in it — every
    surface, every person, the game and her own answers alike — hands it to the
    LLM (Bea's subconscious) segmented by conversation, and writes back a title,
    self-facts, per-person facts and hot facts. Idempotent: processed sessions
    are tracked so re-dreaming is a no-op.

    The session she is standing in is consolidated like any other, and last:
    the evening she just had is the one she will be asked about tomorrow.
    """

    def __init__(self, *, llm, history_manager, roster, people, selflore, recent,
                 sessions, conversations, rag=None, persona=None, language: str = "",
                 prompt_path: str = DEFAULT_PROMPT_PATH):
        self.llm = llm
        self.history = history_manager
        self.roster = roster
        self.people = people
        self.selflore = selflore
        self.recent = recent
        self.sessions = sessions
        self.conversations = conversations
        # optional: without an embedder there is no retrieval, and the cards
        # and self-lore the pass writes are worth having either way
        self.rag = rag
        self.persona = persona or Persona()
        self.language = language
        self.prompt_path = prompt_path or DEFAULT_PROMPT_PATH

    @property
    def _prompt(self) -> str:
        """Read per pass, not cached: it is an editable file like every other."""
        return self.persona.fill(load_text(self.prompt_path, fallback=FALLBACK))

    def _processed(self) -> set:
        return self.sessions.dreamed()

    def _mark_processed(self, session_id: str) -> None:
        self.sessions.mark_dreamed(session_id)

    def _pending(self) -> List[str]:
        """Un-dreamed sessions with something in them, the active one last.

        Ordered by when they started, which puts the one she is in at the end:
        whatever she carries into tomorrow should come from tonight, not from
        a session three days old that happens to sort after it.
        """
        done = self._processed()
        return [sid for sid in self.conversations.sessions_with_content()
                if sid not in done]

    async def run(self) -> Dict[str, Any]:
        """Consolidate every un-dreamed session, the one she is in included."""
        if not self.llm:
            return {"ok": False, "error": "no llm"}

        summary: Dict[str, Any] = {"sessions": 0, "people": 0, "self_facts": 0,
                                   "hot_facts": 0, "carry_over": ""}

        for sid in self._pending():
            rows = self.conversations.stream(sid)
            if spoken_count(rows) < MIN_SPOKEN_LINES:
                self._mark_processed(sid)
                continue

            result = await self._dream_session(rows)
            if result:
                self._apply(sid, result, summary)
            self._mark_processed(sid)
            summary["sessions"] += 1

        return {"ok": True, **summary}

    async def _dream_session(self, rows: List[Dict]) -> Optional[Dict]:
        convo = render_stream(rows)
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        system = (self._prompt
                  .replace("{date}", today)
                  .replace("{language}", write_in(self.language)))
        try:
            res = await self.llm.complete_json(f"CONVERSATION:\n{convo}", system)
            return res if isinstance(res, dict) else None
        except Exception as e:
            logger.error(f"Dreamer: generation failed: {e}")
            return None

    def _apply(self, sid: str, result: Dict, summary: Dict) -> None:
        # the last session consolidated is the freshest one: what it says to
        # carry is what opens the window she wakes up in
        carry = str(result.get("carry_over") or "").strip()
        if carry:
            summary["carry_over"] = carry

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

        for conversation in result.get("conversations", []) or []:
            self._remember_conversation(conversation)

        for hot in result.get("hot_facts", []) or []:
            text = str(hot.get("text", "")).strip()
            ttl_days = float(hot.get("ttl_days", 3) or 3)
            if text:
                self.recent.add(text, ttl_days * DAY_SECONDS, source="dreamer")
                summary["hot_facts"] += 1

    def _remember_conversation(self, conversation: Dict) -> None:
        """One recap per conversation, recallable on its own.

        Scoped by conversation key rather than by session: "what did marco and
        I talk about" is a question about a thread, and a session is a sitting
        that may hold four of them.
        """
        if self.rag is None:
            return
        key = str(conversation.get("key", "")).strip()
        recap = str(conversation.get("recap", "")).strip()
        if not key or not recap:
            return
        try:
            self.rag.remember(scope="conversation", scope_key=key, text=recap,
                              source=SOURCE_PERSON)
        except Exception as e:
            logger.warning(f"Dreamer: could not keep the recap for {key}: {e}")

    def _remember_person(self, key: str, name: str, facts: List[str],
                         attitude: str) -> None:
        """What she learned about someone, as something she can be reminded of.

        Written whether or not they earned a card, which is the whole point:
        a card is what goes in the prompt for the regulars, and this is for
        everyone else — the person she met once and meets again in six weeks,
        who would otherwise be a stranger both times.
        """
        if self.rag is None or not key:
            return
        text = "; ".join([f for f in facts if f] + ([attitude] if attitude else []))
        if not text:
            return
        try:
            self.rag.remember(scope="person", scope_key=key, text=f"{name}: {text}",
                              who=name, source=SOURCE_PERSON)
        except Exception as e:
            logger.warning(f"Dreamer: could not keep what it learned about them: {e}")

    def _apply_person(self, person: Dict, session_id: str) -> bool:
        name = str(person.get("name", "")).strip()
        if not name or name.lower() in _GENERIC_NAMES:
            return False
        facts = [str(f) for f in (person.get("facts") or [])]
        attitude = str(person.get("attitude", "")).strip()

        # build the tally; only earns a card at the real thresholds (no force).
        # first-timers stay as a cheap tally — a card is for regulars.
        card = record_person(self.roster, self.people, name, session_id=session_id)
        entry = self.roster.find_by_name(name)
        self._remember_person(card.person_id if card else (entry.identity if entry else ""),
                              name, facts, attitude)
        if not card:
            return False

        for f in facts:
            self.people.add_fact(card.person_id, f)
        if attitude:
            self.people.set_attitude(card.person_id, attitude)
        return True
