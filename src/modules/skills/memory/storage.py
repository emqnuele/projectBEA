import chromadb
from chromadb.utils import embedding_functions
from rich.console import Console
import time
from typing import Optional, List, Dict

console = Console()

class MemoryStorage:
    def __init__(self, db_path: str, openai_key: Optional[str], embedding_model: str):
        self.db_path = db_path
        self.openai_key = openai_key
        self.embedding_model = embedding_model
        self.chroma_client = None
        self.collection = None

    def initialize(self):
        try:
            console.print(f"[magenta]MemoryStorage: Initializing ChromaDB at {self.db_path}...[/magenta]")
            self.chroma_client = chromadb.PersistentClient(path=self.db_path)
            
            if self.openai_key:
                emb_fn = embedding_functions.OpenAIEmbeddingFunction(
                    api_key=self.openai_key,
                    model_name=self.embedding_model
                )
            else:
                console.print("[red]MemoryStorage: No OpenAI Key found! Falling back to default embedding.[/red]")
                emb_fn = None

            self.collection = self.chroma_client.get_or_create_collection(
                name="bea_diary",
                embedding_function=emb_fn,
                metadata={"hnsw:space": "cosine"}
            )
            console.print(f"[green]MemoryStorage: ChromaDB initialized. Count: {self.collection.count()}[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]MemoryStorage: Error initializing: {e}[/red]")
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
