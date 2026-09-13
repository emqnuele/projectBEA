"""The one place that knows how to build a voice.

Same shape as `avatar/factory.py` and `llm/factory.py`. It exists because the
engine was not the only thing that needed to build one: the diagnostic has to
build the *same* voice the engine would, or it is testing something else.

Imports live inside the builders, so choosing EdgeTTS never pays for loading
onnxruntime.
"""

from typing import Callable, Dict

from src.interfaces.base_interfaces import TTSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.tts.factory")

DEFAULT_BACKEND = "edge"


def _edge(config) -> TTSInterface:
    from src.modules.tts.edge_tts_wrapper import EdgeTTSWrapper
    return EdgeTTSWrapper(voice=config.tts_voice, pitch=config.tts_pitch,
                          rate=config.tts_rate, volume=config.tts_volume)


def _kokoro(config) -> TTSInterface:
    from src.modules.tts.kokoro_tts_wrapper import KokoroTTSWrapper
    return KokoroTTSWrapper(model_path=config.kokoro_model,
                            voices_path=config.kokoro_voices_file,
                            voice=config.kokoro_voice, speed=config.kokoro_speed,
                            lang=config.kokoro_lang)


def _orpheus(config) -> TTSInterface:
    from src.modules.tts.orpheus_tts_wrapper import OrpheusTTSWrapper
    return OrpheusTTSWrapper(api_key=config.orpheus_key,
                             endpoint_url=config.orpheus_endpoint,
                             voice=config.orpheus_voice)


BUILDERS: Dict[str, Callable[..., TTSInterface]] = {
    "edge": _edge,
    "kokoro": _kokoro,
    "orpheus": _orpheus,
}


def backend_name(config) -> str:
    """The configured engine, or the default when it is not one we have."""
    name = getattr(config, "tts_provider", DEFAULT_BACKEND)
    if name in BUILDERS:
        return name
    # a typo in config.json must not leave her mute for a whole stream
    logger.warning(
        f"Unknown TTS provider {name!r}; falling back to {DEFAULT_BACKEND!r}. "
        f"Valid: {', '.join(sorted(BUILDERS))}."
    )
    return DEFAULT_BACKEND


def build_tts(config) -> TTSInterface:
    name = backend_name(config)
    tts = BUILDERS[name](config)
    logger.info(f"TTS backend: {name}")
    return tts
