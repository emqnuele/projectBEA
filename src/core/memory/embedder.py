"""Local, in-process embeddings (fastembed / ONNX on CPU).

Lazy: the model (~220MB) is fetched on the first `embed`, so startup does not
wait for it — `bea --setup` offers to get it out of the way beforehand. Two
methods only, so a test can inject a deterministic fake.

The default is multilingual: with an English-only model, non-English sentences
collapse into the same region and retrieval becomes close to random.
"""

import warnings
from importlib import metadata
from typing import Any, List, Optional, Sequence

from src.core.perf import perf_enabled, physical_cores
from src.utils.huggingface import download_hint
from src.utils.logger import get_logger

logger = get_logger("bea.memory.embedder")

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_CACHE_DIR = "data/embeddings_cache"

# old config values meaning "the default": fastembed rejects them
_LEGACY_NAMES = frozenset({"local", "default", "", "none"})


def _fastembed_series() -> str:
    """`major.minor` of the installed fastembed, or "?" when it cannot be read.

    Patch releases are left out on purpose: the pooling of a model is the kind
    of thing that moves in a minor, and re-embedding a whole store on a bugfix
    would be a long startup for nothing.
    """
    try:
        return ".".join(metadata.version("fastembed").split(".")[:2])
    except Exception as e:
        logger.warning(f"Could not read the fastembed version ({e}).")
        return "?"


def resolve_model(name: Optional[str]) -> str:
    """The model to actually load, migrating the pre-sqlite config values."""
    candidate = (name or "").strip()
    if candidate.lower() in _LEGACY_NAMES:
        if candidate:
            logger.info(f"Embedding model '{candidate}' is from the old config; "
                        f"using {DEFAULT_MODEL}.")
        return DEFAULT_MODEL
    return candidate


def _threads() -> Optional[int]:
    """What the onnx pool is sized with. None means the library's default."""
    return physical_cores() if perf_enabled() else None


class FastEmbedEmbedder:
    def __init__(self, model_name: Optional[str] = DEFAULT_MODEL,
                 cache_dir: Optional[str] = DEFAULT_CACHE_DIR) -> None:
        self.model_name = resolve_model(model_name)
        self.cache_dir = cache_dir
        self._model: Optional[Any] = None
        self._dim: Optional[int] = None
        self._explained = False

    def _ensure(self) -> Any:
        """The loaded model, loading it the first time. Returned, not just set,
        so a caller has the thing itself rather than a promise that it is there."""
        if self._model is not None:
            return self._model
        from fastembed import TextEmbedding  # lazy: heavy import

        logger.info(f"Loading embedding model '{self.model_name}'…")
        try:
            with warnings.catch_warnings():
                # fastembed warns that it pools this model differently than it
                # used to. That is handled — `identity` carries the version, so
                # the store re-embeds — and printing a raw traceback about it on
                # every start reads like something is broken
                warnings.filterwarnings("ignore", message=".*mean pooling.*")
                kwargs: dict = {}
                threads = _threads()
                if threads is not None:
                    kwargs["threads"] = threads
                self._model = TextEmbedding(model_name=self.model_name,
                                           cache_dir=self.cache_dir, **kwargs)
        except Exception as error:
            # the caller writes the memory anyway, without a vector, and comes
            # back for another try — so the explanation is said once, not once
            # per thing she remembers
            hint = download_hint(error)
            if hint and not self._explained:
                self._explained = True
                logger.error(hint)
            raise
        return self._model

    @property
    def identity(self) -> str:
        """What the stored vectors were made with, not merely which model.

        The same model name does not mean the same vector space: fastembed 0.6
        began mean-pooling the sentence-transformers models it used to read the
        CLS token of, which left every memory written before it in a space the
        new queries cannot be compared against. Nothing said so — recall simply
        got worse. Carrying the version here makes that a re-embed, which is
        what a changed model has always been.
        """
        return f"{self.model_name}@fastembed{_fastembed_series()}"

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        model = self._ensure()
        return [list(map(float, v)) for v in model.embed(list(texts))]

    @property
    def dim(self) -> int:
        """How wide the vectors are — looked up, not measured.

        This is asked for while the memory store is being wired, which is
        startup. Measuring it meant embedding a throwaway string, which meant
        loading the model, which on a fresh install meant downloading 220MB
        before she had said anything — the exact wait this module's laziness
        exists to avoid, undone by the one caller that only wanted a number.

        fastembed's own catalogue knows the width of every model it ships. A
        model that is not in it is someone's own repository, and for that there
        is still nothing to do but ask the model itself.
        """
        if self._dim is None:
            self._dim = self._declared_dim() or len(self.embed(["dim probe"])[0])
        return self._dim

    def _declared_dim(self) -> Optional[int]:
        try:
            from fastembed import TextEmbedding

            for model in TextEmbedding.list_supported_models():
                if model.get("model") == self.model_name:
                    return int(model["dim"])
        except Exception as e:
            logger.debug(f"Could not read the width of '{self.model_name}' ({e}).")
        return None
