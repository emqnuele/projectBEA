/**
 * The decisions behind the browser-source PNG avatar. Pure, so node can test them.
 */

// a mouth opens past one level and shuts below a lower one, so a word hovering at the edge does not flicker
export const OPEN_AT = 0.22;
export const CLOSE_AT = 0.12;

/** Whether the mouth is open now, given whether it was open and how loud this frame is. */
export function mouthGate(wasOpen, level, openAt = OPEN_AT, closeAt = CLOSE_AT) {
    return wasOpen ? level > closeAt : level > openAt;
}

/** The picture key to draw. `png` is what the engine published for her face. */
export function frameKey(png, { talking, open, blinking }) {
    if (!png) return null;
    if (talking) return open ? png.open : png.closed;
    if (blinking && png.blink) return png.blink;
    return png.rest;
}

/**
 * How far the picture rises and swells, as [pixels up, scale].
 *
 * A slow breath at rest, and a small hop with the loudness of her voice, so a
 * still image never reads as a screenshot.
 */
export function bob(t, level = 0, asleep = false) {
    const breath = Math.sin(t * (asleep ? 1.1 : 1.6)) * (asleep ? 2 : 3);
    return [breath + level * 10, 1 + Math.sin(t * 1.6) * 0.004 + level * 0.012];
}
