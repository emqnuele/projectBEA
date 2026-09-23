"""Whether edge's mp3 can still be streamed a stretch at a time.

`EdgeTTSWrapper.generate_stream` hands the call each new stretch of a sentence
by decoding everything received so far and sending what is new. That is only
the same audio as decoding the finished file if every prefix of edge's mp3
decodes to a prefix of the whole — true today, because edge sends plain frames
with no gapless header, and something a new edge voice format or a libsndfile
upgrade could quietly break. The tests run against a synthetic clip; this asks
the real service, and CI asks it nightly (the `edge-prefix` job) — a service
hiccup should not read as a broken branch on every push.

    uv run python tools/edge_prefix_check.py
    uv run python tools/edge_prefix_check.py --voice it-IT-ElsaNeural --text "Sì."

Exits non-zero when any cut disagrees with the whole.
"""

import argparse
import asyncio
import io
import sys

import edge_tts
import numpy as np
import soundfile as sf

SAMPLES = [
    ("it-IT-ElsaNeural", "Ah, davvero? Non ci avevo mai pensato, ma adesso ha perfettamente senso."),
    ("en-US-JennyNeural", "Okay, so here's the thing: a creeper blew up the house I was building."),
    ("it-IT-ElsaNeural", "Sì."),
]

# a byte sweep on top of edge's own chunk boundaries, so cuts land mid-frame too
SWEEP_BYTES = 97


def _decode(mp3: bytes) -> np.ndarray:
    return sf.read(io.BytesIO(mp3), dtype="float32")[0]


async def check(voice: str, text: str) -> bool:
    chunks = [c["data"] async for c in edge_tts.Communicate(text, voice).stream()
              if c["type"] == "audio"]
    mp3 = b"".join(chunks)
    whole = _decode(mp3)
    cuts = sorted(set(np.cumsum([len(c) for c in chunks]).tolist())
                  | set(range(SWEEP_BYTES, len(mp3), SWEEP_BYTES)))
    wrong = []
    for cut in cuts:
        try:
            part = _decode(mp3[:cut])
        except Exception:
            # too short to hold a frame: the stream decodes it again later
            continue
        if len(part) > len(whole) or not np.array_equal(part, whole[:len(part)]):
            wrong.append(cut)
    verdict = "ok" if not wrong else f"{len(wrong)} cut(s) disagree, first at byte {wrong[0]}"
    print(f"{voice}: {len(mp3)} bytes, {len(chunks)} chunks, {len(cuts)} cuts - {verdict}")
    return not wrong


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--voice")
    parser.add_argument("--text")
    args = parser.parse_args()
    samples = [(args.voice, args.text)] if args.voice and args.text else SAMPLES
    results = [await check(voice, text) for voice, text in samples]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
