import chromadb
from chromadb.utils import embedding_functions
import time
from typing import Optional, List, Dict, cast, Any
from src.utils.logger import get_logger

logger = get_logger("bea.skills.memory.storage")

class MemoryStorage:
    def __init__(self, db_path: str, api_key: Optional[str], embedding_model: str, api_base: Optional[str] = None):
        self.db_path = db_path
        self.api_key = api_key
        self.embedding_model = embedding_model
        self.api_base = api_base
        self.chroma_client = None
        self.collection = None

    def initialize(self):
        try:
            logger.info(f"MemoryStorage: Initializing ChromaDB at {self.db_path}...")
            self.chroma_client = chromadb.PersistentClient(path=self.db_path)
            
            if self.api_key:
                emb_fn = embedding_functions.OpenAIEmbeddingFunction(
                    api_key=self.api_key,
                    model_name=self.embedding_model,
                    api_base=self.api_base
                )
            else:
                logger.error("MemoryStorage: No OpenAI Key found! Falling back to default embedding.")
                emb_fn = None

            self.collection = self.chroma_client.get_or_create_collection(
                name="bea_diary",
                embedding_function=cast(Any, emb_fn),
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"MemoryStorage: ChromaDB initialized. Count: {self.collection.count()}")
            return True
            
        except Exception as e:
            logger.error(f"MemoryStorage: Error initializing: {e}")
            return False

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
