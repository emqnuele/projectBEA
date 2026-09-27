/**
 * How she carries herself in each state, and the timing behind it.
 *
 * Plain numbers and functions of a random draw, so node can test them without
 * three.js; `life.js` turns them into bone offsets. Angles are radians,
 * distances metres, times seconds.
 *
 *  wander    how far the gaze drifts around its focus
 *  look      where attention sits relative to the camera, [right, up]
 *  head      the fraction of the gaze angle the head turns to follow
 *  headRate  how fast the head catches up; the eyes are already there
 *  blink     seconds between blinks, [shortest, longest]
 *  breath    depth of breathing; sway, the weight shift under it
 *  saccade   the small jumps of the eyes: minimum gap, mean gap, radius in degrees
 *  nod       listening nods: mean gap, jitter either side, depth, length
 *  voice     how far the head dips with the loudness of her own voice
 *  droop     the head falling forward, asleep
 */

export const STATES = {
    idle: {
        wander: 0.09, look: [0, 0], head: 0.16, headRate: 2.2, blink: [2.5, 6.5], breath: 1, sway: 1,
        eyesShut: 0, saccade: { gap: 0.6, mean: 1.6, radius: 4 }, nod: null, voice: 0, droop: 0,
    },
    listening: {
        wander: 0.05, look: [0, 0], head: 0.06, headRate: 2.6, blink: [2, 4.5], breath: 1, sway: 0.7,
        eyesShut: 0, saccade: { gap: 0.8, mean: 2.2, radius: 2.5 },
        nod: { every: 2.5, jitter: 0.7, depth: 0.05, length: 0.55 }, voice: 0, droop: 0,
    },
    thinking: {
        // eyes up and to one side, the head following slowly behind them
        wander: 0.05, look: [0.22, 0.2], head: 0.3, headRate: 1.1, blink: [4, 9], breath: 1, sway: 0.8,
        eyesShut: 0, saccade: { gap: 0.4, mean: 1.0, radius: 3 }, nod: null, voice: 0, droop: 0,
    },
    talking: {
        wander: 0.14, look: [0, 0], head: 0.1, headRate: 2.2, blink: [2.5, 6], breath: 1.15, sway: 1.15,
        eyesShut: 0, saccade: { gap: 0.7, mean: 2.0, radius: 3 }, nod: null, voice: 0.07, droop: 0,
    },
    sleeping: {
        wander: 0, look: [0, 0], head: 0, headRate: 1, blink: [99, 99], breath: 0.7, sway: 0.35,
        eyesShut: 1, saccade: null, nod: null, voice: 0, droop: 0.12,
    },
};

/** The state by name; anything the page does not know reads as idle. */
export function stateNamed(name) {
    return STATES[name] || STATES.idle;
}

/**
 * Seconds until the next saccade, from a uniform draw `u` in [0, 1).
 *
 * A minimum gap and then an exponential wait: a rate per second rather than a
 * chance per frame, so the eyes move as often at 30 fps as at 144.
 */
export function saccadeWait(saccade, u) {
    const spread = Math.max(saccade.mean - saccade.gap, 0);
    return saccade.gap - Math.log(1 - Math.min(u, 0.999999)) * spread;
}

/** A point on a disc of `radius` degrees, uniform over its area, from two draws. */
export function saccadeOffset(radius, u, v) {
    const r = radius * Math.sqrt(u);
    const a = 2 * Math.PI * v;
    return [r * Math.cos(a), r * Math.sin(a)];
}

/** Seconds until the next nod, from a uniform draw. */
export function nodWait(nod, u) {
    return Math.max(nod.length, nod.every + (u * 2 - 1) * nod.jitter);
}

/** How far into a nod the head is, 0 to 1 and back, over `length` seconds. */
export function nodCurve(t, length) {
    if (t <= 0 || t >= length) return 0;
    const s = Math.sin(Math.PI * (t / length));
    return s * s;
}
