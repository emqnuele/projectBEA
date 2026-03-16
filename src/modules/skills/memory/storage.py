import chromadb
from chromadb.utils import embedding_functions
import time
from typing import Optional, List, Dict
from src.utils.logger import get_logger

logger = get_logger("bea.skills.memory.storage")

class MemoryStorage:
    def __init__(self, db_path: str, openai_key: Optional[str], embedding_model: str):
        self.db_path = db_path
        self.openai_key = openai_key
        self.embedding_model = embedding_model
        self.chroma_client = None
        self.collection = None

    def initialize(self):
        try:
            logger.info(f"MemoryStorage: Initializing ChromaDB at {self.db_path}...")
            self.chroma_client = chromadb.PersistentClient(path=self.db_path)
            
            if self.openai_key:
                emb_fn = embedding_functions.OpenAIEmbeddingFunction(
                    api_key=self.openai_key,
                    model_name=self.embedding_model
                )
            else:
                logger.error("MemoryStorage: No OpenAI Key found! Falling back to default embedding.")
                emb_fn = None

            self.collection = self.chroma_client.get_or_create_collection(
                name="bea_diary",
                embedding_function=emb_fn,
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
