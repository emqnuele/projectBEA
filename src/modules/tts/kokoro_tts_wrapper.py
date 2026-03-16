import os
import requests
import sounddevice as sd
import soundfile as sf
import numpy as np
import asyncio
from kokoro_onnx import Kokoro
from src.interfaces.base_interfaces import TTSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.tts.kokoro")

class KokoroTTSWrapper(TTSInterface):
    URL_MODEL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx"
    URL_VOICES = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.bin"

    def __init__(self, model_path: str, voices_path: str, voice: str = "af_bella", speed: float = 1.0, lang: str = "en-us"):
        self.model_path = model_path
        self.voices_path = voices_path
        self.voice = voice
        self.speed = speed
        self.lang = lang
        self.kokoro = None

        self._ensure_models_exist()
        self._initialize_model()

    def _ensure_models_exist(self):
        """Downloads model files if they are missing."""
        self._download_file(self.URL_MODEL, self.model_path)
        self._download_file(self.URL_VOICES, self.voices_path)

    def _download_file(self, url, filename):
        if not os.path.exists(filename):
            logger.info(f"downloading {filename}...")
            try:
                with requests.get(url, stream=True) as r:
                    r.raise_for_status()
                    with open(filename, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                logger.info(f"{filename} downloaded!")
            except Exception as e:
                logger.error(f"error downloading {filename}: {e}")
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
        if config.kokoro_voice != self.voice:
            logger.info(f"voice updated to {config.kokoro_voice}")
            self.voice = config.kokoro_voice
        
        if config.kokoro_speed != self.speed:
            logger.info(f"speed updated to {config.kokoro_speed}")
            self.speed = config.kokoro_speed
        
        if config.kokoro_lang != self.lang:
             logger.info(f"language updated to {config.kokoro_lang}")
             self.lang = config.kokoro_lang

    async def generate_audio(self, text: str) -> tuple[np.ndarray, int]:
        if not text or not self.kokoro:
            return np.zeros(0, dtype=np.float32), 24000

        # run generation in thread to avoid blocking loop
        loop = asyncio.get_event_loop()
        samples, sample_rate = await loop.run_in_executor(
            None, 
            self.kokoro.create, 
            text, 
            self.voice, 
            self.speed, 
            self.lang
        )
        
        # Ensure format
        if not isinstance(samples, np.ndarray):
            samples = np.array(samples, dtype=np.float32)
        if samples.dtype != np.float32:
             samples = samples.astype(np.float32)
             
        return samples, sample_rate

    async def speak(self, text: str, output_device_id: int) -> None:
        # deprecated: brain should use generate_audio and handle playback
        # kept for compatibility or direct usage
        samples, sample_rate = await self.generate_audio(text)
        if len(samples) == 0:
            return

        try:
             # play using sounddevice (non-blocking + sleep)
            if samples.ndim == 1:
                channels = 1
            else:
                channels = samples.shape[1]
            
            sd.play(samples, samplerate=sample_rate, device=output_device_id, blocking=False)
            
            # manual sleep async
            duration = len(samples) / sample_rate
            await asyncio.sleep(duration)
        except Exception as e:
            logger.error(f"error during playback: {e}")
