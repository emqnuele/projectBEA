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


# how often the mouth is told what to do. 30 is well under a stream's frame rate
# and already smoother than a mouth can move.
ENVELOPE_FPS = 30

# the quietest line that still opens her mouth all the way. The envelope is
# normalised so that any engine's output moves a mouth at all, but normalising a
# whisper against its own peak draws it exactly like a shout.
MOUTH_FLOOR_RMS = 0.05

# Where a mouth sits on the vowel axis, as one number in [0, 1] — dark to
# bright. One number rather than a class per frame because that is what a
# spectrum actually gives you, and because a blend between two neighbours moves
# like a mouth where a hard choice between five flickers.
#
# The band is speech: under the first bound is a hum with no vowel in it, over
# the second is an "s", and neither is a shape worth drawing.
DARKEST_HZ = 350.0
BRIGHTEST_HZ = 2600.0

# a frame this quiet has no vowel to measure, only the noise floor's own colour
_SHAPE_FLOOR_RMS = 0.01

# what a frame falls back to when there is nothing to measure: the middle of the
# axis, which is an open `aa` — the shape a mouth already had before any of this
NEUTRAL_SHAPE = 0.5


def envelope(audio: np.ndarray, sample_rate: int, fps: int = ENVELOPE_FPS) -> list:
    """What the mouth does, per frame: `[how open, what shape]`.

    Not a phoneme model. How open comes from the RMS of the audio she is about
    to say; what shape comes from where that frame's energy sits in the
    spectrum, which is what separates an "oo" from an "ee" without knowing a
    single word. Both are computed here rather than in the browser because the
    audio is played on this machine and the page never hears it — and here they
    are testable without one.
    """
    if audio is None or getattr(audio, "size", 0) == 0:
        return []
    mono = to_mono(np.asarray(audio))
    if mono.dtype == np.int16:
        mono = mono.astype(np.float32) / 32768.0

    hop = max(1, int(sample_rate) // max(1, int(fps)))
    frames = mono.size // hop
    if frames == 0:
        return []

    blocks = mono[: frames * hop].reshape(frames, hop).astype(np.float64)
    rms = np.sqrt(np.mean(np.square(blocks), axis=1))
    shapes = _shapes(blocks, rms, sample_rate)

    peak = rms.max()
    open_by_frame = (rms / max(peak, MOUTH_FLOOR_RMS)) if peak > 0 else np.zeros(frames)

    # rounded because this crosses the wire: three decimals is finer than a
    # mouth can be seen to move, and halves the payload
    return [[round(float(how_open), 3), round(float(shape), 3)]
            for how_open, shape in zip(open_by_frame, shapes, strict=True)]


def _shapes(blocks: np.ndarray, rms: np.ndarray, sample_rate: int) -> np.ndarray:
    """Each frame's place on the vowel axis, from the centre of its spectrum.

    The spectral centroid is the frequency the frame's energy balances around.
    It rises for the bright vowels and falls for the dark ones, which is the
    whole of what a mouth has to show — and it is one FFT per frame of a fifth
    of a second, so it costs nothing worth measuring.
    """
    spectrum = np.abs(np.fft.rfft(blocks * np.hanning(blocks.shape[1]), axis=1))
    hertz = np.fft.rfftfreq(blocks.shape[1], d=1.0 / max(1, int(sample_rate)))

    energy = spectrum.sum(axis=1)
    # a frame with no energy would divide by zero; it also has no vowel
    quiet = (energy <= 0) | (rms < _SHAPE_FLOOR_RMS)
    centroid = (spectrum @ hertz) / np.where(energy > 0, energy, 1.0)

    # logarithmic, because pitch is: the distance from 350 to 700 Hz is heard as
    # the same step as the one from 700 to 1400
    span = np.log(BRIGHTEST_HZ / DARKEST_HZ)
    placed = np.log(np.clip(centroid, DARKEST_HZ, BRIGHTEST_HZ) / DARKEST_HZ) / span
    return np.where(quiet, NEUTRAL_SHAPE, placed)
