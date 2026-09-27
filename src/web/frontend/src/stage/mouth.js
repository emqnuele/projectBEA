/**
 * Where her mouth is in the line she is saying. Pure, so node can test it.
 *
 * A line is a list of segments, each one piece's envelope at its offset into
 * the line, and a clock: the page time the line started. A line played on
 * this machine is one segment whose clock starts when it arrives. A line in a
 * call arrives piece by piece and waits for the bot to say the room is hearing
 * it; every report after that moves the clock to what was actually heard.
 */

// a report this close to where the page already is changes nothing, so small jitter never shakes the mouth
export const RESYNC_MS = 50;

export function emptyMouth() {
    return { id: null, startedAt: null, segments: [] };
}

/** A whole line whose envelope just arrived, starting now. */
export function startMouth(frames, fps, now) {
    return { id: null, startedAt: now, segments: [{ offset: 0, frames: frames || [], fps: fps || 30 }] };
}

/** One piece of a call line, `offsetMs` into it. A piece of a new line starts a new one. */
export function addSegment(mouth, id, frames, fps, offsetMs) {
    const segment = { offset: offsetMs || 0, frames: frames || [], fps: fps || 30 };
    if (mouth.id !== id) return { id, startedAt: null, segments: [segment] };
    return { ...mouth, segments: [...mouth.segments, segment] };
}

/** The room has heard `playedMs` of line `id` as of `now`. */
export function syncMouth(mouth, id, playedMs, now) {
    const startedAt = now - (playedMs || 0);
    if (mouth.id !== id) return { id, startedAt, segments: [] };
    if (mouth.startedAt !== null && Math.abs(mouth.startedAt - startedAt) <= RESYNC_MS) return mouth;
    return { ...mouth, startedAt };
}

/** The [open, shape] frame due at `now`, or null before, between or after segments. */
export function frameAt(mouth, now) {
    if (mouth.startedAt === null) return null;
    const ms = now - mouth.startedAt;
    for (const segment of mouth.segments) {
        const index = Math.floor(((ms - segment.offset) / 1000) * segment.fps);
        if (index >= 0 && index < segment.frames.length) return segment.frames[index];
    }
    return null;
}
