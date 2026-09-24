from typing import Any, Dict, List, Optional, Tuple

from src.core.language import write_in
from src.core.memory.rag import SOURCE_PERSON
from src.core.memory.store import PersonCard
from src.core.memory.transcript import MIN_SPOKEN_LINES, render_stream, spoken_count
from src.core.persona import Persona
from src.core.skills.social.people import card_for_identity, record_person
from src.core.timeline import today_in_timezone
from src.utils.logger import get_logger
from src.utils.prompts import load_text

logger = get_logger("bea.skills.dream.dreamer")

DAY_SECONDS = 86400

DEFAULT_PROMPT_PATH = "data/prompts/dreamer.md"

FALLBACK = "Summarize the conversation as JSON with title, self_facts, people, hot_facts."

# names the LLM tends to invent when nobody real is in the chat
_GENERIC_NAMES = {"user", "chat", "chatter", "someone", "audience", "viewer", "fan", "anon"}

# a reply carrying none of these is not a consolidation, whatever parsed out of it
_SCHEMA_KEYS = {"title", "carry_over", "self_facts", "people", "conversations",
                "hot_facts", "profile"}

# unusable replies a sitting may cost before it is given up on: a provider
# hiccup deserves another night, a sitting that always fails does not deserve
# a model call every night forever
MAX_DREAM_ATTEMPTS = 3

# the newest self-facts shown to the pass as already known: a bound on the
# prompt, which would otherwise grow with every night she has ever had
MAX_KNOWN_SELF_FACTS = 100


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
                 timezone: str = "",
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
        self.timezone = timezone or ""
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
        """Consolidate every un-dreamed session, the one she is in included.

        `sittings` lists every session with something said in it that this
        pass read, consolidated or not: they are the pages the diary owes.
        """
        if not self.llm:
            return {"ok": False, "error": "no llm"}

        summary: Dict[str, Any] = {"sessions": 0, "people": 0, "self_facts": 0,
                                   "hot_facts": 0, "failed": 0, "carry_over": "",
                                   "sittings": []}

        for sid in self._pending():
            rows = self.conversations.stream(sid)
            if spoken_count(rows) < MIN_SPOKEN_LINES:
                self._mark_processed(sid)
                continue
            summary["sittings"].append(sid)

            result = await self._dream_session(rows)
            if not _usable(result):
                if self._give_up(sid):
                    self._mark_processed(sid)
                summary["failed"] += 1
                continue

            self._apply(sid, result, summary, rows)
            self._mark_processed(sid)
            summary["sessions"] += 1

        return {"ok": True, **summary}

    def _give_up(self, sid: str) -> bool:
        """Whether a sitting that came back unusable is left for good.

        Marked done on the first failure, a provider that had a bad minute
        cost that evening its cards, its recap and its facts for ever.
        """
        attempts = self.sessions.dream_failed(sid)
        if attempts >= MAX_DREAM_ATTEMPTS:
            logger.error(f"Dreamer: {sid} came back unusable {attempts} times; "
                         f"leaving it unconsolidated.")
            return True
        logger.warning(f"Dreamer: {sid} came back unusable ({attempts}/"
                       f"{MAX_DREAM_ATTEMPTS}); the next dream tries it again.")
        return False

    async def _dream_session(self, rows: List[Dict]) -> Optional[Dict]:
        convo = render_stream(rows)
        today = today_in_timezone(self.timezone)
        system = (self._prompt
                  .replace("{date}", today)
                  .replace("{language}", write_in(self.language)))
        try:
            res = await self.llm.complete_json(f"{self._known_self()}CONVERSATION:\n{convo}",
                                               system)
            return res if isinstance(res, dict) else None
        except Exception as e:
            logger.error(f"Dreamer: generation failed: {e}")
            return None

    def _known_self(self) -> str:
        """What she already worked out about herself, so a night does not repeat it.

        Blind to it, the pass rediscovers the same thing about her every night
        in new words, and the exact-text dedup lets each wording in.
        """
        facts = self.selflore.facts()[-MAX_KNOWN_SELF_FACTS:] if self.selflore is not None else []
        if not facts:
            return ""
        return "ALREADY KNOWN ABOUT YOU:\n" + "\n".join(f"- {f}" for f in facts) + "\n\n"

    def _apply(self, sid: str, result: Dict, summary: Dict,
               rows: Optional[List[Dict]] = None) -> None:
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
            if self.selflore.append_fact(_as_text(fact)):
                summary["self_facts"] += 1

        speakers = _speakers(rows or [])
        for person in result.get("people", []) or []:
            if self._apply_person(person, sid, speakers):
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

    def _apply_person(self, person: Dict, session_id: str,
                      speakers: Optional[Dict[str, set]] = None) -> bool:
        name = str(person.get("name", "")).strip()
        if not name or name.lower() in _GENERIC_NAMES:
            return False
        facts = [t for t in (_as_text(f) for f in (person.get("facts") or [])) if t]
        attitude = str(person.get("attitude", "")).strip()

        card, key = self._card_for(name, session_id, speakers or {})
        self._remember_person(card.person_id if card else key, name, facts, attitude)
        if not card:
            return False

        for f in facts:
            self.people.add_fact(card.person_id, f)
        if attitude:
            self.people.set_attitude(card.person_id, attitude)
        return True

    def _card_for(self, name: str, session_id: str,
                  speakers: Dict[str, set]) -> Tuple[Optional[PersonCard], str]:
        """The card a name from the pass belongs on, and the key to recall it by.

        The sitting knows exactly which account said what, so a name that one
        account spoke under resolves to that account's card: by name alone the
        pass wrote to whichever card came back first for it, while the live
        prompt read the account's own, and one person became two half-cards.
        A name nobody in the stream spoke under (someone talked about, or a
        speaker she never tallied) keeps the name path, which only earns a
        card at the real thresholds.
        """
        identities = speakers.get(name.lower()) or set()
        if len(identities) == 1:
            entry = self.roster.get(next(iter(identities)))
            if entry is not None:
                return card_for_identity(self.roster, self.people, entry), entry.identity
        card = record_person(self.roster, self.people, name, session_id=session_id)
        entry = self.roster.find_by_name(name)
        return card, (entry.identity if entry else "")


def _as_text(item: Any) -> str:
    """One list entry as text: the model sometimes wraps a fact in an object,
    and `str()` of that stored the braces and the key as the fact."""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("fact", "text"):
            if isinstance(item.get(key), str):
                return item[key].strip()
    return ""


def _usable(result: Any) -> bool:
    return isinstance(result, dict) and bool(_SCHEMA_KEYS & result.keys())


def _speakers(rows: List[Dict]) -> Dict[str, set]:
    """Lowercased display name -> the accounts that spoke under it in this sitting."""
    found: Dict[str, set] = {}
    for row in rows:
        identity = str(row.get("author_identity") or "")
        name = str(row.get("display_name") or "").strip().lower()
        if row.get("role") == "user" and identity and name:
            found.setdefault(name, set()).add(identity)
    return found
