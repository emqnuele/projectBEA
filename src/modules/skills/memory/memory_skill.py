import asyncio
import time
import datetime
from typing import List, Dict, Optional
from pathlib import Path
from rich.console import Console

from src.core.config import BrainConfig
from src.modules.skills.base_skill import BaseSkill
from src.modules.skills.memory.storage import MemoryStorage
from src.modules.skills.memory.generator import DiaryGenerator

console = Console()

class MemorySkill(BaseSkill):
    def __init__(self, name: str, config: BrainConfig, brain):
        super().__init__(name, config, brain)
        
        # migrated settings
        self.memory_db_path = self.skill_config.get("chroma_path", "data/memory_db")
        self.embedding_model = self.skill_config.get("embedding_model", "text-embedding-3-small")
        self.openai_key = config.openai_key
        
        # ensure db directory exists
        Path(self.memory_db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.storage = MemoryStorage(self.memory_db_path, self.openai_key, self.embedding_model)
        self.generator = None

    def initialize(self):
        if not self.enabled:
            return

        # initialize storage
        if not self.storage.initialize():
            self.skill_config["enabled"] = False
            return

        # initialize generator
        if hasattr(self.context, 'llm'):
            self.generator = DiaryGenerator(self.context.llm)
        else:
            console.print("[red]MemorySkill: Brain LLM not available for generator![/red]")

    def process_previous_session(self, session_id: str, history: List[Dict]):
        if not self.enabled or not self.storage.collection:
            return

        if len(history) < 2:
            console.print(f"[yellow]MemorySkill: Session {session_id} too short. Skipping.[/yellow]")
            return

        # check if already processed
        if self.storage.entry_exists(f"diary_{session_id}"):
            console.print(f"[cyan]MemorySkill: Diary for {session_id} already exists. Skipping.[/cyan]")
            return

        asyncio.create_task(self._process_session_async(session_id, history))

    async def _process_session_async(self, session_id: str, history: List[Dict]):
        if not self.generator:
            console.print("[red]MemorySkill: Generator not initialized.[/red]")
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
            console.print(f"[red]MemorySkill: Error processing session: {e}[/red]")

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
        console.print(f"[green]MemorySkill: Saved Diary for {session_id}. Tags: {tags}[/green]")

    def retrieve_context(self, query: str, limit: int = 3) -> str:
        if not self.enabled:
            return ""
            
        try:
            # retrieve candidates
            fetch_limit = limit * 3
            results = self.storage.query_similar(query, fetch_limit)
            if not results:
                return ""
            
            # format: 'documents', 'metadatas', 'distances'
            docs = results['documents'][0]
            metas = results['metadatas'][0]
            dists = results['distances'][0]
            
            scored_entries = []
            now = time.time()
            
            for i, doc in enumerate(docs):
                if not doc: continue
                
                # 1. similarity score (1 - distance)
                similarity = 1 - dists[i]
                
                # 2. recency score
                timestamp = metas[i].get("timestamp", 0)
                age_seconds = now - timestamp
                age_days = age_seconds / 86400
                
                # decay
                decay_rate = 0.1 
                recency = 1 / (1 + age_days * decay_rate)
                
                # 3. final score (weighted average)
                # 70% smilarity, 30% recency
                final_score = (similarity * 0.7) + (recency * 0.3)
                
                scored_entries.append({
                    "doc": doc,
                    "date": metas[i].get("date", "Unknown"),
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
            console.print(f"[red]MemorySkill: Error retrieving context: {e}[/red]")
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
             console.print("[yellow]MemorySkill: No active session to save.[/yellow]")
             return False
             
        console.print(f"[cyan]MemorySkill: Manual save triggered for {session_id}[/cyan]")
        self.process_previous_session(session_id, history)
        return True

    async def save_all_pending(self):
        """
        Saves the current session on shutdown.
        Must be awaited.
        """
        if not self.enabled:
            return

        console.print("[magenta]MemorySkill: Checking for pending sessions to save...[/magenta]")
        
        if hasattr(self.context, 'history_manager'):
            hm = self.context.history_manager
            session_id = hm.session_id
            history = hm.history
            
            if session_id and history and len(history) >= 2:
                if not self.storage.entry_exists(f"diary_{session_id}"):
                    console.print(f"[magenta]MemorySkill: Saving final session {session_id}...[/magenta]")
                    # we await directly here to ensure it finishes before shutdown
                    await self._process_session_async(session_id, history)
                else:
                    console.print(f"[cyan]MemorySkill: Session {session_id} already saved.[/cyan]")
