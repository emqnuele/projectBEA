/**
 * Where her mouth is in the line she is saying, by the page's own clock.
 *
 * The engine sends the whole envelope of a piece before it plays; the page
 * runs it from the moment it arrived. Pure, so node can test it.
 */

export function emptyMouth() {
    return { frames: [], fps: 30, startedAt: 0 };
}

/** A line whose envelope just arrived, starting now. */
export function startMouth(frames, fps, now) {
    return { frames: frames || [], fps: fps || 30, startedAt: now };
}

/** The [open, shape] frame due at `now`, or null before, after or without one. */
export function frameAt(mouth, now) {
    if (!mouth.frames.length) return null;
    const index = Math.floor(((now - mouth.startedAt) / 1000) * mouth.fps);
    if (index < 0 || index >= mouth.frames.length) return null;
    return mouth.frames[index];
}
