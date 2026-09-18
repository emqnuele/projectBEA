"""The one place that knows how to build a voice.

Same shape as `avatar/factory.py` and `llm/factory.py`. It exists because the
engine was not the only thing that needed to build one: the diagnostic has to
build the *same* voice the engine would, or it is testing something else.

Which voice that is comes from `providers.voice_for`, not from each builder
reading its own field: the language policy lives in one place, and a builder is
only the two or three lines that hand an engine what it needs.

Imports live inside the builders, so choosing EdgeTTS never pays for loading
onnxruntime.
"""

from typing import Callable, Dict

from src.interfaces.base_interfaces import TTSInterface
from src.modules.tts import providers
from src.utils.logger import get_logger

logger = get_logger("bea.tts.factory")

DEFAULT_BACKEND = providers.DEFAULT_PROVIDER


def _edge(config, voice: providers.Voice) -> TTSInterface:
    from src.modules.tts.edge_tts_wrapper import EdgeTTSWrapper
    return EdgeTTSWrapper(voice=voice.id, pitch=config.tts_pitch,
                          rate=config.tts_rate, volume=config.tts_volume)


def _kokoro(config, voice: providers.Voice) -> TTSInterface:
    from src.modules.tts.kokoro_tts_wrapper import KokoroTTSWrapper
    return KokoroTTSWrapper(model_path=config.kokoro_model,
                            voices_path=config.kokoro_voices_file,
                            voice=voice.id, speed=config.kokoro_speed,
                            lang=kokoro_language(config))


def _orpheus(config, voice: providers.Voice) -> TTSInterface:
    from src.modules.tts.orpheus_tts_wrapper import OrpheusTTSWrapper
    return OrpheusTTSWrapper(api_key=config.orpheus_key,
                             endpoint_url=config.orpheus_endpoint,
                             voice=voice.id)


BUILDERS: Dict[str, Callable[..., TTSInterface]] = {
    "edge": _edge,
    "kokoro": _kokoro,
    "orpheus": _orpheus,
}


def kokoro_language(config) -> str:
    """Which language Kokoro phonemises in, derived rather than configured.

    `kokoro_lang` is still read, because a config.json that set it meant it —
    but only as the fallback. The voice is the better answer: `if_sara` is
    Italian whatever the field says, and the two drifting apart is how the
    engine ended up reading Italian with an English phonemiser.
    """
    kokoro = providers.PROVIDERS["kokoro"]
    voice = providers.voice_for(config)
    spoken = providers.language_of(kokoro, voice.id)
    if spoken == providers.AUTO:
        spoken = getattr(config, "language", "")
    return providers.engine_language(kokoro, spoken) \
        or str(getattr(config, "kokoro_lang", "") or "en-us")


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
    voice = providers.voice_for(config)
    tts = BUILDERS[name](config, voice)
    logger.info(f"TTS backend: {name}, voice {voice.id!r}.")
    for warning in providers.warnings(config):
        logger.warning(warning)
    return tts
