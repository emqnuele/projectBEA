"""Local, in-process embeddings (fastembed / ONNX on CPU).

Lazy: the model (~100MB) is downloaded and initialized on the first `embed`, so
startup is not held hostage by it. The interface is deliberately tiny — two
methods — so tests can inject a deterministic fake.

The default is MULTILINGUAL on purpose. Bea's people write in Italian; with an
English-only model (Chroma's default was `all-MiniLM-L6-v2`) Italian sentences
collapse into the same region of the space and retrieval becomes close to random.
A multilingual model handles English fine — the reverse is not true.
"""

from typing import List, Optional, Sequence

from src.utils.logger import get_logger

logger = get_logger("bea.memory.embedder")

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_CACHE_DIR = "data/embeddings_cache"


class FastEmbedEmbedder:
    def __init__(self, model_name: str = DEFAULT_MODEL,
                 cache_dir: Optional[str] = DEFAULT_CACHE_DIR) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model = None
        self._dim: Optional[int] = None

    def _ensure(self) -> None:
        if self._model is not None:
            return
        from fastembed import TextEmbedding  # lazy: heavy import

        logger.info(f"Loading embedding model '{self.model_name}'…")
        self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        self._ensure()
        return [list(map(float, v)) for v in self._model.embed(list(texts))]

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._dim = len(self.embed(["dim probe"])[0])
        return self._dim
