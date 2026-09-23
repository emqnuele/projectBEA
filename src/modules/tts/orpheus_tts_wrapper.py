import asyncio
import contextlib
import os
import threading
from typing import Optional

import numpy as np
import requests
import soundfile as sf

from src.interfaces.base_interfaces import TTSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.tts.orpheus")

# held so an abandoned download is not garbage collected mid-way
_abandoned: set = set()

# a connect that never answers cannot be cancelled: the request runs on a
# worker thread, and closing a response that does not exist yet is not a thing.
# A timeout is what ends the wait, so a barge-in during the handshake does not
# leave the thread and its socket behind until the endpoint gives up.
CONNECT_TIMEOUT_S = 10.0
# per read, not per sentence: a stream that keeps arriving never trips this
READ_TIMEOUT_S = 60.0

_TIMEOUT = (CONNECT_TIMEOUT_S, READ_TIMEOUT_S)


class OrpheusTTSWrapper(TTSInterface):
    # the endpoint takes a voice and a prompt and nothing else, so `prosody` is
    # accepted and dropped: this engine cannot be told how to say something
    # what the endpoint returns: raw 24 kHz 16-bit mono
    SAMPLE_RATE = 24000
    # ~150ms a block: small enough to start sounding fast, big enough not to
    # spend the win on per-block overhead
    STREAM_BLOCK_BYTES = 7200
    # remote: the wait is on the endpoint, not on this machine
    pieces_in_flight = 2

    def __init__(self,
                 api_key: Optional[str],
                 endpoint_url: Optional[str],
                 voice: str = "tara"):
        self.api_key = api_key
        self.endpoint_url = endpoint_url
        self.voice = voice
        self.client = requests.Session()

    def reload_config(self, config) -> None:
        if config.orpheus_key != self.api_key:
            self.api_key = config.orpheus_key

        if config.orpheus_endpoint and config.orpheus_endpoint != self.endpoint_url:
            logger.info("endpoint updated.")
            self.endpoint_url = config.orpheus_endpoint

        # one decision, one place: see `tts/providers.py`
        from src.modules.tts.providers import voice_for

        chosen = voice_for(config).id
        if chosen and chosen != self.voice:
            logger.info(f"voice updated to {chosen}")
            self.voice = chosen

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
                stream=True,
                timeout=_TIMEOUT,
            ) as resp:
                resp.raise_for_status()

                with open(filename, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024):
                        if chunk:
                            f.write(chunk)

        except Exception as e:
            logger.error(f"API error: {e}")
            raise

    def _stream_pcm_sync(self, text: str, stop: Optional[threading.Event] = None,
                         opened: Optional[list] = None):
        """Yields raw PCM blocks straight off the response, no file in between.

        The endpoint already answers in chunks of 24 kHz 16-bit mono; the old
        path wrote them to disk and read the whole file back, which threw away
        the one thing that makes a voice start sooner.

        `stop` ends the download between two chunks, and `opened` hands the
        response out so it can be closed under a read that is stalled.
        """
        if not self.api_key or not self.endpoint_url:
            logger.error("API key or endpoint URL is missing.")
            return

        headers = {"Authorization": f"Api-Key {self.api_key}"}
        payload = {"voice": self.voice, "prompt": text, "max_tokens": 10000, "stream": True}

        pending = b""
        with self.client.post(self.endpoint_url, headers=headers, json=payload,
                              stream=True, timeout=_TIMEOUT) as resp:
            if opened is not None:
                opened.append(resp)
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=4096):
                if stop is not None and stop.is_set():
                    return
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
        stop = threading.Event()
        opened: list = []

        def pump():
            try:
                for block in self._stream_pcm_sync(text, stop, opened):
                    loop.call_soon_threadsafe(queue.put_nowait, block)
            except Exception as e:
                # closing the response under it is how an abandoned read ends
                if not stop.is_set():
                    logger.error(f"stream failed: {e}")
            finally:
                with contextlib.suppress(RuntimeError):
                    loop.call_soon_threadsafe(queue.put_nowait, None)

        worker = asyncio.create_task(asyncio.to_thread(pump))
        try:
            while True:
                block = await queue.get()
                if block is None:
                    break
                yield np.frombuffer(block, dtype="<i2").astype(np.float32) / 32768.0, self.SAMPLE_RATE
        finally:
            if worker.done():
                await worker
            else:
                # a barge-in must not wait for audio nobody will hear
                stop.set()
                for resp in opened:
                    with contextlib.suppress(Exception):
                        resp.close()
                _abandoned.add(worker)
                worker.add_done_callback(_abandoned.discard)

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
