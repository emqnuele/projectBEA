"""Builds the corpus `bench.js` measures the voice detectors on.

Speech is real synthesized speech (edge-tts, several voices, two languages),
laid out as a call: turns with the pauses a sentence has inside it, and gaps
between turns. Ground truth comes from the clean speech track, before any noise
is mixed in, so it is exact rather than another detector's opinion.

Every scenario is the same timeline of turns under a different background, so
a difference between two rows is the background and nothing else.

    uv run python tools/vad_bench/corpus.py            # into data/vad_bench/
    uv run python tools/vad_bench/corpus.py --out DIR

Needs ffmpeg on the path and a network for the first run; the speech is cached.
"""

import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

RATE = 48000
SEED = 7

VOICES = [
    "it-IT-DiegoNeural", "it-IT-ElsaNeural", "it-IT-IsabellaNeural",
    "en-US-GuyNeural", "en-US-JennyNeural", "en-GB-SoniaNeural",
]

# what people say to her in a call: short answers, a question, a story with a
# hesitation in it. The commas and full stops are where the pauses come from.
LINES = [
    ("it", "Sì."),
    ("it", "Aspetta, no, intendevo l'altro."),
    ("it", "Allora, ascolta un attimo. Ieri sera stavo giocando e a un certo punto, boh, il server è crashato."),
    ("it", "Ma tu hai visto qualcosa?"),
    ("it", "Guarda, non lo so. Forse domani, se ho tempo, ci riprovo."),
    ("it", "Ok. Perfetto, grazie."),
    ("it", "Comunque, dicevo, la cosa strana è che prima funzionava. Poi, niente, si è bloccato tutto."),
    ("it", "Ehm, come si chiamava quel gioco? Quello con i blocchi."),
    ("en", "Yeah."),
    ("en", "Wait, hold on, let me check something."),
    ("en", "So I was thinking, maybe we could build a house near the river. What do you think?"),
    ("en", "No, no, the other one. The one on the left."),
    ("en", "Honestly, I have no idea. It just stopped working, and then, well, it came back."),
    ("en", "Can you hear me?"),
    ("en", "Right. Okay, so, first thing tomorrow, we fix the server. Then we play."),
    ("en", "Hmm. Let me think about it."),
]

GAPS_S = (1.6, 3.2)
# below this, relative to the loudest 10 ms of the clean turn, is not voice
VOICED_DB = -40.0
HOP = RATE // 100


async def speak(text: str, voice: str, cache: Path) -> np.ndarray:
    import edge_tts

    key = hashlib.sha256(f"{voice}|{text}".encode()).hexdigest()[:16]
    mp3 = cache / f"{key}.mp3"
    if not mp3.exists():
        await edge_tts.Communicate(text, voice).save(str(mp3))
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(mp3), "-ar", str(RATE), "-ac", "1", "-f", "f32le", "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def voiced_regions(clean: np.ndarray) -> list:
    """[start, end] in seconds of every stretch of voice in a clean signal."""
    frames = len(clean) // HOP
    rms = np.sqrt(np.mean(clean[: frames * HOP].reshape(frames, HOP) ** 2, axis=1) + 1e-12)
    on = 20 * np.log10(rms / rms.max()) > VOICED_DB
    regions, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            regions.append([start * HOP / RATE, i * HOP / RATE])
            start = None
    if start is not None:
        regions.append([start * HOP / RATE, frames * HOP / RATE])
    # a gap under 30 ms is a plosive, not a pause
    merged = []
    for r in regions:
        if merged and r[0] - merged[-1][1] < 0.03:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return merged


async def timeline(cache: Path, rng: np.random.Generator):
    """The clean speech track and its turns, shared by every scenario."""
    pieces, turns, at = [], [], 1.5
    pieces.append(np.zeros(int(at * RATE)))
    for n, (lang, text) in enumerate(LINES):
        voices = [v for v in VOICES if v.startswith(lang)]
        voice = voices[n % len(voices)]
        audio = await speak(text, voice, cache)
        regions = voiced_regions(audio)
        lead, tail = regions[0][0], regions[-1][1]
        audio = audio[int(lead * RATE): int(tail * RATE)]
        regions = [[s - lead + at, e - lead + at] for s, e in regions]
        pauses = [regions[i + 1][0] - regions[i][1] for i in range(len(regions) - 1)]
        turns.append({
            "text": text, "voice": voice, "start": regions[0][0], "end": regions[-1][1],
            "regions": regions, "longest_pause": max(pauses, default=0.0),
        })
        gap = rng.uniform(*GAPS_S)
        pieces += [audio, np.zeros(int(gap * RATE))]
        at += len(audio) / RATE + gap
    return np.concatenate(pieces), turns


def fan(n, rng):
    brown = np.cumsum(rng.standard_normal(n))
    brown -= np.convolve(brown, np.ones(4801) / 4801, mode="same")
    t = np.arange(n) / RATE
    return brown / np.std(brown) + 0.3 * np.sin(2 * np.pi * 100 * t)


def hiss(n, rng):
    white = rng.standard_normal(n)
    spectrum = np.fft.rfft(white)
    spectrum /= np.sqrt(np.maximum(np.arange(len(spectrum)), 1))
    return np.fft.irfft(spectrum, n)


def keyboard(n, rng):
    """Typing in bursts: short decaying clicks with a resonance, 4-9 a second."""
    out = np.zeros(n)
    t, click_len = 0.0, int(0.012 * RATE)
    env = np.exp(-np.arange(click_len) / (0.002 * RATE))
    ring = np.sin(2 * np.pi * 3100 * np.arange(click_len) / RATE)
    while t < n / RATE:
        if rng.random() < 0.25:
            t += rng.uniform(0.5, 2.0)
            continue
        at = int(t * RATE)
        click = (rng.standard_normal(click_len) * 0.6 + ring) * env * rng.uniform(0.5, 1.0)
        out[at: at + click_len] += click[: max(0, min(click_len, n - at))]
        t += rng.uniform(1 / 9, 1 / 4)
    return out


def music(n, rng):
    """Chords, a bass line and a beat at 110 bpm: squarely in the speech band."""
    t = np.arange(n) / RATE
    beat = 60 / 110
    roots = [220.0, 174.6, 261.6, 196.0]
    out = np.zeros(n)
    bar = (t // (4 * beat)).astype(int) % len(roots)
    for ratio in (1.0, 1.26, 1.5):
        f = np.array(roots)[bar] * ratio
        phase = 2 * np.pi * np.cumsum(f) / RATE
        for h in range(1, 6):
            out += np.sin(h * phase) / h / 3
    since = t % beat
    out += 1.5 * np.sin(2 * np.pi * 55 * since) * np.exp(-since / 0.08)
    half = (t + beat / 2) % beat
    out += 0.3 * rng.standard_normal(n) * np.exp(-half / 0.01)
    return out


BACKGROUNDS = {"fan": fan, "hiss": hiss, "keyboard": keyboard, "music": music}


def mix(speech, noise, snr_db, speech_rms):
    noise = noise / np.sqrt(np.mean(noise ** 2)) * speech_rms / (10 ** (snr_db / 20))
    return speech + noise


def active_rms(signal, turns):
    parts = [signal[int(s * RATE): int(e * RATE)] for t in turns for s, e in t["regions"]]
    return float(np.sqrt(np.mean(np.concatenate(parts) ** 2)))


def write(out: Path, name: str, signal: np.ndarray, turns: list, meta: dict):
    # impulsive noise at a low snr peaks far above its rms: the whole mix comes
    # down together, which keeps the snr and only moves the level
    peak = np.max(np.abs(signal))
    if peak > 0.95:
        signal = signal * 0.95 / peak
        meta = {**meta, "gain_db": round(20 * np.log10(0.95 / peak), 1)}
    pcm = np.round(signal * 32767).astype("<i2")
    stereo = np.repeat(pcm[:, None], 2, axis=1).tobytes()
    (out / f"{name}.pcm").write_bytes(stereo)
    (out / f"{name}.json").write_text(json.dumps({"name": name, "rate": RATE, "turns": turns, **meta}, indent=1))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="data/vad_bench")
    args = parser.parse_args()
    if shutil.which("ffmpeg") is None:
        print("ffmpeg is needed to decode edge-tts output")
        return 1

    out = Path(args.out)
    cache = out / "tts"
    cache.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    speech, turns = await timeline(cache, rng)
    # a normal microphone level, and one a speaker far from theirs would give
    normal = speech / np.max(np.abs(speech)) * 0.25
    rms = active_rms(normal, turns)
    n = len(normal)
    duration = n / RATE

    scenarios = [("clean", normal, {"background": "none", "snr_db": None})]
    for index, (background, make) in enumerate(BACKGROUNDS.items()):
        noise = make(n, np.random.default_rng(SEED + 100 + index))
        for snr in (15, 5):
            scenarios.append((f"{background}_{snr}db", mix(normal, noise, snr, rms),
                              {"background": background, "snr_db": snr}))
        # the same noise with nobody talking: every turn out of it is a false one
        scenarios.append((f"{background}_only", noise / np.sqrt(np.mean(noise ** 2)) * rms / (10 ** (5 / 20)),
                          {"background": background, "snr_db": None, "noise_only": True}))
    quiet = normal * 10 ** (-20 / 20)
    scenarios.append(("quiet_clean", quiet, {"background": "none", "snr_db": None, "level_db": -20}))
    scenarios.append(("quiet_fan_15db", mix(quiet, fan(n, np.random.default_rng(SEED + 1)), 15, rms / 10),
                      {"background": "fan", "snr_db": 15, "level_db": -20}))

    for name, signal, meta in scenarios:
        write(out, name, signal, [] if meta.get("noise_only") else turns, meta)
        print(f"  {name:<18} {duration:6.1f}s")
    pauses = sorted(t["longest_pause"] for t in turns)
    print(f"{len(turns)} turns; longest pause inside a turn: median {np.median(pauses) * 1000:.0f} ms, "
          f"max {pauses[-1] * 1000:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
