import os

import edge_tts
import numpy as np
import soundfile as sf

from src.core.expression.prosody import combine_hz, combine_percent
from src.interfaces.base_interfaces import TTSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.tts.edge")

class EdgeTTSWrapper(TTSInterface):
    def __init__(self, voice: str = "en-US-JennyNeural", pitch: str = "+0Hz", rate: str = "+0%", volume: str = "+0%"):
        self.voice = voice
        self.pitch = pitch
        self.rate = rate
        self.volume = volume

    def reload_config(self, config) -> None:
        # asked for rather than read off the config: which voice a setup means
        # is one decision, made in `tts/providers.py` for every engine at once
        from src.modules.tts.providers import voice_for

        chosen = voice_for(config).id
        if chosen and chosen != self.voice:
            logger.info(f"voice updated to {chosen}")
            self.voice = chosen
        if config.tts_pitch != self.pitch:
             self.pitch = config.tts_pitch
        if config.tts_rate != self.rate:
             self.rate = config.tts_rate
        if config.tts_volume != self.volume:
             self.volume = config.tts_volume

    def _voice_for(self, prosody) -> tuple[str, str, str]:
        """The configured voice, moved by the mood. Neutral leaves it untouched."""
        if prosody is None or prosody.neutral:
            return self.pitch, self.rate, self.volume
        return (
            combine_hz(self.pitch, prosody.pitch_hz),
            combine_percent(self.rate, prosody.rate),
            combine_percent(self.volume, prosody.volume),
        )

    async def generate_audio(self, text: str, prosody=None) -> tuple[np.ndarray, int]:
        """Generates audio and returns numpy array + sample rate."""
        if not text:
             return np.zeros(0, dtype=np.float32), 24000

        import uuid
        unique_filename = f"temp_tts_{uuid.uuid4().hex}.mp3"

        try:
            # generate to file
            pitch, rate, volume = self._voice_for(prosody)
            communicate = edge_tts.Communicate(text, self.voice, pitch=pitch, rate=rate, volume=volume)
            await communicate.save(unique_filename)

            # read to numpy
            data, fs = sf.read(unique_filename, dtype='float32')
            return data, fs

        except Exception as e:
            logger.error(f"generation error: {e}")
            return np.zeros(0, dtype=np.float32), 24000
        finally:
             if os.path.exists(unique_filename):
                try:
                    os.remove(unique_filename)
                except OSError:
                    pass
