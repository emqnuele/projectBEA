import asyncio
import time
import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

from src.core.agent.tools import Tool
from src.core.perception.types import PerceptionKind
from src.core.skills.base import Skill
from src.core.skills.memory.storage import MemoryStorage
from src.core.skills.memory.generator import DiaryGenerator
from src.utils.logger import get_logger

logger = get_logger("bea.skills.memory")

import re

# strips the rendered routing prefix ("[marco] (discord text, channel_id=123): hi")
# so the retrieval query is the actual words, not noisy ids
_PREFIX_RE = re.compile(r"^\s*\[[^\]]*\]\s*(\([^)]*\))?\s*:?\s*")


def _clean_for_query(rendered: str) -> str:
    return _PREFIX_RE.sub("", rendered).strip() or rendered


class MemorySkill(Skill):
    """Long-term memory as a capability: when on, Bea recalls past sessions
    (RAG injected per batch) and can search them via the `recall_memory` tool.
    When off, she has no memory at all."""

    name = "memory"
    skill_name = "memory"

    def __init__(self, config, bus, expression, context=None):
        super().__init__(config, bus, expression, context)

        cfg = config.skills.get("memory", {})
        self.memory_db_path = cfg.get("chroma_path", "data/memory_db")
        self.embedding_model = cfg.get("embedding_model", "local")

        # "local" runs the embedding model on-device: no network round-trip on the
        # hot path (the old openrouter embedding cost ~10s per turn)
        self.local = self.embedding_model == "local"
        if self.local:
            self.api_key = None
            self.api_base = None
        elif "/" in self.embedding_model or config.llm_provider == "openrouter":
            self.api_key = config.openrouter_key
            self.api_base = "https://openrouter.ai/api/v1"
        else:
            self.api_key = config.openai_key
            self.api_base = None

        Path(self.memory_db_path).parent.mkdir(parents=True, exist_ok=True)
        self.storage = MemoryStorage(
            db_path=self.memory_db_path,
            api_key=self.api_key,
            embedding_model=self.embedding_model,
            api_base=self.api_base,
            local=self.local,
        )
        self.generator = None

    def initialize(self):
        if self.enabled:
            self._ensure_ready()

    def _ensure_ready(self) -> bool:
        if self.storage.collection:
            return True
        if not self.storage.initialize():
            logger.error("MemorySkill: storage failed to initialize.")
            return False
        if self.context and hasattr(self.context, "llm"):
            self.generator = DiaryGenerator(self.context.llm)
        else:
            logger.error("MemorySkill: Brain LLM not available for generator!")
        return True

    async def start(self):
        if not self.enabled:
            return
        if self._ensure_ready():
            self.active = True

    def tools(self) -> List[Tool]:
        # no recall tool: long-term memory is injected automatically every turn
        # (context_for). exposing a manual recall made Bea burn an extra slow llm
        # round-trip + a second embedding to fetch what she already had.
        return []

    def context_for(self, batch) -> Optional[str]:
        if not self.active:
            return None
        query = " ".join(_clean_for_query(p.render()) for p in batch)
        if not query.strip():
            return None
        ctx = self.retrieve_context(query)
        return f"[LONG TERM MEMORY]\n{ctx}" if ctx else None

    def process_previous_session(self, session_id: str, history: List[Dict]):
        if not self.enabled or not self.storage.collection:
            return

        if len(history) < 2:
            logger.warning(f"MemorySkill: Session {session_id} too short. Skipping.")
            return

        # check if already processed
        if self.storage.entry_exists(f"diary_{session_id}"):
            logger.info(f"MemorySkill: Diary for {session_id} already exists. Skipping.")
            return

        asyncio.create_task(self._process_session_async(session_id, history))

    async def _process_session_async(self, session_id: str, history: List[Dict]):
        if not self.generator:
            logger.error("MemorySkill: Generator not initialized.")
            return
        
        # double check inside async
        if self.storage.entry_exists(f"diary_{session_id}"):
             return

        try:
            # generate diary
            diary_json = await self.generator.generate_diary(history)
            
            if not diary_json:
                return

            # save to storage
            self._save_diary(session_id, diary_json)

        except Exception as e:
            logger.error(f"MemorySkill: Error processing session: {e}")

    def _save_diary(self, session_id: str, diary_json: Dict):
        diary_content = diary_json.get("diary_content", "")
        tags = diary_json.get("tags", [])
        user_id = diary_json.get("user_id", "owner")
        
        if not diary_content:
            return

        timestamp = time.time()
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        metadata = {
            "timestamp": timestamp,
            "date": today_str,
            "user_id": user_id,
            "tags": ",".join(tags), 
            "session_id": session_id
        }
        
        self.storage.add_entry(diary_content, metadata, f"diary_{session_id}")
        logger.info(f"MemorySkill: Saved Diary for {session_id}. Tags: {tags}")

    def retrieve_context(self, query: str, limit: int = 3) -> str:
        if not self.enabled:
            return ""
            
        try:
            # retrieve candidates
            fetch_limit = limit * 3
            results = self.storage.query_similar(query, fetch_limit)
            if not results:
                return ""
            
            docs = results.get('documents')
            metas = results.get('metadatas')
            dists = results.get('distances')

            if not docs or not metas or not dists:
                return ""

            docs_list = docs[0]
            metas_list = metas[0]
            dists_list = dists[0]

            if not docs_list or not metas_list or not dists_list:
                return ""

            scored_entries = []
            now = time.time()

            for i, doc in enumerate(docs_list):
                if not doc: continue

                dist_val = dists_list[i]
                similarity = 1.0 - (float(dist_val) if dist_val is not None else 0.0)

                meta_item = metas_list[i]
                timestamp_val = meta_item.get("timestamp", 0) if meta_item else 0
                if not isinstance(timestamp_val, (int, float)):
                    timestamp_val = 0
                age_seconds = now - float(timestamp_val)
                age_days = age_seconds / 86400
                
                # decay
                decay_rate = 0.1 
                recency = 1 / (1 + age_days * decay_rate)
                
                # 3. final score (weighted average)
                # 70% smilarity, 30% recency
                final_score = (similarity * 0.7) + (recency * 0.3)
                
                scored_entries.append({
                    "doc": doc,
                    "date": meta_item.get("date", "Unknown") if meta_item else "Unknown",
                    "score": final_score
                })
            
            # sort by score desc
            scored_entries.sort(key=lambda x: x["score"], reverse=True)
            
            # take top 'limit'
            top_entries = scored_entries[:limit]
            
            context_str = "RELEVANT DIARY ENTRIES:\n"
            found = False
            for entry in top_entries:
                context_str += f"- [{entry['date']}]: {entry['doc']}\n"
                found = True
            
            return context_str if found else ""
            
        except Exception as e:
            logger.error(f"MemorySkill: Error retrieving context: {e}")
            return ""

    def save_current_session(self):
        """Manually triggers saving of the current session."""
        if not self.enabled:
            return False
            
        if not hasattr(self.context, 'history_manager'):
             return False
             
        hm = self.context.history_manager
        session_id = hm.session_id
        history = hm.history
        
        if not session_id or not history:
             logger.warning("MemorySkill: No active session to save.")
             return False
             
        logger.info(f"MemorySkill: Manual save triggered for {session_id}")
        self.process_previous_session(session_id, history)
        return True

    async def save_all_pending(self):
        """
        Saves the current session on shutdown.
        Must be awaited.
        """
        if not self.enabled:
            return

        logger.info("MemorySkill: Checking for pending sessions to save...")
        
        if hasattr(self.context, 'history_manager'):
            hm = self.context.history_manager
            session_id = hm.session_id
            history = hm.history
            
            if session_id and history and len(history) >= 2:
                if not self.storage.entry_exists(f"diary_{session_id}"):
                    logger.info(f"MemorySkill: Saving final session {session_id}...")
                    # we await directly here to ensure it finishes before shutdown
                    await self._process_session_async(session_id, history)
                else:
                    logger.info(f"MemorySkill: Session {session_id} already saved.")
