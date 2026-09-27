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

// one table for the page and for vtube studio (`src/modules/avatar/vts_life.py` reads the same file)
import STATES from './states.json' with { type: 'json' };

export { STATES };

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
