"""Local, in-process embeddings (fastembed / ONNX on CPU).

Lazy: the model (~100MB) is fetched on the first `embed`, so startup does not
wait for it. Two methods only, so a test can inject a deterministic fake.

The default is multilingual: with an English-only model, non-English sentences
collapse into the same region and retrieval becomes close to random.
"""

from typing import List, Optional, Sequence

from src.utils.logger import get_logger

logger = get_logger("bea.memory.embedder")

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_CACHE_DIR = "data/embeddings_cache"

# old config values meaning "the default": fastembed rejects them
_LEGACY_NAMES = frozenset({"local", "default", "", "none"})


def resolve_model(name: Optional[str]) -> str:
    """The model to actually load, migrating the pre-sqlite config values."""
    candidate = (name or "").strip()
    if candidate.lower() in _LEGACY_NAMES:
        if candidate:
            logger.info(f"Embedding model '{candidate}' is from the old config; "
                        f"using {DEFAULT_MODEL}.")
        return DEFAULT_MODEL
    return candidate


class FastEmbedEmbedder:
    def __init__(self, model_name: str = DEFAULT_MODEL,
                 cache_dir: Optional[str] = DEFAULT_CACHE_DIR) -> None:
        self.model_name = resolve_model(model_name)
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
