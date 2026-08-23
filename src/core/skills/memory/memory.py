import asyncio
import datetime
import re
import time
from typing import Dict, List, Optional

from src.core.agent.tools import Tool
from src.core.memory.rag import SOURCE_PERSON
from src.core.skills.base import Skill
from src.core.skills.memory.generator import DiaryGenerator
from src.utils.logger import get_logger

logger = get_logger("bea.skills.memory")

# strips the rendered routing prefix ("[marco] (discord text, channel_id=123): hi")
# so the retrieval query is the actual words, not noisy ids
_PREFIX_RE = re.compile(r"^\s*\[[^\]]*\]\s*(\([^)]*\))?\s*:?\s*")

# how many diary entries reach the prompt at once
RECALL_LIMIT = 3


def _clean_for_query(rendered: str) -> str:
    return _PREFIX_RE.sub("", rendered).strip() or rendered


class MemorySkill(Skill):
    """Long-term memory as a capability: when on, Bea recalls past sessions
    (RAG injected per batch). When off, she has no memory at all.

    Recall comes back in two labelled blocks — what people said, and what SHE
    said. Bea invents on purpose, and without that split her own inventions would
    re-enter the prompt as facts and compound into incoherence.
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
        if self.rag is None:
            logger.error("MemorySkill: no rag available (the embedder failed to build).")
            return
        model_for = getattr(self.context, "model_for", None)
        if model_for is not None:
            self.generator = DiaryGenerator(model_for("background"))
        else:
            logger.error("MemorySkill: no model available for the diary generator!")
        self.active = True

    def tools(self) -> List[Tool]:
        # no recall tool: long-term memory is injected automatically every turn
        # (context_for). A manual recall burned an extra slow round-trip and a
        # second embedding to fetch what she already had.
        return []

    # --- per-batch injection ------------------------------------------------

    def context_for(self, batch) -> Optional[str]:
        if not self.active or self.rag is None:
            return None
        query = " ".join(_clean_for_query(p.render()) for p in batch)
        if not query.strip():
            return None
        return self.retrieve_context(query) or None

    def retrieve_context(self, query: str, limit: int = RECALL_LIMIT) -> str:
        """Two blocks, explicitly labelled: facts, and things she made up."""
        if self.rag is None:
            return ""
        try:
            facts, hers = self.rag.recall_split(query, scope="diary", k=limit)
        except Exception as e:
            logger.error(f"MemorySkill: recall failed: {e}")
            return ""

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

    def process_previous_session(self, session_id: str, history: List[Dict]) -> None:
        if not self.enabled or self.rag is None:
            return
        if len(history) < 2:
            logger.info(f"MemorySkill: session {session_id} too short, skipping.")
            return
        if self.rag.exists("diary", session_id):
            logger.info(f"MemorySkill: diary for {session_id} already exists, skipping.")
            return
        self._pending = asyncio.create_task(self._process_session_async(session_id, history))

    async def _process_session_async(self, session_id: str, history: List[Dict]) -> None:
        if not self.generator or self.rag is None:
            logger.error("MemorySkill: generator not initialized.")
            return
        if self.rag.exists("diary", session_id):
            return
        try:
            diary = await self.generator.generate_diary(history)
            if diary:
                self._save_diary(session_id, diary)
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
        if not hm or not hm.session_id or not hm.history:
            logger.warning("MemorySkill: no active session to save.")
            return False
        logger.info(f"MemorySkill: manual save triggered for {hm.session_id}")
        self.process_previous_session(hm.session_id, hm.history)
        return True

    async def save_all_pending(self) -> None:
        """Saves the current session on shutdown. Must be awaited."""
        if not self.enabled or self.rag is None:
            return
        hm = getattr(self.context, "history_manager", None)
        if not hm or not hm.session_id or len(hm.history or []) < 2:
            return
        if self.rag.exists("diary", hm.session_id):
            logger.info(f"MemorySkill: session {hm.session_id} already saved.")
            return
        logger.info(f"MemorySkill: saving final session {hm.session_id}…")
        await self._process_session_async(hm.session_id, hm.history)


def _when(timestamp: float) -> str:
    try:
        return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return "unknown"
