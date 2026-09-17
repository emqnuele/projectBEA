"""Pulling the weights down while someone is still watching.

Two models arrive from Hugging Face on a fresh install: whisper, the first time
she hears anything, and the embedder, the first time she remembers anything.
Both are lazy on purpose — startup should not wait for a download — but on a
fresh clone that means her first sentence, or her first memory, silently taking
a minute. Doing it here costs the same minute in the one place where it looks
like progress rather than a hang.

Nothing here is required. Every failure is a warning: the engine fetches what
is missing on first use exactly as it did before.

The whisper half lives in the transcriber, next to the code that reads the same
folder — the wizard and the engine disagreeing about where the weights go is
precisely the bug this module used to have.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional

from src.core.memory.embedder import DEFAULT_CACHE_DIR, FastEmbedEmbedder, resolve_model
from src.modules.STT.factory import LOCAL as STT_LOCAL
from src.modules.STT.faster_whisper_stt import WEIGHTS_MB, fetch_weights, normalize_model, weights_here
from src.utils.huggingface import watched

EMBEDDER_FALLBACK_MB = 220

DEFAULT_WHISPER_ROOT = "data/models/whisper"


# --- the embedder -----------------------------------------------------------


def embedder_mb(model: Optional[str] = None) -> int:
    """What the embedding model weighs, asked of fastembed's own catalogue."""
    wanted = resolve_model(model)
    try:
        from fastembed import TextEmbedding

        for known in TextEmbedding.list_supported_models():
            if known["model"] == wanted:
                return round(float(known["size_in_GB"]) * 1000)
    except Exception:
        pass
    return EMBEDDER_FALLBACK_MB


def embedder_here(cache_dir: str = DEFAULT_CACHE_DIR) -> bool:
    """Whether an ONNX model is already cached.

    fastembed has no offline probe and the layout of its cache is its own
    business — but nothing else puts an .onnx file in there.
    """
    return any(Path(cache_dir).rglob("*.onnx")) if Path(cache_dir).is_dir() else False


def fetch_embedder(model: Optional[str] = None, cache_dir: str = DEFAULT_CACHE_DIR,
                   loader: Optional[Callable[[], Any]] = None,
                   on_progress: Optional[Callable[[int], None]] = None,
                   tick: float = 0.3) -> Optional[Exception]:
    """Embeds one throwaway sentence, which is what downloads the model.

    Going through `embed` rather than the loader alone means a model that
    arrived but cannot run is found here, not at her first memory.
    """
    load = loader or (lambda: FastEmbedEmbedder(model, cache_dir).embed(["warm-up"]))
    return watched(load, cache_dir, on_progress, tick)


# --- what this machine is missing --------------------------------------------


@dataclass(frozen=True)
class Job:
    """One download the wizard is about to offer, and how to run it."""

    label: str
    root: str
    megabytes: int
    fetch: Callable[[Callable[[int], None]], Optional[Exception]]


def plan(config, answers: Optional[dict] = None) -> List[Job]:
    """The weights this machine does not have yet, given what was just chosen.

    Pure enough to test: it reads the config and the answers and touches the
    disk only to ask whether each model is already there. Her memory needs the
    embedder whether or not anything else was armed, so that one is not tied to
    any answer.
    """
    answers = answers or {}
    jobs: List[Job] = []

    model = normalize_model(answers.get("stt_model") or config.stt_model)
    root = config.faster_whisper_download_root or DEFAULT_WHISPER_ROOT
    provider = answers.get("stt_provider", config.stt_provider)
    if provider in STT_LOCAL and not weights_here(model, root):
        jobs.append(Job(
            f"whisper {model}", root, WEIGHTS_MB.get(model, 0),
            lambda report, model=model, root=root: fetch_weights(model, root,
                                                                 on_progress=report),
        ))

    memory = config.skills.get("memory", {})
    cache = memory.get("embedding_cache_dir") or DEFAULT_CACHE_DIR
    embedder = memory.get("embedding_model")
    if memory.get("enabled", True) and not embedder_here(cache):
        jobs.append(Job(
            "her memory's embedder", cache, embedder_mb(embedder),
            lambda report, embedder=embedder, cache=cache: fetch_embedder(
                embedder, cache, on_progress=report),
        ))

    return jobs
