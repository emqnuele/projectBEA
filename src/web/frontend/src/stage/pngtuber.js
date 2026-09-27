/**
 * The PNG avatar, drawn in the browser source.
 *
 * The engine publishes which pictures belong to the face she is wearing (keys,
 * never paths) and the envelope of each piece she says; this page flaps the
 * mouth off its own clock and never asks OBS for anything.
 */

import { emptyMouth, frameAt, startMouth } from './mouth.js';
import { bob, frameKey, mouthGate } from './sprite.js';

const BLINK_EVERY = [2.5, 6.5];
const BLINK_SECONDS = 0.12;

// how fast the hop follows her voice: per word, not per frame
const LEVEL_RATE = 14;

function url(key) {
    const [mood, slot] = key.split('/');
    return `/stage/preview?mood=${encodeURIComponent(mood)}&state=${encodeURIComponent(slot)}`;
}

export function createPngTuber(root, config = {}) {
    const img = document.createElement('img');
    img.className = 'pngtuber';
    img.alt = '';
    root.appendChild(img);

    const preloaded = new Map();
    const broken = new Set();
    let png = null;
    let state = 'idle';
    let mouth = emptyMouth();
    let open = false;
    let level = 0;
    let shown = null;
    let good = null;
    let blinkIn = 1 + Math.random() * 3;
    let blinking = 0;
    let last = performance.now();

    img.addEventListener('load', () => { good = shown; });
    img.addEventListener('error', () => {
        // a picture mapped but not on disk: keep the last one that drew
        if (shown) broken.add(shown);
        shown = good;
        if (good) img.src = url(good);
    });

    function preload(frames) {
        for (const key of Object.values(frames || {})) {
            if (!key || preloaded.has(key)) continue;
            const image = new Image();
            image.src = url(key);
            preloaded.set(key, image);
        }
    }

    function draw(key) {
        if (!key || key === shown || broken.has(key)) return;
        shown = key;
        img.src = url(key);
    }

    function setBackground(colour) {
        root.style.background = colour || 'transparent';
    }
    setBackground(config.background);

    function tick(now) {
        const dt = Math.min((now - last) / 1000, 0.1);
        last = now;
        const talking = state === 'talking';

        const frame = talking ? frameAt(mouth, now) : null;
        const loudness = frame ? frame[0] : 0;
        open = mouthGate(open, loudness);
        level += (loudness - level) * (1 - Math.exp(-LEVEL_RATE * dt));

        blinkIn -= dt;
        if (blinkIn <= 0) {
            blinkIn = BLINK_EVERY[0] + Math.random() * (BLINK_EVERY[1] - BLINK_EVERY[0]);
            blinking = BLINK_SECONDS;
        }
        blinking = Math.max(0, blinking - dt);

        draw(frameKey(png, { talking, open, blinking: blinking > 0 }));
        const [up, scale] = bob(now / 1000, level, state === 'sleeping');
        img.style.transform = `translate(-50%, ${-up}px) scale(${scale})`;
        requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);

    return {
        apply(patch, { animate = true } = {}) {
            if ('png' in patch) {
                png = patch.png;
                preload(png);
            }
            if ('state' in patch) state = patch.state;
            if (!animate) {
                mouth = emptyMouth();
                return;
            }
            if (patch.envelope) mouth = startMouth(patch.envelope, patch.envelope_fps, performance.now());
        },

        setLook(next = {}) {
            setBackground(next.background);
        },
    };
}
