"""Turning whatever the TTS produced into what a voice call wants to be fed.

Discord plays 48 kHz stereo signed-16 little-endian and nothing else, while every
engine hands back something different — Kokoro 24 kHz float mono, Edge whatever
the mp3 decoded to, Orpheus 24 kHz PCM. Somebody has to bridge that, and it is
cheaper to do it here, where numpy already lives, than in the bot: node would
need a resampler, and the bot's job is to move bytes, not to do DSP.

Pure functions on arrays: no engine, no socket, no config.
"""

from typing import Tuple

import numpy as np

# what discord's opus encoder expects, and the only thing it expects
CALL_SAMPLE_RATE = 48000
CALL_CHANNELS = 2
BYTES_PER_SAMPLE = 2
CALL_BYTES_PER_MS = CALL_SAMPLE_RATE * CALL_CHANNELS * BYTES_PER_SAMPLE // 1000


def to_mono(audio: np.ndarray) -> np.ndarray:
    """Averages a stereo (or wider) buffer down to one channel."""
    if audio.ndim == 1:
        return audio
    return audio.mean(axis=1)


def resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Linear resampling of a mono buffer.

    Linear is enough here: TTS output is band-limited speech going *up* to 48 kHz,
    where the artefacts of interpolation sit above anything the voice contains.
    Downsampling would deserve a real filter — we never do it on this path.
    """
    if source_rate == target_rate or audio.size == 0:
        return audio
    duration = audio.size / float(source_rate)
    target_size = int(round(duration * target_rate))
    if target_size <= 0:
        return np.zeros(0, dtype=np.float32)
    source_t = np.arange(audio.size, dtype=np.float64) / float(source_rate)
    target_t = np.arange(target_size, dtype=np.float64) / float(target_rate)
    return np.interp(target_t, source_t, audio).astype(np.float32)


def to_int16(audio: np.ndarray) -> np.ndarray:
    """Floats in [-1, 1] to signed 16-bit, clipped rather than wrapped.

    Wrapping is what turns a slightly hot sample into a click, and a click in the
    middle of a sentence sounds like a broken bot, not like a loud one.
    """
    if audio.dtype == np.int16:
        return audio
    return (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)


def to_call_pcm(audio: np.ndarray, sample_rate: int) -> bytes:
    """Whatever the engine produced -> 48 kHz stereo s16le bytes, ready for the call."""
    if audio is None or getattr(audio, "size", 0) == 0:
        return b""
    mono = to_mono(np.asarray(audio))
    if mono.dtype == np.int16:
        mono = mono.astype(np.float32) / 32768.0
    mono = resample(mono.astype(np.float32), sample_rate, CALL_SAMPLE_RATE)
    stereo = np.repeat(to_int16(mono)[:, None], CALL_CHANNELS, axis=1)
    return stereo.astype("<i2").tobytes()


def duration_ms(pcm: bytes) -> int:
    """How long a call-format buffer lasts."""
    return len(pcm) // CALL_BYTES_PER_MS if CALL_BYTES_PER_MS else 0


def split_at_ms(pcm: bytes, played_ms: int) -> Tuple[bytes, bytes]:
    """Splits a call-format buffer into (heard, unheard) at a playback position.

    This is how she finds out where she was cut off: the bot reports how many
    milliseconds actually reached the room, and the tail is the part nobody got.
    """
    cut = max(0, min(len(pcm), played_ms * CALL_BYTES_PER_MS))
    # never split mid-frame: half a sample is a click
    cut -= cut % (CALL_CHANNELS * BYTES_PER_SAMPLE)
    return pcm[:cut], pcm[cut:]
