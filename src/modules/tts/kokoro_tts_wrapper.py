import asyncio
import os

import numpy as np
import requests
from kokoro_onnx import Kokoro

from src.interfaces.base_interfaces import TTSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.tts.kokoro")

# every file this engine needs lives in the same release, under its own name,
# so the url is the name rather than a second thing to keep in step
RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files"

# The voice pack ships in two formats and the library only reads one of them.
# `voices.bin` is what this wrapper used to download — always, whatever the
# config named the file — so `Kokoro()` got bytes it could not parse, raised,
# and left the engine at None. Kokoro has been silently mute ever since:
# `generate_audio` returns an empty array and nothing above it can tell that
# apart from a line with nothing to say.
LEGACY_VOICES = "voices.bin"
VOICES = "voices.json"


def normalize_voices_file(path: str) -> str:
    """The voice pack, under a name the pinned library can actually read."""
    path = (path or "").strip() or VOICES
    # split on both separators so posix and windows behave the same, and
    # match the name the way the filesystems that hold it do: `Voices.bin`
    # is the same file on macos and windows
    if path.replace("\\", "/").split("/")[-1].lower() != LEGACY_VOICES:
        return path
    fixed = path[: -len(LEGACY_VOICES)] + VOICES
    logger.warning(f"{LEGACY_VOICES} is not a format kokoro-onnx can read; "
                   f"using {fixed} instead.")
    return fixed


def discard_unreadable_voices(path: str) -> None:
    """Delete a voice pack that is not the format the library can read.

    Renaming the file is only half the fix: an install from before it was
    downloaded the binary pack into whatever name the config gave it, so the
    upgrade finds a `voices.json` full of bytes `Kokoro()` cannot parse and
    `os.path.exists` keeps forever. The first byte tells the two apart.
    """
    if not path.lower().endswith(".json") or not os.path.exists(path):
        return
    try:
        with open(path, "rb") as f:
            head = f.read(64).lstrip()
    except OSError as e:
        logger.warning(f"could not read {path}: {e}")
        return
    if head.startswith(b"{"):
        return
    logger.warning(f"{path} is not the json voice pack — it is the old binary "
                   "one under a new name; removing it so it can be fetched again.")
    try:
        os.remove(path)
    except OSError as e:
        logger.error(f"could not remove {path}: {e}")


class KokoroTTSWrapper(TTSInterface):
    def __init__(self, model_path: str, voices_path: str, voice: str = "af_bella", speed: float = 1.0, lang: str = "en-us"):
        self.model_path = model_path
        self.voices_path = normalize_voices_file(voices_path)
        self.voice = voice
        self.speed = speed
        self.lang = lang
        self.kokoro = None

        self._ensure_models_exist()
        self._initialize_model()

    def _ensure_models_exist(self):
        """Downloads model files if they are missing."""
        discard_unreadable_voices(self.voices_path)
        for path in (self.model_path, self.voices_path):
            # split on both separators so posix and windows behave the same
            name = path.replace("\\", "/").split("/")[-1]
            self._download_file(f"{RELEASE}/{name}", path)

    def _download_file(self, url, filename):
        if os.path.exists(filename):
            return
        logger.info(f"downloading {filename}...")
        # written beside the target and moved into place: a download killed
        # half way used to leave a truncated file that `os.path.exists` then
        # accepted forever, which is the same silent muteness by another route
        partial = f"{filename}.part"
        try:
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(partial, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            os.replace(partial, filename)
            logger.info(f"{filename} downloaded!")
        except Exception as e:
            logger.error(f"error downloading {filename}: {e}")
            if os.path.exists(partial):
                os.remove(partial)
            raise

    def _initialize_model(self):
        try:
            logger.info(f"initializing with model={self.model_path}, voices={self.voices_path}")
            self.kokoro = Kokoro(self.model_path, self.voices_path)
            logger.info("initialized successfully.")
        except Exception as e:
            logger.error(f"initialization failed: {e}")
            self.kokoro = None

    def reload_config(self, config) -> None:
        # the voice and the language it is phonemised in are one decision, and
        # it is made in `tts/providers.py` for every engine rather than here
        from src.modules.tts.factory import kokoro_language
        from src.modules.tts.providers import voice_for

        chosen = voice_for(config).id
        if chosen and chosen != self.voice:
            logger.info(f"voice updated to {chosen}")
            self.voice = chosen

        if config.kokoro_speed != self.speed:
            logger.info(f"speed updated to {config.kokoro_speed}")
            self.speed = config.kokoro_speed

        lang = kokoro_language(config)
        if lang and lang != self.lang:
            logger.info(f"language updated to {lang}")
            self.lang = lang

    async def generate_audio(self, text: str, prosody=None) -> tuple[np.ndarray, int]:
        if not text or not self.kokoro:
            return np.zeros(0, dtype=np.float32), 24000

        # rate is the only knob kokoro has; pitch and volume are simply lost
        speed = self.speed if prosody is None else self.speed * prosody.rate

        # run generation in thread to avoid blocking loop
        loop = asyncio.get_running_loop()
        samples, sample_rate = await loop.run_in_executor(
            None,
            self.kokoro.create,
            text,
            self.voice,
            speed,
            self.lang
        )

        # Ensure format
        if not isinstance(samples, np.ndarray):
            samples = np.array(samples, dtype=np.float32)
        if samples.dtype != np.float32:
             samples = samples.astype(np.float32)

        return samples, sample_rate

    async def speak(self, text: str, output_device_id: int) -> None:
        # imported where it is used, not at module scope: generating audio must not
        # need PortAudio, and a headless box (CI, a server) has no such library
        import sounddevice as sd

        # deprecated: brain should use generate_audio and handle playback
        # kept for compatibility or direct usage
        samples, sample_rate = await self.generate_audio(text)
        if len(samples) == 0:
            return

        try:
             # play using sounddevice (non-blocking + sleep)
            sd.play(samples, samplerate=sample_rate, device=output_device_id, blocking=False)

            # manual sleep async
            duration = len(samples) / sample_rate
            await asyncio.sleep(duration)
        except Exception as e:
            logger.error(f"error during playback: {e}")
