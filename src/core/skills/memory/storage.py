from typing import Any, Dict, Optional, cast

import chromadb
from chromadb.utils import embedding_functions

from src.utils.logger import get_logger

logger = get_logger("bea.skills.memory.storage")

class MemoryStorage:
    def __init__(self, db_path: str, api_key: Optional[str], embedding_model: str,
                 api_base: Optional[str] = None, local: bool = False):
        self.db_path = db_path
        self.api_key = api_key
        self.embedding_model = embedding_model
        self.api_base = api_base
        self.local = local
        self.chroma_client = None
        self.collection = None

    def initialize(self):
        try:
            logger.info(f"MemoryStorage: Initializing ChromaDB at {self.db_path}...")
            self.chroma_client = chromadb.PersistentClient(path=self.db_path)

            if self.local:
                # runs on-device (no network on the hot path); ~tens of ms vs ~10s
                emb_fn = embedding_functions.DefaultEmbeddingFunction()
                name = "bea_diary_local"
            elif self.api_key:
                emb_fn = embedding_functions.OpenAIEmbeddingFunction(
                    api_key=self.api_key,
                    model_name=self.embedding_model,
                    api_base=self.api_base
                )
                name = "bea_diary"
            else:
                logger.error("MemoryStorage: No OpenAI Key found! Falling back to default embedding.")
                emb_fn = None
                name = "bea_diary"

            self.collection = self.chroma_client.get_or_create_collection(
                name=name,
                embedding_function=cast(Any, emb_fn),
                metadata={"hnsw:space": "cosine"}
            )

            # one-time re-embedding of legacy openai diaries into the local space
            if self.local and self.collection.count() == 0:
                self._migrate_legacy()

            logger.info(f"MemoryStorage: ChromaDB initialized ({name}). Count: {self.collection.count()}")
            return True

        except Exception as e:
            logger.error(f"MemoryStorage: Error initializing: {e}")
            return False

    def _migrate_legacy(self) -> None:
        """Copy documents from the old openai-embedded collection into the local
        one, re-embedding with the local model (no LLM calls). Best-effort."""
        try:
            legacy = self.chroma_client.get_collection("bea_diary")
        except Exception:
            return
        try:
            data = legacy.get(include=["documents", "metadatas"])
            ids = data.get("ids") or []
            docs = data.get("documents") or []
            metas = data.get("metadatas") or []
            if not ids:
                return
            self.collection.add(documents=docs, metadatas=metas, ids=ids)
            logger.info(f"MemoryStorage: migrated {len(ids)} legacy diaries to local embeddings.")
        except Exception as e:
            logger.error(f"MemoryStorage: legacy migration failed: {e}")

    def add_entry(self, content: str, metadata: Dict, entry_id: str):
        if not self.collection:
            return

        self.collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[entry_id]
        )

    def query_similar(self, query: str, limit: int = 3):
        if not self.collection:
            return None

        return self.collection.query(
            query_texts=[query],
            n_results=limit,
            include=["documents", "metadatas", "distances"]
        )

    def entry_exists(self, entry_id: str) -> bool:
        if not self.collection:
            return False
        try:
            result = self.collection.get(ids=[entry_id])
            return len(result['ids']) > 0
        except Exception:
            return False
