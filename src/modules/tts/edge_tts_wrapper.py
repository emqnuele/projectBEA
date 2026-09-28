import asyncio
import functools
import io
import types

import edge_tts
import numpy as np
import soundfile as sf

from src.core.expression.prosody import combine_hz, combine_percent
from src.interfaces.base_interfaces import TTSInterface
from src.utils.logger import get_logger

logger = get_logger("bea.tts.edge")

# what edge-tts asks the service for, and cannot be told otherwise
ASKED_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
ASKED_BPS = 48_000
# the same 24 khz voice at twice the bitrate: the service serves it just as fast,
# with a fraction of the mp3 artefacts a recording or a pair of headphones hears as a gargle
BETTER_FORMAT = "audio-24khz-96kbitrate-mono-mp3"
BETTER_BPS = 96_000

# the first part of a streamed piece goes once this much speech has arrived; each
# part after it waits for twice as much, so a sentence costs a handful of decodes
FIRST_PART_SECONDS = 1 / 3

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
            communicate, _ = _communicate(text, self.voice, pitch=pitch, rate=rate, volume=volume)
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
            communicate, bps = _communicate(text, self.voice, pitch=pitch, rate=rate, volume=volume)
            mp3 = bytearray()
            sent = 0
            # counted in speech, not bytes: a richer format must not make her start any sooner or later
            due = int(bps / 8 * FIRST_PART_SECONDS)
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


def _communicate(text: str, voice: str, **prosody):
    """An edge request for the better format when it can be asked for, and its bitrate."""
    better = _asking_for_better(edge_tts.Communicate)
    if better is None:
        return edge_tts.Communicate(text, voice, **prosody), ASKED_BPS
    return better(text, voice, **prosody), BETTER_BPS


@functools.lru_cache(maxsize=None)
def _asking_for_better(base: type):
    """`base` with its one hard-coded format swapped for the better one, or None.

    edge-tts writes the format into the request it sends and has no argument
    for it, so the swap is made on that single constant, leaving the rest of the
    protocol theirs. When a release asks some other way the constant is not
    found and edge is used as it comes, with a warning, never half-patched.
    """
    stream = getattr(base, "_Communicate__stream", None)
    if not isinstance(stream, types.FunctionType):
        return _as_it_comes()
    patched, found = _swapped(stream.__code__)
    if found != 1:
        return _as_it_comes()
    function = types.FunctionType(patched, stream.__globals__, stream.__name__,
                                  stream.__defaults__, stream.__closure__)
    # `self.__stream()` inside edge-tts is looked up under this mangled name
    return type(base.__name__, (base,), {"_Communicate__stream": function})


def _swapped(code: types.CodeType) -> tuple[types.CodeType, int]:
    """`code` asking for the better format, and how many constants named the old one."""
    found = 0
    consts = []
    for const in code.co_consts:
        if isinstance(const, str) and ASKED_FORMAT in const:
            found += 1
            const = const.replace(ASKED_FORMAT, BETTER_FORMAT)
        elif isinstance(const, types.CodeType):
            const, inner = _swapped(const)
            found += inner
        consts.append(const)
    return code.replace(co_consts=tuple(consts)), found


def _as_it_comes() -> None:
    logger.warning(f"edge-tts no longer asks for {ASKED_FORMAT} the way it did; "
                   f"her voice stays at {ASKED_BPS // 1000} kbps")
    return None


def _prefix_of(previous: np.ndarray, whole: np.ndarray) -> bool:
    """Whether what was already handed over is still the start of the whole."""
    return len(previous) <= len(whole) and bool(np.array_equal(previous, whole[:len(previous)]))


def _decode(mp3: bytes) -> tuple[np.ndarray, int]:
    return sf.read(io.BytesIO(mp3), dtype="float32")
