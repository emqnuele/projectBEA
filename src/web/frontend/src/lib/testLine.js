/**
 * A made-up line for the preview's mouth: syllables at a speaking pace, gaps
 * between words, the vowel wandering from dark to bright. The same seed gives
 * the same line, so what you tune against does not change under you.
 */

function random(seed) {
    let s = seed >>> 0;
    return () => {
        s = (s * 1664525 + 1013904223) >>> 0;
        return s / 2 ** 32;
    };
}

/** `[open, shape]` frames at `fps`, the shape the engine sends. */
export function testEnvelope(seconds = 3, fps = 30, seed = 7) {
    const next = random(seed);
    const frames = [];
    const total = Math.round(seconds * fps);
    let shape = 0.5;
    while (frames.length < total) {
        // a word: two to four syllables of about 0.2 s, then a short pause
        const syllables = 2 + Math.floor(next() * 3);
        for (let i = 0; i < syllables && frames.length < total; i += 1) {
            const length = Math.max(3, Math.round(fps * (0.16 + next() * 0.08)));
            const peak = 0.45 + next() * 0.55;
            shape = Math.min(1, Math.max(0, shape + (next() - 0.5) * 0.5));
            for (let f = 0; f < length && frames.length < total; f += 1) {
                const open = Math.sin(Math.PI * (f / length)) ** 2 * peak;
                frames.push([Number(open.toFixed(3)), Number(shape.toFixed(3))]);
            }
        }
        const gap = Math.round(fps * (0.06 + next() * 0.12));
        for (let f = 0; f < gap && frames.length < total; f += 1) frames.push([0, Number(shape.toFixed(3))]);
    }
    return frames;
}
