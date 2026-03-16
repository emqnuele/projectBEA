import asyncio
import os
import requests
import sounddevice as sd
import soundfile as sf
import numpy as np
from src.interfaces.base_interfaces import TTSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.tts.orpheus")

class OrpheusTTSWrapper(TTSInterface):
    def __init__(self, 
                 api_key: str, 
                 endpoint_url: str, 
                 voice: str = "tara", 
                 output_file: str = "temp_orpheus_tts.wav"):
        self.api_key = api_key
        self.endpoint_url = endpoint_url
        self.voice = voice
        self.output_file = output_file
        self.client = requests.Session()

    def reload_config(self, config) -> None:
        if config.orpheus_key != self.api_key:
            self.api_key = config.orpheus_key

        if config.orpheus_endpoint and config.orpheus_endpoint != self.endpoint_url:
            logger.info(f"endpoint updated.")
            self.endpoint_url = config.orpheus_endpoint

        if config.orpheus_voice != self.voice:
            logger.info(f"voice updated to {config.orpheus_voice}")
            self.voice = config.orpheus_voice

    def _download_audio_sync(self, text: str, filename: str):
        """downloads audio from baseten to a file."""
        if not self.api_key:
            logger.error("API key is missing.")
            return

        headers = {"Authorization": f"Api-Key {self.api_key}"}
        payload = {
            "voice": self.voice,
            "prompt": text,
            "max_tokens": 10000, 
            "stream": True # keep stream=True to get raw bytes
        }

        try:
            with self.client.post(
                self.endpoint_url,
                headers=headers,
                json=payload,
                stream=True
            ) as resp:
                resp.raise_for_status()

                with open(filename, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)
            
        except Exception as e:
            logger.error(f"API error: {e}")
            raise

    def _play_audio_sync(self, device_id: int, filename: str):
        """plays the downloaded audio file assuming Raw PCM 24kHz."""
        if not os.path.exists(filename):
            logger.error("audio file not found.")
            return

        try:
            fs = 24000 
            channels = 1 
            subtype = 'PCM_16' 
            
            data, fs = sf.read(
                filename, 
                samplerate=fs, 
                channels=channels, 
                subtype=subtype, 
                format='RAW',
                dtype='float32'
            )
            
            silence_duration = 0.5
            num_silence_samples = int(fs * silence_duration)
            
            if data.ndim == 1:
                silence = np.zeros(num_silence_samples, dtype='float32')
            else:
                silence = np.zeros((num_silence_samples, data.shape[1]), dtype='float32')
            
            final_audio = np.concatenate((silence, data))
            
            if final_audio.ndim == 1:
                out_channels = 1
            else:
                out_channels = final_audio.shape[1]

            sd.play(final_audio, samplerate=fs, device=device_id, blocking=False)
            
            duration = len(final_audio) / fs
            import time
            time.sleep(duration) 
            
        except Exception as e:
            logger.error(f"error playing audio: {e}")

    async def generate_audio(self, text: str) -> tuple[np.ndarray, int]:
        if not text:
             return np.zeros(0, dtype=np.float32), 24000
        
        import uuid
        unique_filename = f"temp_orpheus_tts_{uuid.uuid4().hex}.wav"

        try:
            logger.info(f"downloading audio for: {text[:30]}...")
            # 1. download
            await asyncio.to_thread(self._download_audio_sync, text, unique_filename)
            
            # 2. read as Raw PCM
            if not os.path.exists(unique_filename):
                return np.zeros(0, dtype=np.float32), 24000
                
            fs = 24000 
            channels = 1 
            subtype = 'PCM_16' 
            
            data, fs = sf.read(
                unique_filename, 
                samplerate=fs, 
                channels=channels, 
                subtype=subtype, 
                format='RAW',
                dtype='float32'
            )
            
            return data, fs

        except Exception as e:
            logger.error(f"pipeline failed: {e}")
            return np.zeros(0, dtype=np.float32), 24000
            
        finally:
            if os.path.exists(unique_filename):
                try:
                    os.remove(unique_filename)
                except OSError:
                    pass

    async def speak(self, text: str, output_device_id: int) -> None:
        # deprecated: brain should use generate_audio
        data, fs = await self.generate_audio(text)
        if len(data) == 0:
            return

        try:
            # initial silence padding
            silence_duration = 0.5
            num_silence_samples = int(fs * silence_duration)
            
            if data.ndim == 1:
                silence = np.zeros(num_silence_samples, dtype='float32')
            else:
                silence = np.zeros((num_silence_samples, data.shape[1]), dtype='float32')
            
            final_audio = np.concatenate((silence, data))
            
            sd.play(final_audio, samplerate=fs, device=output_device_id, blocking=False)
            
            duration = len(final_audio) / fs
            await asyncio.sleep(duration)
            
        except Exception as e:
            logger.error(f"playback error: {e}")
