import asyncio
import io

import edge_tts
import numpy as np
import soundfile as sf

from src.core.expression.prosody import combine_hz, combine_percent
from src.interfaces.base_interfaces import TTSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.tts.edge")

# the first part of a streamed piece goes once this much mp3 has arrived, a third
# of a second of speech at edge's 48 kbps; each part after it waits for twice as
# much, so a sentence costs a handful of decodes rather than one per chunk
FIRST_PART_BYTES = 2048

class EdgeTTSWrapper(TTSInterface):
    # every piece is a new connection and most of a second of waiting on it
    pieces_in_flight = 2

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
        """Generates audio and returns numpy array + sample rate.

        The mp3 is gathered in memory and decoded on a worker thread. It used to
        go to a file and be read back and decoded on the event loop — every
        sentence stalled everything else she was doing, the rest of her own
        line included, for the length of a decode.
        """
        if not text:
             return np.zeros(0, dtype=np.float32), 24000

        try:
            pitch, rate, volume = self._voice_for(prosody)
            communicate = edge_tts.Communicate(text, self.voice, pitch=pitch, rate=rate, volume=volume)
            mp3 = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3 += chunk.get("data", b"")
            data, fs = await asyncio.to_thread(_decode, bytes(mp3))
            return data, fs

        except Exception as e:
            logger.error(f"generation error: {e}")
            return np.zeros(0, dtype=np.float32), 24000

    async def generate_stream(self, text: str, prosody=None):
        """The same samples as `generate_audio`, handed over as they arrive.

        An mp3 cut at any byte decodes to exactly the start of what the whole
        file decodes to — checked bit for bit on edge's own output — so each
        part is the next stretch of the very same audio, only sooner: the room
        can be hearing the start of a sentence while the end of it is still on
        the wire.
        """
        if not text:
            return
        try:
            pitch, rate, volume = self._voice_for(prosody)
            communicate = edge_tts.Communicate(text, self.voice, pitch=pitch, rate=rate, volume=volume)
            mp3 = bytearray()
            sent = 0
            due = FIRST_PART_BYTES
            previous = None
            broken = False
            async for chunk in communicate.stream():
                if chunk["type"] != "audio":
                    continue
                mp3 += chunk.get("data", b"")
                if len(mp3) < due:
                    continue
                due = len(mp3) * 2
                try:
                    data, fs = await asyncio.to_thread(_decode, bytes(mp3))
                except Exception:
                    # too short yet to hold a whole frame: the next stretch
                    # decodes it, rather than the sentence costing a decode
                    continue
                if previous is not None and not _prefix_of(previous, data) and not broken:
                    # the invariant the streaming rests on just broke: what was
                    # already handed over is not the start of the whole, so the
                    # room would hear a repeat or a skip. Nothing downstream can
                    # see that, so it is said here, loudly, once
                    broken = True
                    logger.error("edge no longer streams as prefixes of the whole; "
                                 "run tools/edge_prefix_check.py")
                if len(data) > sent:
                    yield data[sent:], fs
                    sent = len(data)
                previous = data
            data, fs = await asyncio.to_thread(_decode, bytes(mp3))
            if previous is not None and not _prefix_of(previous, data) and not broken:
                logger.error("edge no longer streams as prefixes of the whole; "
                             "run tools/edge_prefix_check.py")
            if len(data) > sent:
                yield data[sent:], fs
        except Exception as e:
            logger.error(f"generation error: {e}")


def _prefix_of(previous: np.ndarray, whole: np.ndarray) -> bool:
    """Whether what was already handed over is still the start of the whole."""
    return len(previous) <= len(whole) and bool(np.array_equal(previous, whole[:len(previous)]))


def _decode(mp3: bytes) -> tuple[np.ndarray, int]:
    return sf.read(io.BytesIO(mp3), dtype="float32")
