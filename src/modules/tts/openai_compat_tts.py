"""A voice from any server speaking OpenAI's `/audio/speech`.

Kokoro-FastAPI, speaches, LocalAI, openedai-speech, OpenAI itself. The answer
is asked for as wav rather than raw pcm: pcm carries no sample rate, and the
rate a server picked is not something to guess. The header is read off the
front of the stream and everything after it is played as it arrives.
"""

import asyncio
import contextlib
import io
import struct
import threading
from typing import Iterator, Optional, Tuple

import numpy as np
import requests
import soundfile as sf

from src.interfaces.base_interfaces import TTSInterface
from src.modules.STT.openrouter_stt import _stale
from src.utils.logger import get_logger
from src.utils.warm import Warmer

logger = get_logger("bea.tts.openai_compat")

CONNECT_TIMEOUT_S = 10.0
READ_TIMEOUT_S = 60.0
_TIMEOUT = (CONNECT_TIMEOUT_S, READ_TIMEOUT_S)

# a header bigger than this is not one this parser understands
MAX_HEADER_BYTES = 64 * 1024
# counted in speech, not bytes, so a server's sample rate cannot move when she starts
BLOCK_SECONDS = 0.15

_abandoned: set = set()


def speech_url(base_url: str) -> str:
    return base_url.strip().rstrip("/") + "/audio/speech"


def parse_wav_header(buffer: bytes) -> Optional[Tuple[int, int, int, int, int]]:
    """(format tag, channels, rate, bits, offset of the samples), or None until it is all here.

    The data chunk's size is not trusted: a streamed wav is written before its
    length is known, and servers fill it with zero or 0xFFFFFFFF.
    Raises ValueError on something that is not a wav.
    """
    if len(buffer) < 12:
        return None
    if buffer[:4] != b"RIFF" or buffer[8:12] != b"WAVE":
        raise ValueError("not a wav")
    pos = 12
    fmt = None
    while pos + 8 <= len(buffer):
        chunk_id = buffer[pos:pos + 4]
        size = struct.unpack("<I", buffer[pos + 4:pos + 8])[0]
        body = pos + 8
        if chunk_id == b"data":
            if fmt is None:
                raise ValueError("wav data before its format")
            return (*fmt, body)
        if body + size > len(buffer):
            return None
        if chunk_id == b"fmt ":
            tag, channels, rate = struct.unpack("<HHI", buffer[body:body + 8])
            bits = struct.unpack("<H", buffer[body + 14:body + 16])[0]
            if tag == 0xFFFE and size >= 26:
                # extensible: the real tag is the first two bytes of the subformat guid
                tag = struct.unpack("<H", buffer[body + 24:body + 26])[0]
            fmt = (tag, channels, rate, bits)
        # chunks are padded to an even length
        pos = body + size + (size & 1)
    return None


def decode_samples(raw: bytes, tag: int, channels: int, bits: int) -> np.ndarray:
    """Interleaved samples to mono float32. Only what servers actually send."""
    if tag == 1 and bits == 16:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif tag == 1 and bits == 32:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif tag == 3 and bits == 32:
        samples = np.frombuffer(raw, dtype="<f4").astype(np.float32)
    else:
        raise ValueError(f"unsupported wav encoding (tag {tag}, {bits} bit)")
    if channels > 1:
        samples = samples[: len(samples) - len(samples) % channels]
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples


class OpenAICompatTTSWrapper(TTSInterface):
    # the protocol has speed and nothing else: the mood's rate rides on it, its
    # volume is applied here, and its pitch cannot be said
    pieces_in_flight = 2

    def __init__(self, base_url: str, api_key: Optional[str], model: str,
                 voice: str, speed: float = 1.0):
        self.base_url = (base_url or "").strip()
        self.api_key = api_key or ""
        self.model = model
        self.voice = voice
        self.speed = speed
        self.client = requests.Session()
        self.warm = Warmer(self._open_connection)
        if not self.base_url:
            logger.error("tts_compat_base_url is not set; she will be silent.")

    def reload_config(self, config) -> None:
        from src.modules.tts.providers import voice_for

        self.base_url = (config.tts_compat_base_url or "").strip()
        self.api_key = config.tts_compat_key or ""
        self.model = config.tts_compat_model
        self.speed = config.tts_compat_speed
        chosen = voice_for(config).id
        if chosen and chosen != self.voice:
            logger.info(f"voice updated to {chosen}")
            self.voice = chosen

    def _payload(self, text: str, prosody=None) -> dict:
        payload = {"model": self.model, "input": text, "voice": self.voice,
                   "response_format": "wav"}
        speed = (self.speed or 1.0) * (prosody.rate if prosody is not None else 1.0)
        # left out at its default: a server that does not know the field may refuse it
        if abs(speed - 1.0) > 1e-3:
            payload["speed"] = round(speed, 3)
        return payload

    def _post(self, text: str, prosody=None, stream: bool = False):
        """One request, sent again once if the kept connection had gone."""
        url = speech_url(self.base_url)
        headers, payload = self._headers(), self._payload(text, prosody)
        try:
            return self.client.post(url, headers=headers, json=payload,
                                    stream=stream, timeout=_TIMEOUT)
        except requests.ConnectionError as e:
            if not _stale(e):
                raise
            logger.debug(f"the kept connection had gone ({e}); sending again")
            return self.client.post(url, headers=headers, json=payload,
                                    stream=stream, timeout=_TIMEOUT)

    def _open_connection(self) -> None:
        # any answer will do, a 405 included: what is kept is the socket
        if self.base_url:
            self.client.head(speech_url(self.base_url), timeout=(CONNECT_TIMEOUT_S, 5.0)).close()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _stream_sync(self, text: str, prosody=None, stop: Optional[threading.Event] = None,
                     opened: Optional[list] = None) -> Iterator[Tuple[np.ndarray, int]]:
        if not self.base_url:
            logger.error("No endpoint configured.")
            return

        with self._post(text, prosody, stream=True) as resp:
            if opened is not None:
                opened.append(resp)
            if resp.status_code != 200:
                raise RuntimeError(f"{resp.status_code}: {resp.text[:300]}")

            pending = b""
            fmt = None
            frame = 0
            block = 0
            for chunk in resp.iter_content(chunk_size=4096):
                if stop is not None and stop.is_set():
                    return
                if not chunk:
                    continue
                pending += chunk
                if fmt is None:
                    header = parse_wav_header(pending)
                    if header is None:
                        if len(pending) > MAX_HEADER_BYTES:
                            raise ValueError("no wav data chunk in the first 64 KB")
                        continue
                    tag, channels, rate, bits, offset = header
                    fmt = (tag, channels, rate, bits)
                    frame = channels * bits // 8
                    if not frame or not rate:
                        raise ValueError("wav header with no frame size or rate")
                    block = max(frame, int(rate * BLOCK_SECONDS) * frame)
                    pending = pending[offset:]
                if len(pending) >= block:
                    # never on a partial frame: half a sample is a click
                    cut = len(pending) - len(pending) % frame
                    yield decode_samples(pending[:cut], fmt[0], fmt[1], fmt[3]), fmt[2]
                    pending = pending[cut:]
            if fmt is not None and len(pending) >= frame:
                cut = len(pending) - len(pending) % frame
                yield decode_samples(pending[:cut], fmt[0], fmt[1], fmt[3]), fmt[2]

    async def generate_stream(self, text: str, prosody=None):
        if not text:
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        stop = threading.Event()
        opened: list = []

        def pump():
            try:
                for block in self._stream_sync(text, prosody, stop, opened):
                    loop.call_soon_threadsafe(queue.put_nowait, block)
            except Exception as e:
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
                yield _louder(block[0], prosody), block[1]
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

    def _whole_sync(self, text: str, prosody=None) -> Tuple[np.ndarray, int]:
        resp = self._post(text, prosody)
        if resp.status_code != 200:
            raise RuntimeError(f"{resp.status_code}: {resp.text[:300]}")
        data, rate = sf.read(io.BytesIO(resp.content), dtype="float32", always_2d=True)
        return _louder(data.mean(axis=1), prosody), rate

    async def generate_audio(self, text: str, prosody=None) -> Tuple[np.ndarray, int]:
        if not text or not self.base_url:
            return np.zeros(0, dtype=np.float32), 24000
        try:
            return await asyncio.to_thread(self._whole_sync, text, prosody)
        except Exception as e:
            logger.error(f"synthesis failed: {e}")
            return np.zeros(0, dtype=np.float32), 24000


def _louder(samples: np.ndarray, prosody) -> np.ndarray:
    """The mood's volume, applied here because the protocol has no field for it."""
    if prosody is None or prosody.volume == 1.0:
        return samples
    return np.clip(samples * prosody.volume, -1.0, 1.0).astype(np.float32)
