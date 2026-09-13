"""The one place that knows how to build her ears.

`None` is a valid answer and the default one: she is perfectly usable typed
at, and a transcriber nobody configured should not be a startup error.
"""

from typing import Callable, Dict, Optional

from src.interfaces.base_interfaces import STTInterface
from src.utils.logger import get_logger

logger = get_logger("bea.stt.factory")


def _groq(config) -> STTInterface:
    from src.modules.STT.groq_stt import GroqSTT
    return GroqSTT(config)


def _openrouter(config) -> STTInterface:
    from src.modules.STT.openrouter_stt import OpenRouterSTT
    return OpenRouterSTT(config)


def _faster_whisper(config) -> STTInterface:
    from src.modules.STT.faster_whisper_stt import FasterWhisperSTT
    return FasterWhisperSTT(config)


BUILDERS: Dict[str, Callable[..., STTInterface]] = {
    "groq": _groq,
    "openrouter": _openrouter,
    "faster_whisper": _faster_whisper,
}

# providers that run on this machine, so nothing above should look for a key
LOCAL = frozenset({"faster_whisper"})


def build_stt(config) -> Optional[STTInterface]:
    """Her ears, or None when she is not set up to have any."""
    name = getattr(config, "stt_provider", "") or ""
    if not name:
        return None
    builder = BUILDERS.get(name)
    if builder is None:
        logger.warning(f"Unknown STT provider {name!r}; she will not hear voice input. "
                       f"Valid: {', '.join(sorted(BUILDERS))}.")
        return None
    stt = builder(config)
    logger.info(f"STT backend: {name}")
    return stt
