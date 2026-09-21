import asyncio
import datetime
import re
import time
from typing import Dict, List, Optional

from src.core.agent.tools import Tool
from src.core.memory.rag import SOURCE_PERSON
from src.core.memory.transcript import MIN_SPOKEN_LINES, render_stream, spoken_count
from src.core.perception.types import PerceptionKind
from src.core.persona import persona_of
from src.core.skills.base import Skill
from src.core.skills.memory.generator import DiaryGenerator
from src.utils.logger import get_logger

logger = get_logger("bea.skills.memory")

# strips the rendered routing prefix ("[marco] (discord text, channel_id=123): hi")
# so the retrieval query is the actual words, not noisy ids
_PREFIX_RE = re.compile(r"^\s*\[[^\]]*\]\s*(\([^)]*\))?\s*:?\s*")

# how many diary entries reach the prompt at once
RECALL_LIMIT = 3

# every scope the consolidation writes: the diary of a sitting, the recap of a
# conversation, and what she knows about one person
RECALL_SCOPES = ("diary", "conversation", "person")


def _clean_for_query(rendered: str) -> str:
    return _PREFIX_RE.sub("", rendered).strip() or rendered


class MemorySkill(Skill):
    """Long-term memory as a capability: recall is injected per batch.

    It comes back in two labelled blocks — what people said, and what she said —
    so her own inventions never re-enter the prompt as facts.
    """

    name = "memory"
    skill_name = "memory"

    def initialize(self) -> None:
        self.generator: Optional[DiaryGenerator] = None
        self._pending: Optional[asyncio.Task] = None

    @property
    def rag(self):
        memory = getattr(self.context, "memory", None)
        return getattr(memory, "rag", None) if memory else None

    async def start(self) -> None:
        if not self.enabled:
            logger.info("MemorySkill stays inactive (memory toggle off).")
            return
        self._repair_identities()
        if self.rag is None:
            logger.error("MemorySkill: no rag available (the embedder failed to build).")
            return
        model_for = getattr(self.context, "model_for", None)
        if model_for is not None:
            self.generator = DiaryGenerator(
                model_for("background"),
                persona=persona_of(self.config), language=self.config.language)
        else:
            logger.error("MemorySkill: no model available for the diary generator!")
        self.active = True

    def _repair_identities(self) -> None:
        """Folds duplicate cards minted before promotion had one choke point.

        Runs at boot, needs no embedder: it only reads roster sessions and
        rekeys facts and identities. A failure here must never take memory
        down with it.
        """
        memory = getattr(self.context, "memory", None)
        if memory is None:
            return
        try:
            from src.core.skills.social.people import repair_duplicate_cards
            merged = repair_duplicate_cards(memory.roster, memory.people)
            if merged:
                logger.info(f"MemorySkill: folded {merged} duplicate card(s).")
        except Exception as e:
            logger.warning(f"MemorySkill: identity repair failed: {e}")

    def tools(self) -> List[Tool]:
        # no recall tool: context_for already injects it every turn
        return []

    # --- per-batch injection ------------------------------------------------

    def context_for(self, batch) -> Optional[str]:
        if not self.active or self.rag is None:
            return None
        # silence asks nothing: an idle-only batch has no question for the
        # past, and embedding it would spend the model to retrieve noise
        if not any(self._is_memorable(p) for p in batch):
            return None
        query = " ".join(_clean_for_query(p.render()) for p in batch)
        if not query.strip():
            return None
        return self.retrieve_context(query) or None

    @staticmethod
    def _is_memorable(p) -> bool:
        """The same two exclusions the stream uses: the idle tick is the loop
        talking to itself, and a noise-flagged heartbeat is already carried
        by the live state. Neither is a question worth asking the past."""
        return p.kind is not PerceptionKind.IDLE and not (p.meta or {}).get("noise")

    def retrieve_context(self, query: str, limit: int = RECALL_LIMIT) -> str:
        """Two blocks, explicitly labelled: facts, and things she made up."""
        if self.rag is None:
            return ""
        # one embedding for every scope: the vector is the expensive part,
        # the scoped lookups after it are cheap
        qvec = self.rag.embed_query(query)
        if qvec is None:
            return ""
        facts, hers = [], []
        # one query per scope rather than one unscoped query: a scope is what
        # the vector index is partitioned by, and asking without one sends
        # every recall down the full scan
        for scope in RECALL_SCOPES:
            try:
                found, said = self.rag.recall_split(query, scope=scope, k=limit, qvec=qvec)
            except Exception as e:
                logger.error(f"MemorySkill: recall in '{scope}' failed: {e}")
                continue
            facts.extend(found)
            hers.extend(said)
        facts.sort(key=lambda r: r.similarity, reverse=True)
        hers.sort(key=lambda r: r.similarity, reverse=True)

        parts = []
        if facts:
            lines = "\n".join(f"- [{_when(r.created_at)}] {r.render()}" for r in facts[:limit])
            parts.append(f"[LONG TERM MEMORY]\n{lines}")
        if hers:
            lines = "\n".join(f"- [{_when(r.created_at)}] {r.text}" for r in hers[:limit])
            parts.append(
                "[THINGS YOU SAID BEFORE — your own past lines, not established facts. "
                "You made some of them up; don't treat them as true just because you said them.]\n"
                + lines
            )
        return "\n\n".join(parts)

    # --- writing the diary --------------------------------------------------

    @property
    def _stream(self):
        memory = getattr(self.context, "memory", None)
        return getattr(memory, "conversations", None) if memory else None

    def _transcript(self, session_id: str) -> str:
        """One sitting, both sides of it, every surface. Empty when it was quiet."""
        stream = self._stream
        if stream is None:
            return ""
        rows = stream.stream(session_id)
        if spoken_count(rows) < MIN_SPOKEN_LINES:
            return ""
        return render_stream(rows)

    def process_previous_session(self, session_id: str) -> None:
        if not self.enabled or self.rag is None:
            return
        if self.rag.exists("diary", session_id):
            logger.info(f"MemorySkill: diary for {session_id} already exists, skipping.")
            return
        # rendered once and handed over: reading the sitting again inside the
        # task is a second full query and a second render of the same rows,
        # and this runs on the shutdown path where the clock is already short
        transcript = self._transcript(session_id)
        if not transcript:
            logger.info(f"MemorySkill: session {session_id} too short, skipping.")
            return
        self._pending = asyncio.create_task(
            self._process_session_async(session_id, transcript))

    async def _process_session_async(self, session_id: str,
                                     transcript: Optional[str] = None) -> None:
        if not self.generator or self.rag is None:
            logger.error("MemorySkill: generator not initialized.")
            return
        if self.rag.exists("diary", session_id):
            return
        if transcript is None:
            transcript = self._transcript(session_id)
        if not transcript:
            return
        try:
            diary = await self.generator.generate_diary(transcript)
            if diary:
                # embedding blocks for tens of ms: not on the loop
                await asyncio.to_thread(self._save_diary, session_id, diary)
        except Exception as e:
            logger.error(f"MemorySkill: error processing session: {e}")

    def _save_diary(self, session_id: str, diary: Dict) -> None:
        content = diary.get("diary_content", "")
        if not content or self.rag is None:
            return
        tags = diary.get("tags", []) or []
        self.rag.remember(
            scope="diary", scope_key=session_id, text=content,
            who=str(diary.get("user_id", "") or ""),
            source=SOURCE_PERSON,
            tags=",".join(str(t) for t in tags), created_at=time.time(),
        )
        logger.info(f"MemorySkill: saved diary for {session_id}. Tags: {tags}")

    # --- session lifecycle --------------------------------------------------

    def save_current_session(self) -> bool:
        if not self.enabled:
            return False
        hm = getattr(self.context, "history_manager", None)
        if not hm or not hm.session_id:
            logger.warning("MemorySkill: no active session to save.")
            return False
        logger.info(f"MemorySkill: manual save triggered for {hm.session_id}")
        self.process_previous_session(hm.session_id)
        return True

    async def save_all_pending(self) -> None:
        """Saves the current session on shutdown. Must be awaited."""
        if not self.enabled or self.rag is None:
            return
        hm = getattr(self.context, "history_manager", None)
        if not hm or not hm.session_id:
            return
        if self.rag.exists("diary", hm.session_id):
            logger.info(f"MemorySkill: session {hm.session_id} already saved.")
            return
        logger.info(f"MemorySkill: saving final session {hm.session_id}…")
        await self._process_session_async(hm.session_id)


def _when(timestamp: float) -> str:
    try:
        return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return "unknown"
