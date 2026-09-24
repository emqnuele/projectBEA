"""How well local whisper hears a call, per model, per language setting.

The question it answers is the one a bad call raises: is it the model, the
language detection, the machine, or the audio? Every turn is real synthesized
speech (edge-tts, the voices `vad_bench` uses) cut the way the discord bot cuts
it, so a row is one variable changed and nothing else.

Two numbers matter per row. `lang ok` is how often whisper decided the speech
was the language it is — a wrong answer does not fail, it transcribes *into*
the wrong language, which is the `'포언끼리'` a call in italian came back as.
`cer` is characters wrong against the line that was spoken.

    uv run python tools/stt_bench.py                        # base and small, italian
    uv run python tools/stt_bench.py --models tiny,base,small --lang it,en
    uv run python tools/stt_bench.py --threads 4,8 --json stt_bench.json

Needs ffmpeg and a network the first time; speech and weights are cached.
"""

import argparse
import asyncio
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RATE = 16000
SEED = 11

VOICES = {
    "it": ["it-IT-DiegoNeural", "it-IT-ElsaNeural", "it-IT-IsabellaNeural"],
    "en": ["en-US-GuyNeural", "en-US-JennyNeural", "en-GB-SoniaNeural"],
}

# what a call is mostly made of: short answers, then the odd real sentence.
# The first ones are under the second whisper needs to settle a language.
LINES = {
    "it": [
        "Sì.",
        "No, aspetta.",
        "Che hai detto?",
        "Su internet.",
        "Boh, non lo so.",
        "Ok, perfetto, grazie.",
        "Ma tu hai visto qualcosa?",
        "Aspetta, no, intendevo l'altro.",
        "Guarda, non lo so. Forse domani, se ho tempo, ci riprovo.",
        "Allora, ascolta un attimo. Ieri sera stavo giocando e il server è crashato.",
        "Comunque la cosa strana è che prima funzionava, poi si è bloccato tutto.",
        "Ehm, come si chiamava quel gioco? Quello con i blocchi.",
    ],
    "en": [
        "Yeah.",
        "Wait, what?",
        "Can you hear me?",
        "Hmm. Let me think about it.",
        "No, no, the other one. The one on the left.",
        "So I was thinking, maybe we could build a house near the river.",
        "Honestly, I have no idea. It just stopped working, and then it came back.",
    ],
}

# what reaches the transcriber from a real microphone, roughly: clean, a fan
# under it, and someone sitting far from a cheap mic
CONDITIONS = ("clean", "fan_15db", "far_quiet")


# --- the audio ----------------------------------------------------------------


async def _speak(text: str, voice: str, cache: Path) -> np.ndarray:
    import hashlib

    import edge_tts

    key = hashlib.sha256(f"{voice}|{text}".encode()).hexdigest()[:16]
    mp3 = cache / f"{key}.mp3"
    if not mp3.exists():
        await edge_tts.Communicate(text, voice).save(str(mp3))
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(mp3), "-ar", str(RATE), "-ac", "1",
         "-f", "f32le", "-"],
        check=True, capture_output=True,
    ).stdout
    return _trim(np.frombuffer(raw, dtype=np.float32).copy())


def _trim(audio: np.ndarray) -> np.ndarray:
    """Cut to the voice, with the ~100ms either side the bot's gate keeps."""
    hop = RATE // 100
    frames = len(audio) // hop
    if not frames:
        return audio
    rms = np.sqrt(np.mean(audio[: frames * hop].reshape(frames, hop) ** 2, axis=1) + 1e-12)
    voiced = np.flatnonzero(20 * np.log10(rms / rms.max()) > -40)
    if not len(voiced):
        return audio
    start = max(0, (voiced[0] - 10) * hop)
    end = min(len(audio), (voiced[-1] + 10) * hop)
    return audio[start:end]


def _fan(n: int, rng: np.random.Generator) -> np.ndarray:
    brown = np.cumsum(rng.standard_normal(n))
    brown -= np.convolve(brown, np.ones(1601) / 1601, mode="same")
    t = np.arange(n) / RATE
    return brown / np.std(brown) + 0.3 * np.sin(2 * np.pi * 100 * t)


def condition(audio: np.ndarray, name: str, rng: np.random.Generator) -> np.ndarray:
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if name == "clean":
        out = audio
    elif name == "fan_15db":
        noise = _fan(len(audio), rng)
        out = audio + noise / np.sqrt(np.mean(noise ** 2)) * rms / (10 ** (15 / 20))
    elif name == "far_quiet":
        # -24 dB and a floor of mic hiss 20 dB under what is left of the voice
        quiet = audio * 10 ** (-24 / 20)
        hiss = rng.standard_normal(len(audio))
        out = quiet + hiss / np.std(hiss) * rms * 10 ** (-24 / 20) / 10
    else:
        raise ValueError(name)
    # through int16, like everything the bot sends
    return (np.clip(np.round(out * 32767), -32768, 32767) / 32768.0).astype(np.float32)


# --- the score ----------------------------------------------------------------


def _normal(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s']", " ", text)
    return " ".join(text.split())


def cer(reference: str, heard: str) -> float:
    """Character error rate: edits to get from what was heard to what was said."""
    a, b = _normal(reference), _normal(heard)
    if not a:
        return 0.0 if not b else 1.0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        previous = current
    return min(1.0, previous[-1] / len(a))


# --- the run ------------------------------------------------------------------


def load(model: str, threads: int, root: str):
    from faster_whisper import WhisperModel

    from src.modules.STT.faster_whisper_stt import normalize_model

    return WhisperModel(normalize_model(model), device="cpu", compute_type="int8",
                        cpu_threads=threads, num_workers=1, download_root=root)


def run_one(model, audio: np.ndarray, pin: Optional[str]) -> dict:
    from src.modules.STT.faster_whisper_stt import TEMPERATURES

    started = time.perf_counter()
    segments, info = model.transcribe(audio, language=pin, temperature=TEMPERATURES,
                                      vad_filter=True)
    text = "".join(s.text for s in segments).strip()
    return {"text": text, "language": info.language,
            "p": float(info.language_probability),
            "ms": (time.perf_counter() - started) * 1000}


def summarize(rows: List[dict], spoken: str) -> dict:
    return {
        "n": len(rows),
        "lang_ok": sum(r["language"] == spoken for r in rows) / len(rows),
        "confident": sum(r["p"] >= 0.85 for r in rows) / len(rows),
        "cer": statistics.mean(r["cer"] for r in rows),
        "ms_p50": statistics.median(r["ms"] for r in rows),
        "ms_max": max(r["ms"] for r in rows),
    }


def _csv(text: str) -> List[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


async def main() -> int:
    from src.core.perf import physical_cores

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--models", default="base,small")
    parser.add_argument("--lang", default="it", help="languages spoken, e.g. it,en")
    parser.add_argument("--conditions", default=",".join(CONDITIONS))
    parser.add_argument("--threads", default="", help="cpu_threads to try; default physical cores")
    parser.add_argument("--root", default="data/models/whisper")
    parser.add_argument("--cache", default="data/vad_bench/tts")
    parser.add_argument("--json", default="", help="write every row here")
    parser.add_argument("--verbose", action="store_true", help="print every transcript")
    args = parser.parse_args()

    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    threads = [int(t) for t in _csv(args.threads)] or [physical_cores()]

    print(f"{platform.platform()} | {platform.processor() or platform.machine()} | "
          f"{os.cpu_count()} logical, {physical_cores()} physical")

    clips: Dict[str, list] = {}
    for spoken in _csv(args.lang):
        clips[spoken] = []
        for n, line in enumerate(LINES[spoken]):
            voices = VOICES[spoken]
            audio = await _speak(line, voices[n % len(voices)], cache)
            for name in _csv(args.conditions):
                clips[spoken].append((line, name, condition(audio, name, rng)))

    every: List[dict] = []
    header = (f"{'model':<8}{'thr':>4}  {'spoken':<6}{'pin':<6}{'condition':<11}"
              f"{'lang ok':>8}{'p>=.85':>8}{'cer':>7}{'p50 ms':>8}{'max ms':>8}")
    print(header)
    print("-" * len(header))
    for model_name in _csv(args.models):
        for thread_count in threads:
            model = load(model_name, thread_count, args.root)
            # the first decode pays for allocations nothing after it does
            run_one(model, np.zeros(RATE, dtype=np.float32), None)
            for spoken, items in clips.items():
                for pin in (None, spoken):
                    for name in _csv(args.conditions):
                        rows = []
                        for line, cond, audio in items:
                            if cond != name:
                                continue
                            row = run_one(model, audio, pin)
                            row.update({"model": model_name, "threads": thread_count,
                                        "spoken": spoken, "pin": pin or "auto",
                                        "condition": cond, "line": line,
                                        "seconds": len(audio) / RATE,
                                        "cer": cer(line, row["text"])})
                            rows.append(row)
                            if args.verbose:
                                print(f"    {row['seconds']:.1f}s {row['language']} "
                                      f"p={row['p']:.2f} {line!r} -> {row['text']!r}")
                        every += rows
                        s = summarize(rows, spoken)
                        print(f"{model_name:<8}{thread_count:>4}  {spoken:<6}{pin or 'auto':<6}"
                              f"{name:<11}{s['lang_ok']:>8.0%}{s['confident']:>8.0%}"
                              f"{s['cer']:>7.2f}{s['ms_p50']:>8.0f}{s['ms_max']:>8.0f}")
            del model

    short = [r for r in every if r["pin"] == "auto" and r["seconds"] < 1.2]
    if short:
        print(f"\nauto on turns under 1.2s: {sum(r['language'] == r['spoken'] for r in short)}"
              f"/{len(short)} placed right")

    if args.json:
        Path(args.json).write_text(json.dumps(every, indent=1, ensure_ascii=False),
                                   encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
