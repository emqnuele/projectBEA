import React, { useEffect, useRef } from 'react';
import { useAppearance } from '../../state/AppearanceProvider';

// the classic 8×8 ordered-dither threshold map, normalised to 0..1
const BAYER = [
    0, 32, 8, 40, 2, 34, 10, 42,
    48, 16, 56, 24, 50, 18, 58, 26,
    12, 44, 4, 36, 14, 46, 6, 38,
    60, 28, 52, 20, 62, 30, 54, 22,
    3, 35, 11, 43, 1, 33, 9, 41,
    51, 19, 59, 27, 49, 17, 57, 25,
    15, 47, 7, 39, 13, 45, 5, 37,
    63, 31, 55, 23, 61, 29, 53, 21,
].map((v) => (v + 0.5) / 64);

const SCALE = 5;        // one drawn pixel covers 5 screen pixels
const FRAME_MS = 1000 / 24;

function readTone(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return parseHex(value) || fallback;
}

function parseHex(hex) {
    const match = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if (!match) return null;
    return [parseInt(match[1], 16), parseInt(match[2], 16), parseInt(match[3], 16)];
}

/** `amount` of `from` folded into `into`, per channel. */
function mix(into, from, amount) {
    return into.map((channel, index) => Math.round(channel + (from[index] - channel) * amount));
}

/**
 * The ground the glass sits on.
 *
 * A flat fill gives refraction nothing to bend, so the backdrop carries a very
 * slow two-tone field, ordered-dithered rather than smoothly interpolated: the
 * texture is what the lens picks up at the rim.
 */
export function DitherField() {
    const canvasRef = useRef(null);
    const { settings } = useAppearance();

    useEffect(() => {
        if (!settings.dither) return undefined;
        const canvas = canvasRef.current;
        if (!canvas) return undefined;
        const context = canvas.getContext('2d', { alpha: false });
        if (!context) return undefined;

        const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        let width = 0;
        let height = 0;
        let image = null;
        let frame = 0;
        let last = 0;

        let dark = readTone('--bg', [8, 8, 10]);
        let light = readTone('--bg-raised', [14, 14, 18]);
        let accent = dark;

        const resize = () => {
            width = Math.max(1, Math.ceil(window.innerWidth / SCALE));
            height = Math.max(1, Math.ceil(window.innerHeight / SCALE));
            canvas.width = width;
            canvas.height = height;
            image = context.createImageData(width, height);
        };

        const readTones = () => {
            dark = readTone('--bg', dark);
            light = readTone('--bg-raised', light);
            // the brightest tone carries a trace of the chosen accent, so the
            // ground belongs to the same palette as everything sitting on it
            const hue = readTone('--accent-raw', [61, 125, 255]);
            accent = mix(light, hue, document.documentElement.dataset.theme === 'light' ? 0.1 : 0.16);
        };

        const draw = (time) => {
            const t = time / 22000;
            const data = image.data;
            // two slow centres, so the field never reads as a static gradient
            const ax = 0.28 + Math.sin(t * 1.7) * 0.22;
            const ay = 0.22 + Math.cos(t * 1.3) * 0.18;
            const bx = 0.78 + Math.cos(t * 1.1) * 0.18;
            const by = 0.82 + Math.sin(t * 0.9) * 0.16;

            for (let y = 0; y < height; y++) {
                const ny = y / height;
                for (let x = 0; x < width; x++) {
                    const nx = x / width;
                    const da = Math.hypot(nx - ax, (ny - ay) * 1.35);
                    const db = Math.hypot(nx - bx, (ny - by) * 1.35);
                    // inverse-square-ish falloff keeps the centres soft and the field dark
                    let value = 0.62 / (1 + da * 5.2) + 0.44 / (1 + db * 6.4);
                    value = Math.min(1, value);

                    const threshold = BAYER[(y & 7) * 8 + (x & 7)];
                    const level = value * 1.9 - threshold;
                    const tone = level > 0.62 ? accent : level > 0.14 ? light : dark;

                    const index = (y * width + x) * 4;
                    data[index] = tone[0];
                    data[index + 1] = tone[1];
                    data[index + 2] = tone[2];
                    data[index + 3] = 255;
                }
            }
            context.putImageData(image, 0, 0);
        };

        const loop = (time) => {
            if (time - last >= FRAME_MS) {
                last = time;
                draw(time);
            }
            frame = requestAnimationFrame(loop);
        };

        resize();
        readTones();
        draw(0);
        if (!reduced) frame = requestAnimationFrame(loop);

        const onResize = () => { resize(); draw(performance.now()); };
        window.addEventListener('resize', onResize);

        // the accent is written onto the root's style attribute, and so are the
        // glass sliders — coalesce, or dragging one repaints the whole field
        let pending = 0;
        const themeWatcher = new MutationObserver(() => {
            if (pending) return;
            pending = requestAnimationFrame(() => {
                pending = 0;
                readTones();
                draw(performance.now());
            });
        });
        themeWatcher.observe(document.documentElement, {
            attributes: true, attributeFilter: ['data-theme', 'style'],
        });

        return () => {
            cancelAnimationFrame(frame);
            if (pending) cancelAnimationFrame(pending);
            window.removeEventListener('resize', onResize);
            themeWatcher.disconnect();
        };
    }, [settings.dither]);

    if (!settings.dither) {
        return <div aria-hidden="true" className="fixed inset-0 -z-10 bg-bg" />;
    }

    return (
        <canvas
            ref={canvasRef}
            aria-hidden="true"
            className="fixed inset-0 -z-10 h-full w-full"
            style={{ imageRendering: 'pixelated' }}
        />
    );
}
