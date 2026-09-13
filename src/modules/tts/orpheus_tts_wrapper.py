import asyncio
import os
from typing import Optional

import numpy as np
import requests
import soundfile as sf

from src.interfaces.base_interfaces import TTSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.tts.orpheus")

class OrpheusTTSWrapper(TTSInterface):
    # the endpoint takes a voice and a prompt and nothing else, so `prosody` is
    # accepted and dropped: this engine cannot be told how to say something
    # what the endpoint returns: raw 24 kHz 16-bit mono
    SAMPLE_RATE = 24000
    # ~150ms a block: small enough to start sounding fast, big enough not to
    # spend the win on per-block overhead
    STREAM_BLOCK_BYTES = 7200

    def __init__(self,
                 api_key: Optional[str],
                 endpoint_url: Optional[str],
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
            logger.info("endpoint updated.")
            self.endpoint_url = config.orpheus_endpoint

        if config.orpheus_voice != self.voice:
            logger.info(f"voice updated to {config.orpheus_voice}")
            self.voice = config.orpheus_voice

    def _download_audio_sync(self, text: str, filename: str):
        """downloads audio from baseten to a file."""
        if not self.api_key:
            logger.error("API key is missing.")
            return

        if not self.endpoint_url:
            logger.error("Endpoint URL is missing.")
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
        # imported where it is used, not at module scope: generating audio must
        # not need PortAudio, and a headless box (CI, a server) has no such library
        import sounddevice as sd

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

            sd.play(final_audio, samplerate=fs, device=device_id, blocking=False)

            duration = len(final_audio) / fs
            import time
            time.sleep(duration)

        except Exception as e:
            logger.error(f"error playing audio: {e}")

    def _stream_pcm_sync(self, text: str):
        """Yields raw PCM blocks straight off the response, no file in between.

        The endpoint already answers in chunks of 24 kHz 16-bit mono; the old
        path wrote them to disk and read the whole file back, which threw away
        the one thing that makes a voice start sooner.
        """
        if not self.api_key or not self.endpoint_url:
            logger.error("API key or endpoint URL is missing.")
            return

        headers = {"Authorization": f"Api-Key {self.api_key}"}
        payload = {"voice": self.voice, "prompt": text, "max_tokens": 10000, "stream": True}

        pending = b""
        with self.client.post(self.endpoint_url, headers=headers, json=payload, stream=True) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=4096):
                if not chunk:
                    continue
                pending += chunk
                if len(pending) >= self.STREAM_BLOCK_BYTES:
                    # never on an odd byte: half a sample is a click
                    cut = len(pending) - (len(pending) % 2)
                    yield pending[:cut]
                    pending = pending[cut:]
        if len(pending) >= 2:
            yield pending[:len(pending) - (len(pending) % 2)]

    async def generate_stream(self, text: str, prosody=None):
        """The real thing: samples reach the caller while the rest is still coming."""
        if not text:
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def pump():
            try:
                for block in self._stream_pcm_sync(text):
                    loop.call_soon_threadsafe(queue.put_nowait, block)
            except Exception as e:
                logger.error(f"stream failed: {e}")
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        worker = asyncio.create_task(asyncio.to_thread(pump))
        try:
            while True:
                block = await queue.get()
                if block is None:
                    break
                yield np.frombuffer(block, dtype="<i2").astype(np.float32) / 32768.0, self.SAMPLE_RATE
        finally:
            await worker

    async def generate_audio(self, text: str, prosody=None) -> tuple[np.ndarray, int]:
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
        import sounddevice as sd

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
